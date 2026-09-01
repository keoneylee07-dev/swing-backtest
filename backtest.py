"""
Backtest harness for a rule-based swing strategy.

ANALYSIS ONLY. This file places no orders and connects to no broker.
It answers one question: does this rule set have positive expectancy?

Strategy (edit STRATEGY PARAMS to test your own variants):
    Setup   : uptrend pullback. Price above the 50-day SMA, then a
              pullback that touches the 20-day EMA and closes back above it.
    Entry   : next open after the trigger bar.
    Stop    : below the lowest low of the last SWING_LOOKBACK bars,
              minus a small buffer. Structural, not a round number.
    Target  : entry + (RR * risk_per_share).
    Exit    : whichever of stop/target the bar touches first. If a bar
              spans both, it counts as a LOSS (conservative assumption --
              you cannot know intrabar sequence from daily data).
    Sizing  : shares = floor(RISK_DOLLARS / risk_per_share), capped by
              available capital. Zero shares = trade skipped and logged.

Usage:
    python backtest.py --csv data/AAPL.csv
    python backtest.py --demo          # runs on synthetic data

CSV needs columns: date,open,high,low,close,volume
Get real data locally with:
    pip install yfinance
    python -c "import yfinance as yf; yf.download('AAPL','2020-01-01').to_csv('data/AAPL.csv')"
"""

import argparse
import math
import numpy as np
import pandas as pd

# ---------------------------------------------------------------- PARAMS

ACCOUNT_START   = 100.00   # starting capital
RISK_PCT        = 0.01     # 1R = 1% of STARTING equity (fixed, not compounding)
RR              = 2.0      # reward:risk target
FAST_EMA        = 20
SLOW_SMA        = 50
SWING_LOOKBACK  = 10       # bars back for the structural swing low
STOP_BUFFER     = 0.002    # 0.2% below the swing low, so you sit under the wick
MAX_HOLD_BARS   = 20       # time stop
MIN_PRICE       = 10.00    # your liquidity filters
MIN_AVG_VOLUME  = 2_000_000

RISK_DOLLARS    = ACCOUNT_START * RISK_PCT

# ------------------------------------------------------------- INDICATORS

def add_indicators(df):
    df = df.copy()
    df["ema_fast"]   = df["close"].ewm(span=FAST_EMA, adjust=False).mean()
    df["sma_slow"]   = df["close"].rolling(SLOW_SMA).mean()
    df["avg_volume"] = df["volume"].rolling(20).mean()
    df["swing_low"]  = df["low"].rolling(SWING_LOOKBACK).min()
    return df


def is_trigger(row, prev):
    """Pullback to the fast EMA inside an uptrend, closing back above it."""
    if any(pd.isna(x) for x in (row.sma_slow, row.ema_fast, prev.ema_fast)):
        return False
    if row.close < MIN_PRICE or row.avg_volume < MIN_AVG_VOLUME:
        return False
    uptrend  = row.close > row.sma_slow
    tagged   = row.low <= row.ema_fast          # pulled back into the EMA
    reclaim  = row.close > row.ema_fast         # and closed back above it
    rising   = row.ema_fast > prev.ema_fast     # EMA still sloping up
    return uptrend and tagged and reclaim and rising

# -------------------------------------------------------------- BACKTEST

def backtest(df, verbose=False):
    df = add_indicators(df).reset_index(drop=True)
    trades, skipped = [], []
    i, n = SLOW_SMA + 1, len(df)

    while i < n - 1:
        row, prev = df.iloc[i], df.iloc[i - 1]

        if not is_trigger(row, prev):
            i += 1
            continue

        entry_bar = df.iloc[i + 1]
        entry     = entry_bar.open                       # next open, no lookahead
        stop      = row.swing_low * (1 - STOP_BUFFER)    # structural
        risk_ps   = entry - stop

        if risk_ps <= 0:
            i += 1
            continue

        target = entry + RR * risk_ps
        shares = math.floor(RISK_DOLLARS / risk_ps)

        # the two constraints that bite a small account
        if shares < 1:
            skipped.append({"date": row.date, "reason": "stop too wide for 1R",
                            "risk_ps": round(risk_ps, 2)})
            i += 1
            continue
        if shares * entry > ACCOUNT_START:
            affordable = math.floor(ACCOUNT_START / entry)
            if affordable < 1:
                skipped.append({"date": row.date, "reason": "1 share > account",
                                "price": round(entry, 2)})
                i += 1
                continue
            shares = affordable   # under-risked, but tradeable

        # walk forward bar by bar
        outcome, exit_px, held = None, None, 0
        for j in range(i + 1, min(i + 1 + MAX_HOLD_BARS, n)):
            bar  = df.iloc[j]
            held = j - i
            hit_stop, hit_target = bar.low <= stop, bar.high >= target
            if hit_stop and hit_target:      # ambiguous bar -> assume the loss
                outcome, exit_px = "loss", stop
                break
            if hit_stop:
                outcome, exit_px = "loss", stop
                break
            if hit_target:
                outcome, exit_px = "win", target
                break
        if outcome is None:                  # time stop
            exit_px = df.iloc[min(i + MAX_HOLD_BARS, n - 1)].close
            outcome = "time"

        pnl = (exit_px - entry) * shares
        trades.append({
            "date": entry_bar.date, "entry": round(entry, 2),
            "stop": round(stop, 2), "target": round(target, 2),
            "exit": round(exit_px, 2), "shares": shares,
            "risk_ps": round(risk_ps, 2), "notional": round(shares * entry, 2),
            "pnl": round(pnl, 2), "R": round(pnl / (risk_ps * shares), 2),
            "bars_held": held, "outcome": outcome,
        })
        i += held + 1                        # no overlapping positions

    return pd.DataFrame(trades), pd.DataFrame(skipped)

# ----------------------------------------------------------------- STATS

def report(trades, skipped):
    if trades.empty:
        print("No trades generated.")
        return

    R      = trades["R"]
    wins   = R[R > 0]
    losses = R[R <= 0]
    wr     = len(wins) / len(R)
    aw     = wins.mean()   if len(wins)   else 0.0
    al     = abs(losses.mean()) if len(losses) else 0.0
    exp    = wr * aw - (1 - wr) * al

    equity = ACCOUNT_START + trades["pnl"].cumsum()
    dd     = ((equity - equity.cummax()) / equity.cummax()).min() * 100
    gp     = trades.loc[trades.pnl > 0, "pnl"].sum()
    gl     = abs(trades.loc[trades.pnl <= 0, "pnl"].sum())
    pf     = gp / gl if gl else float("inf")

    # standard error on expectancy -- is the edge real or is it noise?
    se     = R.std(ddof=1) / math.sqrt(len(R))
    lo, hi = exp - 1.96 * se, exp + 1.96 * se

    print("\n" + "=" * 58)
    print("BACKTEST RESULTS".center(58))
    print("=" * 58)
    print(f"{'Trades':<28}{len(R)}")
    print(f"{'Win rate':<28}{wr:.1%}")
    print(f"{'Avg win':<28}{aw:.2f}R")
    print(f"{'Avg loss':<28}{al:.2f}R")
    print(f"{'Expectancy':<28}{exp:+.3f}R per trade")
    print(f"{'95% CI on expectancy':<28}[{lo:+.3f}R, {hi:+.3f}R]")
    print(f"{'Profit factor':<28}{pf:.2f}")
    print(f"{'Max drawdown':<28}{dd:.1f}%")
    print(f"{'Net P&L':<28}${trades['pnl'].sum():+.2f} on ${ACCOUNT_START:.2f}")
    print(f"{'Avg notional':<28}${trades['notional'].mean():.2f} "
          f"({trades['notional'].mean()/ACCOUNT_START:.0%} of account)")
    print(f"{'Trades skipped (sizing)':<28}{len(skipped)}")

    print("\n" + "-" * 58)
    if lo > 0:
        print("Edge is positive and the CI excludes zero.")
        print("Still check: is the sample big enough, and out-of-sample?")
    elif exp > 0:
        print("Expectancy is positive but the CI includes zero.")
        print("This is NOT yet evidence of an edge. Need more trades.")
    else:
        print("Negative expectancy. Do not trade this rule set live.")
    if len(R) < 30:
        print(f"WARNING: {len(R)} trades is too few to conclude anything.")
    print("-" * 58)

    print("\nLast 10 trades:")
    cols = ["date", "entry", "stop", "exit", "shares", "R", "outcome"]
    print(trades[cols].tail(10).to_string(index=False))

# ------------------------------------------------------------------ DATA

def synthetic(n=1200, seed=7):
    """Random-walk data with mild drift. Use this to sanity-check the harness.
    A strategy that looks profitable on THIS is overfit -- there is no edge
    to find in a random walk."""
    rng = np.random.default_rng(seed)
    ret = rng.normal(0.0004, 0.018, n)
    close = 40 * np.exp(np.cumsum(ret))
    spread = close * rng.uniform(0.004, 0.022, n)
    high = close + spread * rng.uniform(0.3, 1.0, n)
    low  = close - spread * rng.uniform(0.3, 1.0, n)
    op   = np.r_[close[0], close[:-1]] + rng.normal(0, close * 0.003)
    return pd.DataFrame({
        "date": pd.bdate_range("2021-01-01", periods=n).astype(str),
        "open": op, "high": np.maximum.reduce([op, high, close]),
        "low": np.minimum.reduce([op, low, close]), "close": close,
        "volume": rng.uniform(3e6, 6e7, n),
    })


def load_csv(path):
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    need = {"date", "open", "high", "low", "close", "volume"}
    missing = need - set(df.columns)
    if missing:
        raise SystemExit(f"CSV missing columns: {sorted(missing)}")
    return df.sort_values("date").reset_index(drop=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()

    if a.demo or not a.csv:
        print("Running on SYNTHETIC data (random walk, no real edge exists).")
        data = synthetic()
    else:
        data = load_csv(a.csv)

    t, s = backtest(data)
    report(t, s)
    if not t.empty:
        t.to_csv("trades.csv", index=False)
        print("\nFull trade log -> trades.csv")

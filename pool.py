"""
Pooled multi-ticker driver for backtest.py.

Runs the unmodified strategy in backtest.py independently on each ticker,
concatenates every trade into one sample, and reports the COMBINED
expectancy. Pooling is the whole point: 3 trades on one name tells you
nothing, 200 trades across 25 uncorrelated-ish names starts to.

Three views are printed, because they answer different questions:

  1. POOLED (harness rules)   -- backtest.py exactly as written, including
                                 the $100 account sizing constraints. This
                                 is "what this account could actually take".
  2. PORTFOLIO-SEQUENTIAL     -- same trades, but one open position at a
                                 time across the WHOLE universe. The pooled
                                 equity curve in (1) silently assumes you
                                 can hold many names at once on $100; this
                                 view does not.
  3. UNCONSTRAINED EDGE       -- the same rules with the account cap lifted,
                                 so sizing cannot filter setups. This
                                 isolates the RULE SET's edge from the
                                 small-account selection effect.

Usage:
    python pool.py                 # all 25 tickers in universe.py
    python pool.py --tickers AAPL,MSFT
    python pool.py --start 2019-01-01 --end 2026-09-01
"""

import argparse
import math
import sys
from pathlib import Path

import pandas as pd

import backtest as bt
from universe import TICKERS

DATA_DIR = Path("data")

# ------------------------------------------------------------------- LOAD

def load(ticker, start=None, end=None):
    """Read data/<TICKER>.csv and clip to the window. Returns None if absent."""
    path = DATA_DIR / f"{ticker}.csv"
    if not path.exists():
        return None
    df = bt.load_csv(path)
    if start:
        df = df[df["date"] >= start]
    if end:
        df = df[df["date"] <= end]
    return df.reset_index(drop=True)


def exit_dates(df, trades):
    """Attach the exit bar's date to each trade.

    backtest.py records the ENTRY bar's date and how many bars were held.
    Entry is bar i+1 and exit is bar i+held, so exit sits held-1 bars after
    entry. We need this to enforce one-position-at-a-time across tickers.
    """
    idx = {d: k for k, d in enumerate(df["date"])}
    out = []
    for _, t in trades.iterrows():
        k = idx[t["date"]] + int(t["bars_held"]) - 1
        out.append(df["date"].iloc[min(k, len(df) - 1)])
    return out

# --------------------------------------------------------------- RUN LOOP

def run_universe(tickers, start, end, unconstrained=False):
    """Backtest each ticker separately, then concatenate the trade logs."""
    if unconstrained:
        # Lift the account cap so sizing cannot reject a setup. R-multiples
        # are unaffected by share count -- only WHICH setups survive changes.
        saved = (bt.ACCOUNT_START, bt.RISK_DOLLARS)
        bt.ACCOUNT_START = 1e12
        bt.RISK_DOLLARS = 1e12

    all_trades, all_skipped, missing, per_ticker = [], [], [], []
    try:
        for tk in tickers:
            df = load(tk, start, end)
            if df is None or len(df) < bt.SLOW_SMA + 5:
                missing.append(tk)
                continue
            trades, skipped = bt.backtest(df)
            if not trades.empty:
                trades = trades.copy()
                trades.insert(0, "ticker", tk)
                trades["exit_date"] = exit_dates(df, trades)
                all_trades.append(trades)
            if not skipped.empty:
                skipped = skipped.copy()
                skipped.insert(0, "ticker", tk)
                all_skipped.append(skipped)
            per_ticker.append({
                "ticker": tk, "bars": len(df),
                "trades": len(trades), "skipped": len(skipped),
                "expectancy": round(trades["R"].mean(), 3) if len(trades) else float("nan"),
                "net_pnl": round(trades["pnl"].sum(), 2) if len(trades) else 0.0,
            })
    finally:
        if unconstrained:
            bt.ACCOUNT_START, bt.RISK_DOLLARS = saved

    pooled = (pd.concat(all_trades, ignore_index=True)
              if all_trades else pd.DataFrame())
    if not pooled.empty:
        pooled = pooled.sort_values(["date", "ticker"]).reset_index(drop=True)
    skipped = (pd.concat(all_skipped, ignore_index=True)
               if all_skipped else pd.DataFrame())
    return pooled, skipped, pd.DataFrame(per_ticker), missing

# ----------------------------------------------------------------- VIEWS

def sequential(pooled):
    """Keep only trades takeable one-at-a-time across the whole universe.

    First come, first served: once a position opens, every setup that
    triggers before it exits is passed on. This is the honest single-account
    path -- the pooled equity curve is not.
    """
    kept, free_from = [], ""
    for _, t in pooled.iterrows():
        if t["date"] >= free_from:
            kept.append(t)
            free_from = t["exit_date"]
    return pd.DataFrame(kept).reset_index(drop=True)


def expectancy_block(label, trades):
    """Expectancy in R with a 95% CI -- the only number that pools cleanly."""
    if trades.empty:
        print(f"\n{label}: no trades.")
        return
    R  = trades["R"]
    wr = (R > 0).mean()
    aw = R[R > 0].mean() if (R > 0).any() else 0.0
    al = abs(R[R <= 0].mean()) if (R <= 0).any() else 0.0
    exp = R.mean()
    se  = R.std(ddof=1) / math.sqrt(len(R))
    lo, hi = exp - 1.96 * se, exp + 1.96 * se

    equity = bt.ACCOUNT_START + trades["pnl"].cumsum()
    dd = ((equity - equity.cummax()) / equity.cummax()).min() * 100
    gp = trades.loc[trades.pnl > 0, "pnl"].sum()
    gl = abs(trades.loc[trades.pnl <= 0, "pnl"].sum())

    print(f"\n{label}")
    print("-" * 58)
    print(f"{'Trades':<28}{len(R)}")
    print(f"{'Win rate':<28}{wr:.1%}")
    print(f"{'Avg win':<28}{aw:.2f}R")
    print(f"{'Avg loss':<28}{al:.2f}R")
    print(f"{'COMBINED EXPECTANCY':<28}{exp:+.3f}R per trade")
    print(f"{'95% CI':<28}[{lo:+.3f}R, {hi:+.3f}R]")
    print(f"{'Profit factor':<28}{(gp / gl) if gl else float('inf'):.2f}")
    print(f"{'Max drawdown':<28}{dd:.1f}%")
    print(f"{'Net P&L':<28}${trades['pnl'].sum():+.2f}")
    verdict = ("edge positive, CI excludes zero" if lo > 0
               else "positive but CI includes zero -- not yet evidence"
               if exp > 0 else "NEGATIVE expectancy")
    print(f"{'Verdict':<28}{verdict}")
    if len(R) < 30:
        print(f"WARNING: {len(R)} trades is too few to conclude anything.")

# ------------------------------------------------------------------ MAIN

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", help="comma-separated; default = universe.py")
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default=None)
    a = ap.parse_args()

    tickers = a.tickers.split(",") if a.tickers else TICKERS

    pooled, skipped, per_ticker, missing = run_universe(
        tickers, a.start, a.end)

    if missing:
        print(f"No data for {len(missing)} ticker(s): {', '.join(missing)}",
              file=sys.stderr)
    if pooled.empty:
        raise SystemExit("No trades generated across the universe.")

    span = f"{pooled['date'].min()} -> {pooled['date'].max()}"
    print("=" * 58)
    print(f"POOLED BACKTEST  |  {len(tickers) - len(missing)} tickers  |  {span}".center(58))
    print("=" * 58)

    print("\nPer-ticker:")
    print(per_ticker.to_string(index=False))

    expectancy_block(
        "1. POOLED, HARNESS RULES ($%.0f account, 1R = $%.2f)"
        % (bt.ACCOUNT_START, bt.RISK_DOLLARS), pooled)
    print(f"{'Setups skipped (sizing)':<28}{len(skipped)}")

    expectancy_block("2. PORTFOLIO-SEQUENTIAL (one open position at a time)",
                     sequential(pooled))

    unc, _, unc_per_ticker, _ = run_universe(
        tickers, a.start, a.end, unconstrained=True)
    expectancy_block("3. UNCONSTRAINED EDGE (account cap lifted)", unc)

    pooled.to_csv("pooled_trades.csv", index=False)
    per_ticker.to_csv("per_ticker.csv", index=False)
    print("\nPooled trade log -> pooled_trades.csv, per-ticker -> per_ticker.csv")

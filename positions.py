"""
Exit management for open positions -- the sell side of backtest.py.

The strategy already answers "when do I sell". It is not discretionary, and
there are exactly three ways out, checked against each new daily bar in this
order:

  1. STOP    bar's low  <= stop            -> out at the stop
  2. TARGET  bar's high >= target          -> out at the target
  3. TIME    20 bars held, neither hit     -> out at that bar's close

The order matters. If a single bar's range spans BOTH the stop and the
target, backtest.py counts it a LOSS, because daily bars do not tell you
which came first intrabar. This module keeps that same conservative rule, so
live exits match what the backtest measured -- resolving ambiguous bars the
optimistic way is exactly how a backtest drifts away from reality.

    python positions.py                       # list open positions
    python positions.py --open KO 1 88.67 87.70 90.60 2026-09-02
    python positions.py --check KO 89.10 88.20 88.90    # high low close
    python positions.py --close KO
"""

import json
import sys
from pathlib import Path

MAX_HOLD_BARS = 20
STORE = Path("positions.json")


def load():
    return json.loads(STORE.read_text()) if STORE.exists() else []


def save(positions):
    STORE.write_text(json.dumps(positions, indent=2) + "\n")


def decide(pos, high, low, close):
    """Return (action, exit_price, reason) for one new daily bar."""
    hit_stop = low <= pos["stop"]
    hit_target = high >= pos["target"]

    if hit_stop and hit_target:
        return ("SELL", pos["stop"],
                "bar spanned stop and target -- counted a loss, since daily "
                "bars cannot tell you which was touched first")
    if hit_stop:
        return "SELL", pos["stop"], "stop hit"
    if hit_target:
        return "SELL", pos["target"], "target hit"
    if pos["bars_held"] + 1 >= MAX_HOLD_BARS:
        return "SELL", close, f"time stop -- {MAX_HOLD_BARS} bars held"
    return "HOLD", None, f"bar {pos['bars_held'] + 1} of {MAX_HOLD_BARS}"


def report(pos, action, price, reason):
    r = ((price - pos["entry"]) / (pos["entry"] - pos["stop"])
         if price is not None else None)
    head = f"{pos['ticker']:5s} {action}"
    if action == "SELL":
        pnl = (price - pos["entry"]) * pos["shares"]
        print(f"{head}  {pos['shares']} share(s) @ {price:.2f}   "
              f"P&L ${pnl:+.2f}  ({r:+.2f}R)")
    else:
        print(f"{head}  entry {pos['entry']:.2f}  stop {pos['stop']:.2f}  "
              f"target {pos['target']:.2f}")
    print(f"      {reason}")


if __name__ == "__main__":
    a = sys.argv[1:]
    positions = load()

    if not a:
        if not positions:
            print("No open positions.")
        for p in positions:
            print(f"{p['ticker']:5s} {p['shares']} share(s)  entry {p['entry']:.2f} "
                  f"on {p['entry_date']}  stop {p['stop']:.2f}  "
                  f"target {p['target']:.2f}  held {p['bars_held']} bars")

    elif a[0] == "--open":
        tk, shares, entry, stop, target, date = a[1:7]
        positions.append({"ticker": tk, "shares": int(shares),
                          "entry": float(entry), "stop": float(stop),
                          "target": float(target), "entry_date": date,
                          "bars_held": 0})
        save(positions)
        print(f"opened {tk}: {shares} share(s) @ {entry}, "
              f"stop {stop}, target {target}")

    elif a[0] == "--check":
        tk, high, low, close = a[1], float(a[2]), float(a[3]), float(a[4])
        for p in positions:
            if p["ticker"] == tk:
                action, price, reason = decide(p, high, low, close)
                report(p, action, price, reason)
                if action == "HOLD":
                    p["bars_held"] += 1
                    save(positions)
                else:
                    print(f"      -> remove with: python positions.py --close {tk}")
                break
        else:
            print(f"no open position in {tk}")

    elif a[0] == "--close":
        save([p for p in positions if p["ticker"] != a[1]])
        print(f"closed {a[1]}")

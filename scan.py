"""
Evaluate today's setups against the live tape, with the $100 sizing gates.

There is no market-data host reachable from this sandbox, so the inputs are
the values read from the broker connector for the last SETTLED session. The
2026-09-01 daily bars were all interpolated=true with zero volume -- an
unsettled placeholder, not a session -- so the trigger bar is 2026-08-31.

This scans; it does not trade. Entry per the rules is the next open AFTER
the trigger bar, so a signal listed here was actionable at the 2026-09-01
open, which has already passed.
"""

import math

ACCOUNT = 100.00
RR = 2.0
STOP_BUFFER = 0.002

# ticker: (open, high, low, close, ema20, ema20_prev, sma50, swing_low_10)
BARS_2026_08_31 = {
    "T":    (25.915, 26.240, 25.860, 25.890, 24.92205, 24.82016, None,     None),
    "PFE":  (27.850, 28.700, 27.640, 28.460, 27.31177, 27.19090, 25.63560, 27.100),
    "BAC":  (62.250, 62.490, 61.900, 61.940, 62.41391, 62.46380, None,     None),
    "NFLX": (81.000, 81.730, 80.650, 81.050, 78.37805, 78.09680, None,     None),
    "WFC":  (86.290, 87.090, 85.880, 86.390, 86.14123, 86.11505, 86.27980, 83.480),
    "KO":   (89.505, 89.530, 88.600, 88.670, 88.62095, 88.61579, 85.42060, 87.880),
    "INTC": (90.000, 91.850, 88.970, 89.510, 93.94614, 94.41311, None,     None),
}


def triggers(o, h, l, c, ema, ema_prev, sma):
    """backtest.py is_trigger(), evaluated on one bar."""
    if sma is None:
        sma = float("inf")          # not fetched: only when an earlier gate failed
    return {
        "uptrend  close>sma50": c > sma,
        "tagged   low<=ema20":  l <= ema,
        "reclaim  close>ema20": c > ema,
        "rising   ema>ema_prev": ema > ema_prev,
    }


def size(entry, swing_low, risk_pct):
    """The two sizing gates from backtest.py, in order."""
    risk_dollars = ACCOUNT * risk_pct
    stop = swing_low * (1 - STOP_BUFFER)
    risk_ps = entry - stop
    shares = math.floor(risk_dollars / risk_ps)
    gate = "risk gate: stop too wide for 1R" if shares < 1 else None
    if shares >= 1 and shares * entry > ACCOUNT:
        shares = math.floor(ACCOUNT / entry)
        gate = "capped by affordability"
        if shares < 1:
            gate = "affordability gate: 1 share > account"
    return stop, risk_ps, shares, gate


if __name__ == "__main__":
    print("Trigger bar 2026-08-31 (2026-09-01 bars were interpolated)\n")
    fired = []
    for tk, (o, h, l, c, ema, ema_prev, sma, swing) in BARS_2026_08_31.items():
        conds = triggers(o, h, l, c, ema, ema_prev, sma)
        ok = all(conds.values())
        print(f"{tk:5s} close {c:8.2f}  ema20 {ema:8.4f}  "
              f"{'SETUP' if ok else 'no'}")
        if not ok:
            failed = [k for k, v in conds.items() if not v]
            print(f"      fails: {', '.join(failed)}")
        else:
            fired.append((tk, c, swing))

    print(f"\n{len(fired)} setup(s): {', '.join(t for t, _, _ in fired)}")
    for pct, label in ((0.01, "as written (RISK_PCT=1%)"),
                       (0.04, "raised (RISK_PCT=4%)")):
        print(f"\n--- sizing {label}, 1R = ${ACCOUNT*pct:.2f} ---")
        for tk, entry, swing in fired:
            stop, risk_ps, shares, gate = size(entry, swing, pct)
            target = entry + RR * risk_ps
            if shares < 1:
                print(f"{tk:5s} SKIPPED  ({gate}; stop ${risk_ps:.2f} away)")
            else:
                print(f"{tk:5s} {shares} share  entry ~{entry:.2f}  "
                      f"stop {stop:.2f}  target {target:.2f}  "
                      f"risk ${shares*risk_ps:.2f} "
                      f"({shares*risk_ps/ACCOUNT:.1%} of account)"
                      + (f"  [{gate}]" if gate else ""))

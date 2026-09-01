"""
What a $100 account can actually trade in this universe.

backtest.py has two sizing gates. On a $100 account the second one is the
binding constraint, and it is not a tuning parameter -- you cannot buy a
fraction of a share:

    shares = floor(RISK_DOLLARS / risk_per_share)     # risk gate
    if shares * entry > ACCOUNT_START:                # affordability gate
        shares = floor(ACCOUNT_START / entry)

With RISK_PCT = 1%, 1R = $1.00, so the risk gate alone rejects any setup
whose structural stop is more than $1.00 away -- which on a $300 stock is
essentially all of them. Raising RISK_PCT removes that gate, but then the
affordability gate takes over: at $100 you own floor(100/price) shares and
your dollar risk is whatever the chart hands you.

Prices are last trade on 2026-09-01 from the broker connector.
"""

import pandas as pd

PRICES = {  # 2026-09-01 last trade
    "AAPL": 325.14, "MSFT": 501.15, "AMZN": 254.92, "GOOGL": 335.02,
    "META": 578.53, "NFLX": 80.80, "DIS": 106.23, "NVDA": 217.54,
    "AMD": 459.75, "INTC": 88.97, "MU": 933.24, "QCOM": 166.63,
    "CSCO": 109.74, "TSLA": 356.12, "BA": 205.72, "JPM": 354.98,
    "BAC": 62.02, "WFC": 87.05, "C": 132.52, "XOM": 164.56,
    "CVX": 211.05, "PFE": 28.57, "KO": 88.01, "WMT": 105.94, "T": 26.02,
}

ACCOUNT = 100.00
# a swing stop under a 10-bar low sits roughly 3-6% away on a large cap;
# 4% is a fair central estimate for translating price into dollar risk
TYPICAL_STOP_PCT = 0.04


def table():
    rows = []
    for tk, px in sorted(PRICES.items(), key=lambda kv: kv[1]):
        shares = int(ACCOUNT // px)
        stop_dist = px * TYPICAL_STOP_PCT
        rows.append({
            "ticker": tk,
            "price": px,
            "shares_affordable": shares,
            "notional": round(shares * px, 2),
            "stop_$": round(stop_dist, 2),
            "risk_$": round(shares * stop_dist, 2),
            "risk_%acct": round(shares * stop_dist / ACCOUNT * 100, 1),
            "1R_gate_1pct": "pass" if stop_dist <= ACCOUNT * 0.01 else "REJECT",
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = table()
    print(f"$100 account, prices 2026-09-01, assumed stop {TYPICAL_STOP_PCT:.0%} away\n")
    print(df.to_string(index=False))

    tradeable = df[df.shares_affordable >= 1]
    print(f"\nAffordable at 1+ share : {len(tradeable)} of {len(df)}")
    print(f"  {', '.join(tradeable.ticker)}")
    print(f"Unaffordable           : {len(df) - len(tradeable)} of {len(df)}")
    passes = df[df["1R_gate_1pct"] == "pass"]
    print(f"\nPass the 1%-risk gate (stop <= $1.00): {len(passes)} of {len(df)}"
          f"{' -- ' + ', '.join(passes.ticker) if len(passes) else ''}")
    print(f"\nMedian risk per trade on the affordable names: "
          f"{tradeable['risk_%acct'].median():.1f}% of the account")

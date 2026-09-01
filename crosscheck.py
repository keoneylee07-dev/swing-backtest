"""
Cross-check transcribed daily bars against the connector's MONTHLY bars.

A monthly bar is a pure function of that month's daily bars:
    open   = first day's open      high = max of daily highs
    close  = last day's close      low  = min of daily lows
    volume = sum of daily volumes

So re-aggregating data/<TICKER>.csv to months and comparing against the
connector's own monthly series catches transcription damage that the
structural validator cannot: a mistyped digit shifts the month's high, low,
or -- for any volume error at all -- the month's volume sum.

Usage: python crosscheck.py AAPL monthly/AAPL.txt
where the monthly file is one line per month: yyyy-mm,open,close,high,low,volume
"""

import sys
import pandas as pd

TOL = 1e-6


def check(ticker, monthly_path):
    df = pd.read_csv(f"data/{ticker}.csv")
    df["ym"] = df["date"].str.slice(0, 7)
    agg = df.groupby("ym").agg(
        open=("open", "first"), close=("close", "last"),
        high=("high", "max"), low=("low", "min"), volume=("volume", "sum"))

    bad = []
    n = 0
    for line in open(monthly_path):
        line = line.strip()
        if not line:
            continue
        ym, o, c, h, l, v = line.split(",")
        if ym not in agg.index:
            bad.append(f"{ym}: no daily bars transcribed")
            continue
        r = agg.loc[ym]
        n += 1
        for name, want, got in (("open", float(o), r["open"]),
                                ("close", float(c), r["close"]),
                                ("high", float(h), r["high"]),
                                ("low", float(l), r["low"]),
                                ("volume", int(v), int(r["volume"]))):
            if abs(want - got) > (TOL if name != "volume" else 0):
                bad.append(f"{ym} {name}: connector={want} transcribed={got}")
    return n, bad


if __name__ == "__main__":
    tk, path = sys.argv[1], sys.argv[2]
    n, bad = check(tk, path)
    if bad:
        print(f"{tk}: {len(bad)} MISMATCH(ES) across {n} months")
        for b in bad:
            print("   ", b)
        raise SystemExit(1)
    print(f"{tk}: all {n} months reconcile exactly (O/H/L/C and volume sum)")

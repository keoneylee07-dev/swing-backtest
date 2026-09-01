"""
Alternative data fetcher: Stooq instead of Yahoo.

Stooq is the simpler allowlist target -- ONE hostname, plain CSV over HTTPS,
no API key and no cookie/crumb handshake. yfinance by contrast reaches
fc.yahoo.com and guce.yahoo.com for cookies before it can call
query1/query2.finance.yahoo.com, so the Yahoo route needs four hosts
permitted rather than one.

    https://stooq.com/q/d/l/?s=aapl.us&i=d   ->  Date,Open,High,Low,Close,Volume

Untested against the live host: Stooq is still blocked from this sandbox, so
this is written defensively and validated on first successful run.
"""

import sys
import time
from pathlib import Path

import pandas as pd

from universe import TICKERS

START = "2019-01-01"
OUT = Path("data")
URL = "https://stooq.com/q/d/l/?s={sym}.us&i=d"


def fetch(tickers, start=START):
    OUT.mkdir(exist_ok=True)
    ok, failed = [], []
    for tk in tickers:
        for attempt in range(4):
            try:
                df = pd.read_csv(URL.format(sym=tk.lower()))
                # Stooq answers with a one-line body on a bad symbol or a
                # rate limit, so check shape before trusting the response.
                need = {"Date", "Open", "High", "Low", "Close", "Volume"}
                if not need.issubset(df.columns) or df.empty:
                    raise RuntimeError(f"unexpected body: {list(df.columns)[:6]}")
                df = df.rename(columns=str.lower)
                df["date"] = df["date"].astype(str)
                df = df[df["date"] >= start]
                df = df[["date", "open", "high", "low", "close", "volume"]]
                df = df.sort_values("date").reset_index(drop=True)
                if df.empty:
                    raise RuntimeError(f"no rows on or after {start}")
                df.to_csv(OUT / f"{tk}.csv", index=False)
                print(f"{tk:6s} {len(df):5d} bars  "
                      f"{df.date.iloc[0]} -> {df.date.iloc[-1]}")
                ok.append(tk)
                break
            except Exception as e:                       # noqa: BLE001
                if attempt == 3:
                    print(f"{tk:6s} FAILED: {e}", file=sys.stderr)
                    failed.append(tk)
                else:
                    time.sleep(2 ** (attempt + 1))
    return ok, failed


if __name__ == "__main__":
    ok, failed = fetch(sys.argv[1:] or TICKERS)
    print(f"\n{len(ok)} fetched, {len(failed)} failed")
    if failed:
        print("failed:", ", ".join(failed))

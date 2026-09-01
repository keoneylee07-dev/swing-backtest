"""
Fetch daily OHLCV for the universe into data/<TICKER>.csv.

Run this anywhere Yahoo is reachable; then `python pool.py` needs no network.
In the Claude Code remote sandbox this fails by design -- the egress policy
denies every market-data host -- so the CSVs are fetched elsewhere and
committed, or transcribed from a broker connector.

    pip install yfinance
    python fetch_data.py
    python pool.py
"""

import sys
import time
from pathlib import Path

from universe import TICKERS

START = "2019-01-01"
OUT = Path("data")


def fetch(tickers, start=START, end=None):
    try:
        import yfinance as yf
    except ImportError:
        raise SystemExit("pip install yfinance")

    OUT.mkdir(exist_ok=True)
    ok, failed = [], []
    for tk in tickers:
        for attempt in range(4):
            try:
                # auto_adjust=False keeps raw OHLC; we split-adjust only,
                # because dividend-adjusting daily bars distorts the exact
                # highs and lows the stop/target logic keys off.
                df = yf.download(tk, start=start, end=end, progress=False,
                                 auto_adjust=False, actions=False)
                if df.empty:
                    raise RuntimeError("empty frame")
                if hasattr(df.columns, "levels"):      # yfinance MultiIndex
                    df.columns = df.columns.get_level_values(0)
                df = df.rename(columns=str.lower).reset_index()
                df["date"] = df["Date"].dt.strftime("%Y-%m-%d")
                df = df[["date", "open", "high", "low", "close", "volume"]]
                df.to_csv(OUT / f"{tk}.csv", index=False)
                print(f"{tk:6s} {len(df):5d} bars  "
                      f"{df.date.iloc[0]} -> {df.date.iloc[-1]}")
                ok.append(tk)
                break
            except Exception as e:                     # noqa: BLE001
                if attempt == 3:
                    print(f"{tk:6s} FAILED: {e}", file=sys.stderr)
                    failed.append(tk)
                else:
                    time.sleep(2 ** (attempt + 1))     # 2s, 4s, 8s
    return ok, failed


if __name__ == "__main__":
    ok, failed = fetch(sys.argv[1:] or TICKERS)
    print(f"\n{len(ok)} fetched, {len(failed)} failed")
    if failed:
        print("failed:", ", ".join(failed))

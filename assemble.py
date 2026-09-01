"""
Assemble per-ticker CSVs from connector bars.

Bars come out of the Robinhood connector as tool results, so they are
transcribed by hand. Two things keep that honest:

  * the trading calendar is written ONCE (raw/calendar.txt) and shared by
    every ticker, so only the 5 numeric columns are retyped per name;
  * validate() re-derives what the data must satisfy and refuses to build a
    CSV that fails, so a fat-fingered digit surfaces here and not silently
    inside an expectancy number.

raw/<TICKER>.txt is one line per bar: open,close,high,low,volume --
deliberately the SAME field order the connector emits, so transcription is a
straight copy and never a mental reorder. build() does the reordering.
"""

import sys
from pathlib import Path
import pandas as pd

RAW = Path("raw")
OUT = Path("data")


def calendar():
    return [d.strip() for d in (RAW / "calendar.txt").read_text().split() if d.strip()]


def validate(tk, df):
    """Every OHLC bar must satisfy these. A transcription slip breaks one."""
    errs = []
    if df["high"].lt(df[["open", "close"]].max(axis=1) - 1e-9).any():
        errs.append("high below open/close")
    if df["low"].gt(df[["open", "close"]].min(axis=1) + 1e-9).any():
        errs.append("low above open/close")
    if df["high"].lt(df["low"]).any():
        errs.append("high below low")
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        errs.append("non-positive price")
    if (df["volume"] <= 0).any():
        errs.append("non-positive volume")
    if df["date"].duplicated().any():
        errs.append("duplicate dates")
    if not df["date"].is_monotonic_increasing:
        errs.append("dates out of order")
    # a >40% single-bar move in a mega cap is a typo, not a market event
    jump = (df["close"].pct_change().abs() > 0.40)
    if jump.any():
        errs.append(f"implausible close jump on {list(df.loc[jump,'date'])[:3]}")
    return errs


def build(tk):
    dates = calendar()
    rows = [l for l in (RAW / f"{tk}.txt").read_text().splitlines() if l.strip()]
    if len(rows) != len(dates):
        raise SystemExit(
            f"{tk}: {len(rows)} bars but calendar has {len(dates)}. "
            "This ticker does not share the common calendar -- transcribe "
            "its own dates instead of aligning it.")
    recs = []
    for d, line in zip(dates, rows):
        o, c, h, l, v = line.split(",")
        recs.append({"date": d, "open": float(o), "high": float(h),
                     "low": float(l), "close": float(c), "volume": int(v)})
    df = pd.DataFrame(recs)
    errs = validate(tk, df)
    if errs:
        raise SystemExit(f"{tk} FAILED validation: {errs}")
    OUT.mkdir(exist_ok=True)
    df.to_csv(OUT / f"{tk}.csv", index=False)
    return df


if __name__ == "__main__":
    for tk in sys.argv[1:]:
        df = build(tk)
        print(f"{tk:6s} {len(df)} bars  {df.date.iloc[0]} -> {df.date.iloc[-1]}  "
              f"close {df.close.iloc[0]:.2f} -> {df.close.iloc[-1]:.2f}  OK")

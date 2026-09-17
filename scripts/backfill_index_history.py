"""
Backfill authentic historical daily index bars.

Strategies 1 and 2 (NiftyWeeklyIronCondorStrategy, CurvatureCreditSpreadStrategy)
declare min_data_points = 200. The local index history began at 2026-01-01 and
held ~174 bars, so those strategies could never evaluate and always failed
closed. This script extends the history BACKWARDS using the same Yahoo Finance
source and the same schema as scripts/download_real_2026.py.

Safety properties:
  * Backward-only. Bars are fetched strictly BEFORE the earliest existing row,
    so no future information can enter the file and no lookahead is possible.
  * Never fabricated. Every row comes from the market-data feed; missing data
    is dropped, never interpolated, filled or synthesised.
  * Non-destructive. Existing rows win on any date collision; the script only
    prepends dates that are not already present.

Usage:
    python scripts/backfill_index_history.py [--start 2025-01-01]
"""

import argparse
import os
import sys

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

INDEX_FILES = {
    "INDEX_NIFTY50": ("^NSEI", "data/real_2026/INDEX_NIFTY50_daily.csv"),
    "INDEX_BANKNIFTY": ("^NSEBANK", "data/real_2026/INDEX_BANKNIFTY_daily.csv"),
    "INDEX_INDIAVIX": ("^INDIAVIX", "data/real_2026/INDEX_INDIAVIX_daily.csv"),
}
COLUMNS = ["datetime", "open", "high", "low", "close", "volume"]
NEWLINE = chr(10)


def fetch_history(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Fetches authentic daily bars. Returns an empty frame on any failure."""
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=False)
    if df is None or df.empty:
        return pd.DataFrame(columns=COLUMNS)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [str(c).lower() for c in df.columns]

    df = df.reset_index()
    for src in ("Date", "date", "index"):
        if src in df.columns:
            df = df.rename(columns={src: "datetime"})
            break

    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        print(f"    [!] Missing columns {missing}; refusing to write partial data.")
        return pd.DataFrame(columns=COLUMNS)

    df["datetime"] = pd.to_datetime(df["datetime"]).dt.strftime("%Y-%m-%d")
    df = df[COLUMNS].dropna(subset=["open", "high", "low", "close"])
    return df.sort_values("datetime").reset_index(drop=True)


def backfill(name: str, ticker: str, path: str, start: str) -> int:
    if not os.path.exists(path):
        print(f"[!] {path} does not exist; skipping (this script only extends existing history).")
        return 0

    existing = pd.read_csv(path)
    existing["datetime"] = pd.to_datetime(existing["datetime"]).dt.strftime("%Y-%m-%d")
    earliest = existing["datetime"].min()
    before = len(existing)

    print(f"\n[+] {name} ({ticker}) — {before} bars, earliest {earliest}")
    if start >= earliest:
        print(f"    Nothing to do: --start {start} is not before {earliest}.")
        return 0

    # Backward-only window: strictly earlier than what we already hold.
    fetched = fetch_history(ticker, start=start, end=earliest)
    if fetched.empty:
        print("    [!] No authentic bars returned; leaving file unchanged (fail closed).")
        return 0

    fetched = fetched[fetched["datetime"] < earliest]
    if fetched.empty:
        print("    [!] Feed returned nothing strictly earlier than existing history.")
        return 0

    # Byte-exact prepend: the existing file's lines are copied verbatim so that
    # not one stored value is rewritten (a CSV float round-trip would otherwise
    # perturb the last bit of every existing row). Only genuinely new, strictly
    # earlier rows are added ahead of them.
    with open(path, "r", encoding="utf-8") as fh:
        original_lines = fh.read().splitlines()
    header, original_rows = original_lines[0], original_lines[1:]

    existing_dates = {row.split(",", 1)[0] for row in original_rows if row.strip()}
    new_rows = [
        ",".join([
            r["datetime"], repr(float(r["open"])), repr(float(r["high"])),
            repr(float(r["low"])), repr(float(r["close"])), str(int(float(r["volume"]))),
        ])
        for _, r in fetched.iterrows()
        if r["datetime"] not in existing_dates
    ]
    if not new_rows:
        print("    [!] No genuinely new dates to add.")
        return 0

    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(NEWLINE.join([header] + new_rows + original_rows) + NEWLINE)

    added = len(new_rows)
    print(f"    Added {added} authentic bars -> {before + added} total "
          f"({new_rows[0].split(',')[0]} -> {original_rows[-1].split(',')[0]})")
    return added


def main():
    parser = argparse.ArgumentParser(description="Backfill authentic index daily history")
    parser.add_argument("--start", default="2025-01-01", help="Earliest date to backfill from")
    args = parser.parse_args()

    print("=" * 72)
    print(f"BACKFILLING AUTHENTIC INDEX HISTORY FROM {args.start} (backward-only)")
    print("=" * 72)

    total = 0
    for name, (ticker, path) in INDEX_FILES.items():
        total += backfill(name, ticker, path, args.start)

    print(f"\nDone. {total} authentic bars added across {len(INDEX_FILES)} indices.")
    print("No synthetic bars were written. No future data was introduced.")


if __name__ == "__main__":
    main()

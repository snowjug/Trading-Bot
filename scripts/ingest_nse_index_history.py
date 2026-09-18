"""
Ingest NIFTY 50 and India VIX daily OHLC from NSE's public index archive.

WHY: the repository's index history starts 2025-01-01, which caps Bot 1 at roughly
85 weekly cycles — too few to say anything about a structure whose loss is ~17x its
credit. NSE publishes `ind_close_all_DDMMYYYY.csv` free and unauthenticated with
full OHLC for every index including India VIX, and it reaches back to at least
2024-01-02. Extending the underlying history is the only way to enlarge the sample
without touching the strategy.

This is a read-only HTTP GET against a public exchange archive. It derives nothing
and fabricates nothing: a session the exchange does not publish stays absent.

INTEGRITY: `verify_against_repo()` cross-checks the overlapping window against the
existing INDEX_*.csv files. A mismatch is reported, never silently reconciled.
"""

import argparse
import io
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

ARCHIVE = "https://nsearchives.nseindia.com/content/indices/ind_close_all_{d}.csv"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/",
}
OUT = Path("data/raw/nse/index_history")
WANTED = {"Nifty 50": "NIFTY50", "India VIX": "INDIAVIX"}


def fetch_day(d: date, timeout: int = 40):
    """Returns a list of row dicts for the wanted indices, or None if unpublished."""
    try:
        r = requests.get(ARCHIVE.format(d=d.strftime("%d%m%Y")), headers=HEADERS, timeout=timeout)
    except Exception:                                          # noqa: BLE001
        return None
    if r.status_code != 200 or len(r.content) < 500:
        return None                                            # holiday / weekend / absent
    try:
        df = pd.read_csv(io.StringIO(r.text))
    except Exception:                                          # noqa: BLE001
        return None
    df.columns = [c.strip() for c in df.columns]
    rows = []
    for nse_name, tag in WANTED.items():
        m = df[df["Index Name"].astype(str).str.strip() == nse_name]
        if m.empty:
            continue
        x = m.iloc[0]
        try:
            rows.append({
                "symbol": tag, "datetime": pd.Timestamp(d),
                "open": float(x["Open Index Value"]), "high": float(x["High Index Value"]),
                "low": float(x["Low Index Value"]), "close": float(x["Closing Index Value"]),
            })
        except (TypeError, ValueError):
            continue                                           # unparseable row is dropped, not guessed
    return rows or None


def verify_against_repo(df: pd.DataFrame) -> dict:
    """Cross-check the overlap with the repository's existing history."""
    report = {}
    for tag, path in [("NIFTY50", "data/real_2026/INDEX_NIFTY50_daily.csv"),
                      ("INDIAVIX", "data/real_2026/INDEX_INDIAVIX_daily.csv")]:
        if not Path(path).exists():
            report[tag] = "repo file absent"
            continue
        old = pd.read_csv(path)
        old["datetime"] = pd.to_datetime(old["datetime"])
        new = df[df["symbol"] == tag][["datetime", "close"]]
        j = old[["datetime", "close"]].merge(new, on="datetime", suffixes=("_repo", "_nse"))
        if j.empty:
            report[tag] = "no overlap"
            continue
        diff = (j["close_repo"] - j["close_nse"]).abs()
        rel = diff / j["close_repo"].abs()
        report[tag] = {
            "overlap_sessions": int(len(j)),
            "max_abs_diff": round(float(diff.max()), 4),
            "max_rel_diff_pct": round(float(rel.max() * 100), 5),
            "sessions_over_0.1pct": int((rel > 0.001).sum()),
        }
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2026-09-16")
    ap.add_argument("--sleep", type=float, default=0.25)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / "nse_index_daily.parquet"
    have = pd.read_parquet(cache) if cache.exists() else pd.DataFrame()
    known = set(pd.to_datetime(have["datetime"]).dt.date) if len(have) else set()

    d0 = pd.Timestamp(args.start).date()
    d1 = pd.Timestamp(args.end).date()
    rows, n_fetch, day = [], 0, d0
    while day <= d1:
        if day.weekday() < 5 and day not in known:
            got = fetch_day(day)
            n_fetch += 1
            if got:
                rows.extend(got)
            if n_fetch % 50 == 0:
                print(f"  ...{day} fetched={n_fetch} rows={len(rows)}", flush=True)
            time.sleep(args.sleep)
        day += timedelta(days=1)

    if rows:
        have = pd.concat([have, pd.DataFrame(rows)], ignore_index=True)
    if have.empty:
        print("NOTHING INGESTED")
        return 1
    have["datetime"] = pd.to_datetime(have["datetime"])
    have = (have.drop_duplicates(subset=["symbol", "datetime"])
                .sort_values(["symbol", "datetime"]).reset_index(drop=True))
    have.to_parquet(cache, index=False)

    for tag in WANTED.values():
        s = have[have["symbol"] == tag]
        print(f"{tag}: {len(s)} sessions {s['datetime'].min().date()} .. {s['datetime'].max().date()}")
    print("\nINTEGRITY vs repo history:")
    for k, v in verify_against_repo(have).items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Ingest continuous 5-minute rolling option bars for top 5 liquid Indian F&O stocks:
SBIN, RELIANCE, HDFCBANK, TCS, INFY from DhanHQ /charts/rollingoption.

Stock options in India are monthly contracts, traded under instrument="OPTSTK"
and exchangeSegment="NSE_FNO".
"""

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from src.config import Config

OUT_ROOT = Path("data/raw/dhan/option_grid_5m_stocks")
DERIVED_DIR = Path("data/derived")

# Top 5 most liquid F&O stocks in India with official Dhan NSE security IDs
STOCKS: Dict[str, str] = {
    "SBIN": "3045",
    "RELIANCE": "2885",
    "HDFCBANK": "1333",
    "TCS": "11536",
    "INFY": "1594",
}

URL = "https://api.dhan.co/v2/charts/rollingoption"
REQ_FIELDS = ["open", "high", "low", "close", "volume", "oi", "iv", "spot", "strike"]


def get_headers() -> Dict[str, str]:
    return {
        "access-token": str(Config.DHAN_ACCESS_TOKEN).strip(),
        "client-id": str(Config.DHAN_CLIENT_ID).strip(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def month_windows(start: str, end: str) -> List[Tuple[str, str]]:
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    out = []
    for m in pd.date_range(s.normalize().replace(day=1), e, freq="MS"):
        last = min(m + pd.offsets.MonthEnd(0), e)
        out.append((m.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d")))
    return list(reversed(out))


def fetch_chunk(headers: Dict[str, str], symbol: str, sid: str, side: str, frm: str, to: str) -> Tuple[str, int]:
    out_dir = OUT_ROOT / f"symbol={symbol}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{side}_{frm[:7]}.parquet"

    if out_file.exists():
        return "CACHED", 1

    payload = {
        "exchangeSegment": "NSE_FNO",
        "interval": "5",
        "securityId": str(sid),
        "instrument": "OPTSTK",
        "expiryFlag": "MONTH",
        "expiryCode": 1,
        "strike": "ATM",
        "drvOptionType": "CALL" if side == "ce" else "PUT",
        "requiredData": REQ_FIELDS,
        "fromDate": frm,
        "toDate": to,
    }

    for attempt in range(3):
        try:
            resp = requests.post(URL, headers=headers, json=payload, timeout=25)
            if resp.status_code == 429:
                time.sleep(2.0 * (attempt + 1))
                continue
            if resp.status_code != 200:
                return f"HTTP_{resp.status_code}", 0
            body = resp.json()
            data = body.get("data", {}) or {}
            leg_data = data.get(side) or {}
            if not isinstance(leg_data, dict) or not leg_data.get("timestamp"):
                return "EMPTY", 0

            df = pd.DataFrame(leg_data)
            df["symbol"] = symbol
            df["side"] = side.upper()
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
            df.to_parquet(out_file, index=False)
            return "FETCHED", len(df)
        except Exception as exc:
            if attempt == 2:
                return f"ERROR_{type(exc).__name__}", 0
            time.sleep(1.0)
    return "FAILED", 0


def download_symbol(sym: str, sid: str, windows: List[Tuple[str, str]], headers: Dict[str, str], sleep: float):
    print(f"Starting {sym} (sid={sid})...", flush=True)
    for side in ["ce", "pe"]:
        for frm, to in windows:
            status, count = fetch_chunk(headers, sym, sid, side, frm, to)
            if status == "FETCHED":
                print(f"  {sym} {side.upper()} {frm[:7]}: {status} ({count} rows)", flush=True)
                time.sleep(sleep)
            elif status != "CACHED":
                print(f"  {sym} {side.upper()} {frm[:7]}: {status}", flush=True)
    print(f"Finished {sym}!", flush=True)


def ingest_all(start: str = "2024-10-01", end: str = "2026-09-18", sleep: float = 0.3, max_workers: int = 3):
    headers = get_headers()
    windows = month_windows(start, end)
    print(f"Ingesting stock options for {list(STOCKS.keys())} across {len(windows)} months with {max_workers} workers...", flush=True)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(download_symbol, sym, sid, windows, headers, sleep)
            for sym, sid in STOCKS.items()
        ]
        for f in as_completed(futures):
            f.result()

    print("\nConsolidating parquet files into derived dataset...", flush=True)
    all_files = list(OUT_ROOT.glob("**/*.parquet"))
    print(f"Found {len(all_files)} files. Reading...", flush=True)
    all_dfs = [pd.read_parquet(f) for f in all_files]

    if all_dfs:
        full_df = pd.concat(all_dfs, ignore_index=True)
        full_df = full_df.sort_values(["datetime", "symbol", "side"]).reset_index(drop=True)
        DERIVED_DIR.mkdir(parents=True, exist_ok=True)
        out_parquet = DERIVED_DIR / "grid5m_stocks.parquet"
        full_df.to_parquet(out_parquet, index=False)
        print(f"\n[DONE] Successfully saved consolidated panel to {out_parquet}: shape={full_df.shape}", flush=True)
        print(f"Date range: {full_df['datetime'].min()} to {full_df['datetime'].max()}", flush=True)
        print(f"Symbols: {full_df['symbol'].value_counts().to_dict()}", flush=True)
    else:
        print("\n[WARNING] No data ingested!", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2024-10-01")
    parser.add_argument("--end", default="2026-09-18")
    parser.add_argument("--sleep", type=float, default=0.3)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()

    ingest_all(args.start, args.end, args.sleep, args.workers)

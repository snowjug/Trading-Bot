"""
Data Inventory Utility (Phase 17).
Scans the Parquet Data Lake and prints an inventory summary:
Dataset, Total Rows, Size on Disk, File Count, and Date Range.
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Any
import pyarrow.parquet as pq

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.logging import setup_logging

logger = setup_logging("scripts.data_inventory")


def scan_dataset(name: str, base_dir: Path) -> Dict[str, Any]:
    if not base_dir.exists():
        return {"name": name, "rows": 0, "size_mb": 0.0, "files": 0, "dates": "N/A"}

    parquet_files = list(base_dir.rglob("*.parquet"))
    if not parquet_files:
        return {"name": name, "rows": 0, "size_mb": 0.0, "files": 0, "dates": "N/A"}

    total_rows = 0
    total_bytes = 0
    dates = set()

    for f in parquet_files:
        try:
            total_bytes += f.stat().st_size
            meta = pq.read_metadata(f)
            total_rows += meta.num_rows
            for part in f.parts:
                if part.startswith("date="):
                    dates.add(part.replace("date=", ""))
        except Exception:
            continue

    date_range = "N/A"
    if dates:
        sorted_dates = sorted(list(dates))
        date_range = f"{sorted_dates[0]} to {sorted_dates[-1]}" if len(sorted_dates) > 1 else sorted_dates[0]

    return {
        "name": name,
        "rows": total_rows,
        "size_mb": round(total_bytes / (1024 * 1024), 2),
        "files": len(parquet_files),
        "dates": date_range,
    }


def main():
    datasets = [
        ("Raw Option Chains", Path("data/raw/dhan/optionchain")),
        ("Raw Quotes & Feed", Path("data/raw/dhan/quotes")),
        ("Normalized Options", Path("data/normalized/options")),
        ("Normalized Indices", Path("data/normalized/indices")),
        ("Point-in-Time Features", Path("data/derived/features")),
        ("Instrument Manifests", Path("data/metadata/instruments")),
        ("Replay Datasets", Path("data/replay")),
    ]

    print("=========================================================================================")
    print("MARKET DATA LAKE INVENTORY")
    print("=========================================================================================")
    print(f"{'Dataset':<26} | {'Rows':<12} | {'Size (MB)':<10} | {'Files':<6} | {'Date Range':<20}")
    print("---------------------------+--------------+------------+--------+------------------------")

    total_all_rows = 0
    total_all_mb = 0.0

    for name, path in datasets:
        info = scan_dataset(name, path)
        total_all_rows += info["rows"]
        total_all_mb += info["size_mb"]
        print(f"{info['name']:<26} | {info['rows']:<12,d} | {info['size_mb']:<10.2f} | {info['files']:<6d} | {info['dates']:<20}")

    print("=========================================================================================")
    print(f"TOTAL DATA LAKE STORAGE: {total_all_rows:,} rows across {total_all_mb:.2f} MB")
    print("=========================================================================================")


if __name__ == "__main__":
    main()

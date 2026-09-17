"""
Data Statistics & Storage Projections Utility (Phase 17).
Calculates total rows, files, bytes, compression ratio, daily velocity,
and projected monthly/yearly storage requirements for the Parquet Data Lake.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any
import pyarrow.parquet as pq

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def compute_lake_stats(lake_dir: Path = Path("data")) -> Dict[str, Any]:
    if not lake_dir.exists():
        return {}

    parquet_files = list(lake_dir.rglob("*.parquet"))
    total_files = len(parquet_files)
    total_bytes = sum(f.stat().st_size for f in parquet_files)
    total_rows = 0
    total_uncompressed_bytes = 0
    dates = set()

    for f in parquet_files:
        try:
            meta = pq.read_metadata(f)
            total_rows += meta.num_rows
            for r_idx in range(meta.num_row_groups):
                rg = meta.row_group(r_idx)
                total_uncompressed_bytes += rg.total_byte_size
            for part in f.parts:
                if part.startswith("date="):
                    dates.add(part.replace("date=", ""))
        except Exception:
            continue

    active_days = max(1, len(dates))
    compression_ratio = (total_uncompressed_bytes / total_bytes) if total_bytes > 0 else 1.0
    rows_per_day = total_rows / active_days
    bytes_per_day = total_bytes / active_days

    # Institutional Indian market projections (252 trading sessions / year, 21 / month)
    monthly_projected_bytes = bytes_per_day * 21
    yearly_projected_bytes = bytes_per_day * 252

    return {
        "total_rows": total_rows,
        "total_files": total_files,
        "total_bytes": total_bytes,
        "total_mb": total_bytes / (1024 * 1024),
        "total_uncompressed_mb": total_uncompressed_bytes / (1024 * 1024),
        "compression_ratio": compression_ratio,
        "active_days": active_days,
        "rows_per_day": rows_per_day,
        "mb_per_day": bytes_per_day / (1024 * 1024),
        "monthly_projected_gb": monthly_projected_bytes / (1024 * 1024 * 1024),
        "yearly_projected_gb": yearly_projected_bytes / (1024 * 1024 * 1024),
    }


def main():
    stats = compute_lake_stats()
    if not stats:
        print("Data lake directory 'data' not found or empty.")
        sys.exit(0)

    print("==================================================")
    print("PARQUET DATA LAKE STATISTICS & PROJECTIONS")
    print("==================================================")
    print(f"Total Rows:                {stats['total_rows']:,}")
    print(f"Total Parquet Files:       {stats['total_files']:,}")
    print(f"Total Disk Footprint:      {stats['total_mb']:.2f} MB")
    print(f"Uncompressed Data Size:    {stats['total_uncompressed_mb']:.2f} MB")
    print(f"Effective Compression:     {stats['compression_ratio']:.2f}x (Snappy/ZSTD)")
    print("--------------------------------------------------")
    print(f"Active Market Sessions:    {stats['active_days']} day(s)")
    print(f"Ingestion Velocity (Rows): {stats['rows_per_day']:,.0f} rows/day")
    print(f"Ingestion Velocity (Size): {stats['mb_per_day']:.2f} MB/day")
    print("--------------------------------------------------")
    print("STORAGE CAPACITY FORECAST (252 NSE Trading Days):")
    print(f"Estimated Monthly Storage: {stats['monthly_projected_gb']:.3f} GB / month")
    print(f"Estimated Yearly Storage:  {stats['yearly_projected_gb']:.3f} GB / year")
    print("==================================================")


if __name__ == "__main__":
    main()

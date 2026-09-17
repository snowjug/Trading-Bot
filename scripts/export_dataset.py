"""
Dataset Export Utility (Phase 18).
Exports captured and normalized datasets from the Parquet Data Lake into
consolidated Parquet or CSV files for external research, model training, or offline archiving.
Automatically generates an accompanying README metadata file.

Usage:
python scripts/export_dataset.py --dataset options --start 2026-01-01 --end 2026-09-17 --output exports/options_2026.parquet
python scripts/export_dataset.py --dataset features --format csv --output exports/features.csv
"""

import os
import sys
import argparse
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.logging import setup_logging

logger = setup_logging("scripts.export_dataset")


DATASET_PATHS = {
    "options": Path("data/normalized/options"),
    "indices": Path("data/normalized/indices"),
    "features": Path("data/derived/features"),
    "raw_options": Path("data/raw/dhan/optionchain"),
    "instruments": Path("data/metadata/instruments"),
}


def export_data(
    dataset_name: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    output_path: Optional[str] = None,
    export_format: str = "parquet",
) -> Optional[Path]:
    base_dir = DATASET_PATHS.get(dataset_name.lower())
    if not base_dir or not base_dir.exists():
        logger.error(f"Dataset '{dataset_name}' not found. Available: {list(DATASET_PATHS.keys())}")
        return None

    logger.info(f"Scanning files for dataset '{dataset_name}' in {base_dir}...")
    parquet_files = list(base_dir.rglob("*.parquet"))
    if not parquet_files:
        logger.warning(f"No Parquet files found in {base_dir}.")
        return None

    # Filter by date range if specified
    filtered_files = []
    for f in parquet_files:
        include = True
        file_date_str = None
        for part in f.parts:
            if part.startswith("date="):
                file_date_str = part.replace("date=", "")
                break

        if file_date_str:
            if start_date and file_date_str < start_date:
                include = False
            if end_date and file_date_str > end_date:
                include = False

        if include:
            filtered_files.append(f)

    if not filtered_files:
        logger.warning("No files matched the specified date criteria.")
        return None

    logger.info(f"Loading {len(filtered_files)} Parquet files for export...")
    dfs = [pd.read_parquet(f) for f in filtered_files]
    combined_df = pd.concat(dfs, ignore_index=True)

    out_p = Path(output_path) if output_path else Path(f"exports/{dataset_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{export_format}")
    out_p.parent.mkdir(parents=True, exist_ok=True)

    if export_format.lower() == "csv":
        combined_df.to_csv(out_p, index=False)
    else:
        combined_df.to_parquet(out_p, compression="snappy", index=False)

    # Generate accompanying README metadata
    readme_path = out_p.parent / f"{out_p.stem}_README.md"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(f"# Exported Dataset: `{dataset_name}`\n\n")
        f.write(f"- **Generated At:** {datetime.now().isoformat()}\n")
        f.write(f"- **Source Format:** Apache Parquet (Dhan Data Lake)\n")
        f.write(f"- **Total Rows:** {len(combined_df):,}\n")
        f.write(f"- **Total Columns:** {len(combined_df.columns)}\n")
        f.write(f"- **Date Filter:** {start_date or 'ALL'} to {end_date or 'ALL'}\n")
        f.write(f"- **Export File:** `{out_p.name}`\n\n")
        f.write("## Schema Fields:\n")
        for col in combined_df.columns:
            f.write(f"- `{col}`: {combined_df[col].dtype}\n")

    logger.info(f"Successfully exported {len(combined_df):,} rows -> {out_p}")
    logger.info(f"Export metadata written -> {readme_path}")
    return out_p


def main():
    parser = argparse.ArgumentParser(description="Export Data Lake Datasets to Parquet or CSV")
    parser.add_argument("--dataset", required=True, help="Dataset name: options, indices, features, raw_options, instruments")
    parser.add_argument("--start", default=None, help="Start date filter YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="End date filter YYYY-MM-DD")
    parser.add_argument("--output", default=None, help="Output destination file path")
    parser.add_argument("--format", default="parquet", choices=["parquet", "csv"], help="Export format")
    args = parser.parse_args()

    res = export_data(
        dataset_name=args.dataset,
        start_date=args.start,
        end_date=args.end,
        output_path=args.output,
        export_format=args.format,
    )
    if res:
        print(f"Export completed: {res}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

"""
Feature Pipeline & Dataset Builder (Phase 8 & 9).
Reads normalized Parquet datasets, computes point-in-time features without lookahead,
and stores derived features under data/derived/features/date=YYYY-MM-DD/.
"""

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.logging import setup_logging
from src.features.pit_store import PointInTimeFeatureStore

logger = setup_logging("scripts.build_features")


def process_features_for_dataset(source_path: Path, output_dir: Path, bar_interval: int = 1):
    """
    Computes point-in-time features for a normalized dataset.
    """
    if not source_path.exists():
        logger.error(f"Source file not found: {source_path}")
        return None

    logger.info(f"Loading normalized dataset: {source_path}...")
    df = pd.read_parquet(source_path)
    if df.empty:
        logger.warning(f"Dataset {source_path} is empty.")
        return None

    features = PointInTimeFeatureStore.compute_features(df, bar_interval_minutes=bar_interval)
    output_dir.mkdir(parents=True, exist_ok=True)
    dest_path = output_dir / f"features_{source_path.stem}.parquet"

    table = pa.Table.from_pandas(features)
    pq.write_table(table, dest_path, compression="snappy")
    logger.info(f"Saved {len(features)} point-in-time feature rows -> {dest_path}")
    return dest_path


def main():
    parser = argparse.ArgumentParser(description="Build Point-in-Time Features from Normalized Data")
    parser.add_argument("--source", required=True, help="Path to normalized parquet file")
    parser.add_argument("--output", default="data/derived/features", help="Output directory")
    parser.add_argument("--interval", type=int, default=1, help="Bar interval in minutes")
    args = parser.parse_args()

    dest = process_features_for_dataset(
        source_path=Path(args.source),
        output_dir=Path(args.output),
        bar_interval=args.interval,
    )
    if dest:
        print(f"Features successfully built: {dest}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

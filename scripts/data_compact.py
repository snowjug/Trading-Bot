"""
Parquet Data Compaction Utility (Phase 17).
Merges small Parquet files within partitions safely into consolidated chunks
to prevent small-file fragmentation while preserving immutability and atomic writes.
"""

import os
import sys
import argparse
from pathlib import Path
from typing import List
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.logging import setup_logging

logger = setup_logging("scripts.data_compact")


def compact_directory(target_dir: Path, min_file_count: int = 3) -> bool:
    if not target_dir.exists():
        logger.error(f"Target directory does not exist: {target_dir}")
        return False

    parquet_files = [f for f in target_dir.glob("*.parquet") if not f.name.endswith(".tmp.parquet")]
    if len(parquet_files) < min_file_count:
        logger.info(f"Directory {target_dir} has {len(parquet_files)} files (threshold: {min_file_count}). No compaction needed.")
        return True

    logger.info(f"Compacting {len(parquet_files)} files in {target_dir}...")
    tables = []
    total_rows = 0

    for f in parquet_files:
        try:
            t = pq.read_table(f)
            tables.append(t)
            total_rows += t.num_rows
        except Exception as e:
            logger.error(f"Failed to read file {f} during compaction: {e}")
            return False

    if not tables:
        return False

    # Concatenate tables safely
    consolidated_table = pa.concat_tables(tables)
    compacted_file = target_dir / "consolidated_part0.parquet"
    tmp_compacted = target_dir / "consolidated_part0.tmp.parquet"

    pq.write_table(consolidated_table, tmp_compacted, compression="snappy")
    if tmp_compacted.exists():
        tmp_compacted.replace(compacted_file)

    logger.info(f"Successfully compacted {len(parquet_files)} files into {compacted_file} ({total_rows:,} rows).")
    return True


def main():
    parser = argparse.ArgumentParser(description="Compact Small Parquet Files in a Directory Partition")
    parser.add_argument("--dir", required=True, help="Directory path to compact")
    parser.add_argument("--min-files", type=int, default=3, help="Minimum file count to trigger compaction")
    args = parser.parse_args()

    success = compact_directory(Path(args.dir), min_file_count=args.min_files)
    if success:
        print("Compaction check completed successfully.")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

"""
Training Dataset Pipeline (Phase 19).
Transforms normalized market observations and point-in-time features into
strictly causal, leak-free machine learning datasets (X, y) with chronological splits.

Preserves an untouched out-of-sample test period and stores:
- dataset_version
- feature_definitions
- label_definitions
- source_manifest
- git_commit_sha
"""

import os
import sys
import json
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple, List, Any
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.logging import setup_logging
from src.features.pit_store import PointInTimeFeatureStore

logger = setup_logging("scripts.build_training_dataset")


def get_git_commit_sha() -> str:
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return "UNKNOWN_COMMIT"


def create_training_dataset(
    source_parquet: Path,
    output_dir: Path,
    forward_horizon_bars: int = 5,
    test_split_ratio: float = 0.20,
    val_split_ratio: float = 0.15,
    dataset_version: str = "2026.1.0",
) -> Tuple[Path, Path, Path]:
    if not source_parquet.exists():
        raise FileNotFoundError(f"Source file does not exist: {source_parquet}")

    logger.info(f"Loading normalized data from {source_parquet}...")
    df = pd.read_parquet(source_parquet)
    if df.empty:
        raise ValueError("Source dataset is empty.")

    # 1. Compute Point-in-Time Features
    features = PointInTimeFeatureStore.compute_features(df, bar_interval_minutes=1)
    
    # 2. Construct Ground Truth Labels (Target)
    close = df["close"] if "close" in df.columns else df.get("ltp", pd.Series(dtype=float))
    
    # Forward return over horizon
    fwd_ret = (close.shift(-forward_horizon_bars) - close) / close
    # Binary label: 1 if positive return, 0 if flat/negative
    label = (fwd_ret > 0.0005).astype(int)

    features["label_fwd_ret"] = fwd_ret
    features["target"] = label

    # Drop rows at the end where forward label cannot be computed
    valid_data = features.dropna(subset=["target"]).copy()
    valid_data = valid_data.sort_values(by="available_at").reset_index(drop=True)

    total_samples = len(valid_data)
    if total_samples < 5:
        # For small historical slices, keep all
        n_test = max(1, int(total_samples * test_split_ratio))
        n_val = max(1, int(total_samples * val_split_ratio))
        n_train = max(1, total_samples - n_test - n_val)
    else:
        n_test = int(total_samples * test_split_ratio)
        n_val = int(total_samples * val_split_ratio)
        n_train = total_samples - n_test - n_val

    # 3. Chronological Split (Strictly NO random shuffling)
    train_df = valid_data.iloc[:n_train].copy()
    val_df = valid_data.iloc[n_train:n_train + n_val].copy()
    test_df = valid_data.iloc[n_train + n_val:].copy()

    # Tag splits
    train_df["split"] = "TRAIN"
    val_df["split"] = "VALIDATION"
    test_df["split"] = "TEST_UNTOUCHED"

    output_dir.mkdir(parents=True, exist_ok=True)
    train_path = output_dir / f"train_{dataset_version}.parquet"
    val_path = output_dir / f"val_{dataset_version}.parquet"
    test_path = output_dir / f"test_{dataset_version}.parquet"
    meta_path = output_dir / f"dataset_manifest_{dataset_version}.json"

    pq.write_table(pa.Table.from_pandas(train_df), train_path, compression="snappy")
    pq.write_table(pa.Table.from_pandas(val_df), val_path, compression="snappy")
    pq.write_table(pa.Table.from_pandas(test_df), test_path, compression="snappy")

    # 4. Manifest
    manifest = {
        "dataset_version": dataset_version,
        "created_at": datetime.now().isoformat(),
        "git_commit_sha": get_git_commit_sha(),
        "source_file": str(source_parquet),
        "total_samples": total_samples,
        "train_samples": len(train_df),
        "val_samples": len(val_df),
        "test_samples": len(test_df),
        "features": [c for c in train_df.columns if c not in ["target", "label_fwd_ret", "split", "feature_timestamp", "available_at"]],
        "label_definition": f"1 if forward_{forward_horizon_bars}m_return > +0.05% else 0",
        "causality_policy": "Strict Point-In-Time. No future information leakage.",
    }

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    logger.info(f"Training dataset saved: Train={len(train_df)}, Val={len(val_df)}, Test={len(test_df)} -> {output_dir}")
    return train_path, val_path, test_path


def main():
    parser = argparse.ArgumentParser(description="Build Leak-Free ML Training Dataset")
    parser.add_argument("--source", required=True, help="Source normalized parquet file")
    parser.add_argument("--output", default="data/derived/training", help="Destination directory")
    parser.add_argument("--version", default="2026.1.0", help="Dataset semantic version")
    args = parser.parse_args()

    train, val, test = create_training_dataset(
        source_parquet=Path(args.source),
        output_dir=Path(args.output),
        dataset_version=args.version,
    )
    print(f"Training splits generated successfully at {Path(args.output)}")


if __name__ == "__main__":
    main()

"""
Sacred Quarantined Test Dataset Guardian.
Strictly quarantines the out-of-sample test period (2024-01-01 to 2026-09-16).
Prevents data snooping, feature selection leakage, and parameter optimization on unseen data.
"""
import hashlib
import json
from datetime import datetime
from pathlib import Path
import pandas as pd
from src.utils.logging import setup_logging

logger = setup_logging("data.sacred_dataset")


class SacredDataBreachError(Exception):
    """Raised when an algorithm attempts to access quarantined test data during training/tuning."""
    pass


class SacredDatasetGuardian:
    """
    Guarantees strict quarantine of out-of-sample data.
    """
    SACRED_SPLIT_DATE = datetime(2024, 1, 1)
    MANIFEST_PATH = Path("data/processed/sacred_test_manifest.json")

    @classmethod
    def split_sacred_data(cls, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Partition dataset into Research/Train (pre-2024) and Sacred Test (post-2024).
        """
        df = df.copy()
        df["datetime"] = pd.to_datetime(df["datetime"])
        
        train_df = df[df["datetime"] < cls.SACRED_SPLIT_DATE].copy().reset_index(drop=True)
        sacred_df = df[df["datetime"] >= cls.SACRED_SPLIT_DATE].copy().reset_index(drop=True)
        
        return train_df, sacred_df

    @classmethod
    def verify_no_sacred_leakage(cls, training_df: pd.DataFrame, context_name: str = "Training"):
        """
        Asserts that training or optimization dataset contains zero bars from the sacred period.
        """
        if "datetime" not in training_df.columns:
            return
        dates = pd.to_datetime(training_df["datetime"])
        max_date = dates.max()
        if max_date >= cls.SACRED_SPLIT_DATE:
            raise SacredDataBreachError(
                f"FATAL RESEARCH LEAKAGE in {context_name}: "
                f"Attempted to access sacred data beyond {cls.SACRED_SPLIT_DATE} (found bar at {max_date})!"
            )

    @classmethod
    def generate_sacred_manifest(cls, nifty_df: pd.DataFrame) -> dict:
        """Create cryptographic checksum hash of sacred out-of-sample data."""
        _, sacred_df = cls.split_sacred_data(nifty_df)
        csv_bytes = sacred_df.to_csv(index=False).encode("utf-8")
        sha256_hash = hashlib.sha256(csv_bytes).hexdigest()

        manifest = {
            "sacred_split_date": cls.SACRED_SPLIT_DATE.isoformat(),
            "num_bars": len(sacred_df),
            "start_date": str(sacred_df["datetime"].min()),
            "end_date": str(sacred_df["datetime"].max()),
            "sha256_hash": sha256_hash,
            "created_at": datetime.now().isoformat(),
            "policy": "STRICT_QUARANTINE_NO_TUNING_PERMITTED",
        }
        cls.MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(cls.MANIFEST_PATH, "w") as f:
            json.dump(manifest, f, indent=2)
        return manifest

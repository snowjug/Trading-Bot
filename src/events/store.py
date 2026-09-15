"""
Event Store for Indian Quant Platform.
Stores processed event features and enforces strict point-in-time lookup
to prevent look-ahead bias during backtesting and live simulation.
"""

from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict
import pandas as pd
import json

from src.config import Config
from src.events.feature_engine import EventFeature
from src.utils.logging import get_logger

logger = get_logger("events.store")


class EventStore:
    """Persistent storage for market events with strict point-in-time querying."""

    def __init__(self, store_path: Optional[Path] = None):
        self.store_dir = store_path or (Config.DATA_DIR / "events")
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.parquet_path = self.store_dir / "event_features.parquet"
        self._cache: Optional[pd.DataFrame] = None
        self._load()

    def _load(self):
        """Load cached events from Parquet if available."""
        if self.parquet_path.exists():
            try:
                self._cache = pd.read_parquet(self.parquet_path)
                logger.info(f"Loaded {len(self._cache)} event records from {self.parquet_path}")
            except Exception as e:
                logger.warning(f"Could not load event store: {e}")
                self._cache = pd.DataFrame()
        else:
            self._cache = pd.DataFrame()

    def save_features(self, features: List[EventFeature]):
        """Append new event features and persist to Parquet."""
        if not features:
            return

        records = [f.to_dict() for f in features]
        new_df = pd.DataFrame(records)
        new_df["event_timestamp"] = pd.to_datetime(new_df["event_timestamp"])
        new_df["available_at"] = pd.to_datetime(new_df["available_at"])

        if self._cache is not None and not self._cache.empty:
            combined = pd.concat([self._cache, new_df], ignore_index=True)
            combined.drop_duplicates(subset=["event_id"], keep="last", inplace=True)
            self._cache = combined
        else:
            self._cache = new_df

        self._cache.to_parquet(self.parquet_path, index=False)
        logger.info(f"Persisted {len(self._cache)} events to {self.parquet_path}")

    def get_events_point_in_time(
        self,
        decision_timestamp: datetime,
        symbol: Optional[str] = None,
        lookback_days: int = 5,
    ) -> pd.DataFrame:
        """
        CRITICAL NO-LOOKAHEAD ENFORCEMENT:
        Returns events where available_at <= decision_timestamp.
        Information published AFTER decision_timestamp is strictly inaccessible.
        """
        if self._cache is None or self._cache.empty:
            return pd.DataFrame()

        ts = pd.to_datetime(decision_timestamp)
        # Point-in-time filter
        valid = self._cache[self._cache["available_at"] <= ts]

        # Lookback filter
        earliest = ts - pd.Timedelta(days=lookback_days)
        valid = valid[valid["available_at"] >= earliest]

        if symbol:
            valid = valid[(valid["symbol"] == symbol) | (valid["symbol"].isna()) | (valid["symbol"] == "ALL")]

        return valid.sort_values("available_at", ascending=False)

    def get_aggregate_sentiment(
        self,
        decision_timestamp: datetime,
        symbol: Optional[str] = None,
        lookback_days: int = 3,
    ) -> float:
        """Computes aggregate sentiment score known at decision_timestamp."""
        events = self.get_events_point_in_time(decision_timestamp, symbol, lookback_days)
        if events.empty:
            return 0.0
        # Weighted by importance and confidence
        weights = events["importance"] * events["confidence"]
        if weights.sum() == 0:
            return 0.0
        weighted_score = (events["directional_score"] * weights).sum() / weights.sum()
        return float(weighted_score)

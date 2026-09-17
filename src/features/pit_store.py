"""
Point-in-Time (PIT) Feature Store & Anti-Lookahead Engine (Phases 8 & 9).
Enforces the fundamental causal condition:
feature_timestamp <= available_at <= decision_time

Guarantees zero future information leakage into historical backtests,
deterministic replays, or real-time paper trading.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Union
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.utils.logging import setup_logging

logger = setup_logging("features.pit_store")


class LookaheadBiasError(Exception):
    """Raised when future data leakage is detected in a decision query."""
    pass


class PointInTimeFeatureStore:
    """
    Computes and queries point-in-time features with strict causal timestamps.
    """

    FEATURE_METADATA = {
        "returns": {"lookback": 1, "desc": "Percentage return over prior available close"},
        "log_returns": {"lookback": 1, "desc": "Log return over prior available close"},
        "rsi_14": {"lookback": 14, "desc": "Relative Strength Index (Wilder's smoothing)"},
        "ema_9": {"lookback": 9, "desc": "Exponential Moving Average over 9 closed bars"},
        "ema_21": {"lookback": 21, "desc": "Exponential Moving Average over 21 closed bars"},
        "sma_50": {"lookback": 50, "desc": "Simple Moving Average over 50 closed bars"},
        "atr_14": {"lookback": 14, "desc": "Average True Range over 14 closed bars"},
        "vwap": {"lookback": "intraday", "desc": "Intraday Volume Weighted Average Price"},
        "bb_upper": {"lookback": 20, "desc": "Bollinger Bands Upper Band (2 std dev)"},
        "bb_lower": {"lookback": 20, "desc": "Bollinger Bands Lower Band (2 std dev)"},
        "realized_vol_20": {"lookback": 20, "desc": "Realized 20-period annualized volatility"},
        "volume_momentum_5": {"lookback": 5, "desc": "Ratio of 5-period average volume to 20-period average volume"},
        "oi_change": {"lookback": 1, "desc": "Absolute change in Open Interest"},
        "spread_width": {"lookback": 0, "desc": "Bid-Ask spread width in INR"},
    }

    @classmethod
    def compute_features(
        cls,
        df: pd.DataFrame,
        bar_interval_minutes: int = 1,
        source_version: str = "1.0.0",
    ) -> pd.DataFrame:
        """
        Calculates all technical, volatility, and microstructure features.
        Enforces:
        available_at = bar_timestamp + bar_interval_minutes
        so closed bar features are only accessible AFTER the bar period has elapsed.
        """
        if df.empty:
            return pd.DataFrame()

        data = df.copy()
        
        # Sort chronologically to preserve causality
        ts_col = "timestamp" if "timestamp" in data.columns else "event_timestamp"
        data[ts_col] = pd.to_datetime(data[ts_col])
        data = data.sort_values(by=ts_col).reset_index(drop=True)

        close = data["close"] if "close" in data.columns else data.get("ltp", pd.Series(dtype=float))
        high = data.get("high", close)
        low = data.get("low", close)
        vol = data.get("volume", pd.Series(0, index=data.index))
        oi = data.get("oi", pd.Series(0, index=data.index))
        bid = data.get("bid", pd.Series(0.0, index=data.index))
        ask = data.get("ask", pd.Series(0.0, index=data.index))

        features = pd.DataFrame(index=data.index)
        features["feature_timestamp"] = data[ts_col]
        # Bar closes at timestamp + interval. Feature is available strictly at bar close.
        features["available_at"] = data[ts_col] + pd.to_timedelta(bar_interval_minutes, unit="m")

        if "security_id" in data.columns:
            features["security_id"] = data["security_id"]
        if "symbol" in data.columns:
            features["symbol"] = data["symbol"]
        elif "underlying" in data.columns:
            features["symbol"] = data["underlying"]

        # 1. Returns & Log Returns (causal shift)
        features["returns"] = close.pct_change().shift(1).fillna(0.0)
        features["log_returns"] = np.log(close / close.shift(1)).shift(1).fillna(0.0)

        # 2. Moving Averages (causal shift: computed on closed bars)
        features["ema_9"] = close.ewm(span=9, adjust=False).mean().shift(1)
        features["ema_21"] = close.ewm(span=21, adjust=False).mean().shift(1)
        features["sma_50"] = close.rolling(window=50, min_periods=10).mean().shift(1)

        # 3. RSI (14-period Wilder's, shifted)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0.0)).rolling(window=14, min_periods=14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=14, min_periods=14).mean()
        rs = gain / (loss.replace(0, 1e-9))
        rsi = 100.0 - (100.0 / (1.0 + rs))
        features["rsi_14"] = rsi.shift(1).fillna(50.0)

        # 4. ATR (14-period, shifted)
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        features["atr_14"] = tr.rolling(window=14, min_periods=5).mean().shift(1).fillna(0.0)

        # 5. Bollinger Bands (20-period, 2 std dev, shifted)
        rolling_mean = close.rolling(window=20, min_periods=5).mean()
        rolling_std = close.rolling(window=20, min_periods=5).std()
        features["bb_upper"] = (rolling_mean + (2 * rolling_std)).shift(1)
        features["bb_lower"] = (rolling_mean - (2 * rolling_std)).shift(1)

        # 6. Realized Volatility (20-period annualized, shifted)
        ret = close.pct_change()
        features["realized_vol_20"] = (ret.rolling(window=20, min_periods=5).std() * np.sqrt(252 * 375)).shift(1).fillna(0.0)

        # 7. Volume Momentum & OI
        vol_mean_5 = vol.rolling(window=5, min_periods=1).mean()
        vol_mean_20 = vol.rolling(window=20, min_periods=5).mean().replace(0, 1)
        features["volume_momentum_5"] = (vol_mean_5 / vol_mean_20).shift(1).fillna(1.0)
        features["oi_change"] = oi.diff().shift(1).fillna(0)

        # 8. Microstructure: Executable Spread Width
        spread = (ask - bid).where((ask > 0) & (bid > 0), 0.0)
        features["spread_width"] = spread

        # Greeks and IV if present in normalized data
        if "iv" in data.columns:
            features["iv"] = data["iv"]
        if "delta" in data.columns:
            features["delta"] = data["delta"]
        if "theta" in data.columns:
            features["theta"] = data["theta"]
        if "gamma" in data.columns:
            features["gamma"] = data["gamma"]
        if "vega" in data.columns:
            features["vega"] = data["vega"]

        features["source_version"] = source_version
        features["computed_at"] = datetime.now().isoformat()
        return features

    @classmethod
    def get_features_as_of(
        cls,
        feature_df: pd.DataFrame,
        decision_time: Union[datetime, pd.Timestamp, str],
        symbol: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Point-in-Time Query Engine.
        Retrieves ONLY observations that were strictly available on or before decision_time.
        Strictly enforces:
        available_at <= decision_time
        """
        if feature_df.empty:
            return pd.DataFrame()

        d_time = pd.to_datetime(decision_time)
        avail_col = pd.to_datetime(feature_df["available_at"])

        # Filter strictly causal observations
        mask = avail_col <= d_time
        if symbol and "symbol" in feature_df.columns:
            mask = mask & (feature_df["symbol"] == symbol)

        filtered = feature_df[mask].copy()

        # Audit check: Assert zero future leakage
        cls.assert_no_lookahead(filtered, d_time)

        return filtered

    @classmethod
    def assert_no_lookahead(
        cls,
        df: pd.DataFrame,
        decision_time: Union[datetime, pd.Timestamp, str],
    ) -> None:
        """
        Rigorous lookahead detector.
        Raises LookaheadBiasError if ANY record has available_at > decision_time.
        """
        if df.empty:
            return

        d_time = pd.to_datetime(decision_time)
        avail = pd.to_datetime(df["available_at"])
        violations = avail[avail > d_time]

        if not violations.empty:
            bad_sample = violations.iloc[0]
            raise LookaheadBiasError(
                f"CRITICAL LOOKAHEAD DETECTED! Observation available at {bad_sample} queried for decision at {d_time}. "
                f"Total {len(violations)} lookahead violations intercepted!"
            )

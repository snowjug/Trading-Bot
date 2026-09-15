"""
Volume-based features.
"""
import pandas as pd
import numpy as np
from src.utils.logging import setup_logging

logger = setup_logging("features.volume")


class VolumeFeatures:
    """Compute volume-based features."""

    @staticmethod
    def compute_all(df: pd.DataFrame) -> pd.DataFrame:
        """Compute all volume features. Requires: volume, close columns."""
        df = df.copy()

        if "volume" not in df.columns:
            logger.warning("No volume column — skipping volume features")
            return df

        vol = df["volume"].replace(0, np.nan)

        # Volume change
        df["volume_change_1d"] = vol.pct_change(1)
        df["volume_change_5d"] = vol.pct_change(5)

        # Relative volume (vs moving average)
        for w in [10, 20, 50]:
            avg_vol = vol.rolling(w).mean()
            df[f"relative_volume_{w}"] = vol / avg_vol.replace(0, np.nan)

        # Volume acceleration
        df["volume_accel"] = vol.diff().diff()

        # Volume moving averages
        for w in [10, 20]:
            df[f"volume_sma_{w}"] = vol.rolling(w).mean()

        # OBV (On-Balance Volume)
        df["obv"] = (np.sign(df["close"].diff()) * vol).fillna(0).cumsum()
        df["obv_sma_20"] = df["obv"].rolling(20).mean()

        # Volume-price trend
        df["vpt"] = (vol * df["close"].pct_change()).fillna(0).cumsum()

        # Volume standard deviation (volatility of volume)
        df["volume_std_20"] = vol.rolling(20).std()

        # High volume indicator (volume > 2x 20-day average)
        df["high_volume"] = (df.get("relative_volume_20", pd.Series(dtype=float)) > 2.0).astype(int)

        return df

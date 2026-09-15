"""
Market structure features.
Previous day levels, gaps, breakouts, opening range.
"""
import pandas as pd
import numpy as np
from src.utils.logging import setup_logging

logger = setup_logging("features.market")


class MarketStructureFeatures:
    """Compute market structure features."""

    @staticmethod
    def compute_all(df: pd.DataFrame) -> pd.DataFrame:
        """Compute market structure features."""
        df = df.copy()

        # Previous day high/low/close (shifted to avoid leakage)
        df["prev_high"] = df["high"].shift(1)
        df["prev_low"] = df["low"].shift(1)
        df["prev_close"] = df["close"].shift(1)
        df["prev_open"] = df["open"].shift(1)

        # Gap
        df["gap_pct"] = (df["open"] - df["prev_close"]) / df["prev_close"].replace(0, np.nan)
        df["gap_abs"] = df["open"] - df["prev_close"]

        # Gap direction
        df["gap_up"] = (df["gap_pct"] > 0.005).astype(int)
        df["gap_down"] = (df["gap_pct"] < -0.005).astype(int)

        # Inside day (today's range within yesterday's)
        df["inside_day"] = (
            (df["high"] <= df["prev_high"]) & (df["low"] >= df["prev_low"])
        ).astype(int)

        # Outside day (today's range engulfs yesterday's)
        df["outside_day"] = (
            (df["high"] > df["prev_high"]) & (df["low"] < df["prev_low"])
        ).astype(int)

        # Breakout distance from recent high/low
        for w in [20, 50]:
            rolling_high = df["high"].rolling(w).max()
            rolling_low = df["low"].rolling(w).min()
            df[f"breakout_dist_high_{w}"] = (df["close"] - rolling_high.shift(1)) / rolling_high.shift(1).replace(0, np.nan)
            df[f"breakout_dist_low_{w}"] = (df["close"] - rolling_low.shift(1)) / rolling_low.shift(1).replace(0, np.nan)

        # Volatility expansion/contraction
        df["range_pct"] = (df["high"] - df["low"]) / df["close"].replace(0, np.nan)
        df["avg_range_10"] = df["range_pct"].rolling(10).mean()
        df["range_expansion"] = df["range_pct"] / df["avg_range_10"].replace(0, np.nan)

        # Distance from all-time high (rolling max)
        df["rolling_max_close"] = df["close"].expanding().max()
        df["dist_from_ath"] = (df["close"] - df["rolling_max_close"]) / df["rolling_max_close"].replace(0, np.nan)

        # Consecutive up/down days
        df["up_day"] = (df["close"] > df["prev_close"]).astype(int)
        df["consecutive_up"] = MarketStructureFeatures._consecutive_count(df["up_day"])
        df["consecutive_down"] = MarketStructureFeatures._consecutive_count(1 - df["up_day"])

        # Higher highs / lower lows
        df["higher_high"] = (df["high"] > df["prev_high"]).astype(int)
        df["lower_low"] = (df["low"] < df["prev_low"]).astype(int)

        return df

    @staticmethod
    def _consecutive_count(series: pd.Series) -> pd.Series:
        """Count consecutive True values."""
        groups = (series != series.shift()).cumsum()
        return series.groupby(groups).cumsum()


class CrossAssetFeatures:
    """Compute cross-asset features (index-relative, sector, macro)."""

    @staticmethod
    def compute_relative_strength(
        stock_df: pd.DataFrame,
        index_df: pd.DataFrame,
        prefix: str = "nifty",
    ) -> pd.DataFrame:
        """Compute stock vs index relative strength features."""
        df = stock_df.copy()

        if index_df.empty or "close" not in index_df.columns:
            return df

        # Align on datetime
        idx = index_df[["datetime", "close"]].rename(columns={"close": f"{prefix}_close"})
        df = df.merge(idx, on="datetime", how="left")

        # Relative strength
        for w in [5, 10, 20, 60]:
            stock_ret = df["close"].pct_change(w)
            idx_ret = df[f"{prefix}_close"].pct_change(w)
            df[f"rs_vs_{prefix}_{w}"] = stock_ret - idx_ret

        # Beta (rolling)
        stock_ret = df["close"].pct_change()
        idx_ret = df[f"{prefix}_close"].pct_change()
        for w in [60, 120]:
            cov = stock_ret.rolling(w).cov(idx_ret)
            var = idx_ret.rolling(w).var()
            df[f"beta_{prefix}_{w}"] = cov / var.replace(0, np.nan)

        # Drop temp column
        df = df.drop(columns=[f"{prefix}_close"], errors="ignore")

        return df

"""
Feature store — centralized feature computation, caching, and leakage prevention.
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from src.features.price_features import PriceFeatures
from src.features.volume_features import VolumeFeatures
from src.features.market_features import MarketStructureFeatures, CrossAssetFeatures
from src.utils.logging import setup_logging

logger = setup_logging("features.store")


class LeakageGuard:
    """
    Prevents look-ahead bias in features.
    Every feature must be computable using only information available
    at the timestamp of the row.
    """

    # Features that are inherently lagged (safe)
    SAFE_FEATURES = {
        "return_1d", "return_5d", "return_10d", "return_20d", "log_return_1d",
        "prev_high", "prev_low", "prev_close", "prev_open",
        "gap_pct", "gap_abs",
    }

    # Features that use rolling windows (safe if shift is correct)
    ROLLING_FEATURES_PREFIX = [
        "sma_", "ema_", "bb_", "atr_", "rsi_", "macd", "adx",
        "donchian_", "momentum_", "volatility_", "volume_sma_",
        "relative_volume_", "obv", "trend_slope_",
    ]

    @staticmethod
    def audit_features(df: pd.DataFrame, target_col: str = "return_1d") -> list[str]:
        """
        Audit feature columns for potential leakage.
        Returns list of suspicious feature names.
        """
        suspicious = []

        if target_col not in df.columns:
            return suspicious

        future_return = df[target_col].shift(-1)  # Next period return

        for col in df.select_dtypes(include=[np.number]).columns:
            if col in ("datetime", target_col, "open", "high", "low", "close", "volume"):
                continue

            try:
                corr = df[col].corr(future_return)
                if abs(corr) > 0.95:
                    suspicious.append(col)
                    logger.warning(f"LEAKAGE SUSPECT: {col} has {corr:.3f} correlation with future return")
            except Exception:
                pass

        return suspicious

    @staticmethod
    def ensure_no_future_data(df: pd.DataFrame, as_of_col: str = "datetime") -> pd.DataFrame:
        """Remove any rows that reference future data."""
        if as_of_col in df.columns:
            now = pd.Timestamp.now()
            mask = df[as_of_col] <= now
            removed = (~mask).sum()
            if removed > 0:
                logger.warning(f"Removed {removed} future-dated rows")
            return df[mask].copy()
        return df


class FeatureStore:
    """
    Centralized feature computation and storage.
    Computes all features for a symbol and caches to Parquet.
    """

    def __init__(self, features_dir: Path = Path("data/features")):
        self.features_dir = Path(features_dir)
        self.features_dir.mkdir(parents=True, exist_ok=True)
        self.leakage_guard = LeakageGuard()

    def compute_features(
        self,
        df: pd.DataFrame,
        symbol: str,
        index_df: pd.DataFrame | None = None,
        cache: bool = True,
        use_cached: bool = True,
    ) -> pd.DataFrame:
        """
        Compute all features for a symbol's OHLCV data.
        Returns DataFrame with all features added.
        """
        if df.empty:
            return df

        if use_cached:
            cached_df = self.load_features(symbol)
            if not cached_df.empty and len(cached_df) >= len(df):
                logger.info(f"Loaded cached features for {symbol} ({len(cached_df)} rows)")
                return cached_df

        logger.info(f"Computing features for {symbol} ({len(df)} rows)")

        # Price features
        featured = PriceFeatures.compute_all(df)

        # Volume features
        featured = VolumeFeatures.compute_all(featured)

        # Market structure features
        featured = MarketStructureFeatures.compute_all(featured)

        # Cross-asset features (if index data available)
        if index_df is not None and not index_df.empty:
            featured = CrossAssetFeatures.compute_relative_strength(
                featured, index_df, prefix="nifty"
            )

        # Add symbol column
        featured["symbol"] = symbol

        # Leakage audit
        suspicious = self.leakage_guard.audit_features(featured)
        if suspicious:
            logger.warning(f"Potential leakage in features: {suspicious}")

        # Cache to Parquet
        if cache:
            cache_path = self.features_dir / f"{symbol}_features.parquet"
            featured.to_parquet(cache_path, index=False, compression="snappy")
            logger.info(f"Cached features to {cache_path}")

        return featured

    def load_features(self, symbol: str) -> pd.DataFrame:
        """Load cached features for a symbol."""
        path = self.features_dir / f"{symbol}_features.parquet"
        if path.exists():
            return pd.read_parquet(path)
        return pd.DataFrame()

    def compute_universe_features(
        self,
        universe_data: dict[str, pd.DataFrame],
        index_df: pd.DataFrame | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Compute features for all symbols in a universe."""
        results = {}
        for symbol, df in universe_data.items():
            try:
                featured = self.compute_features(df, symbol, index_df)
                results[symbol] = featured
            except Exception as e:
                logger.error(f"Failed to compute features for {symbol}: {e}")
        logger.info(f"Computed features for {len(results)}/{len(universe_data)} symbols")
        return results

    def get_feature_columns(self, df: pd.DataFrame) -> list[str]:
        """Get list of feature columns (excluding metadata and price data)."""
        exclude = {"datetime", "symbol", "open", "high", "low", "close", "volume",
                    "adj_close", "dividends", "splits", "cap_gains"}
        return [c for c in df.columns if c not in exclude]

"""
Market regime detection framework.
Detects bull/bear, volatility, trend strength regimes.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
import pandas as pd
import numpy as np
from src.utils.logging import setup_logging

logger = setup_logging("regime.detector")


class RegimeType(Enum):
    """Possible market regime classifications."""
    STRONG_BULL = "strong_bull"
    WEAK_BULL = "weak_bull"
    SIDEWAYS = "sideways"
    WEAK_BEAR = "weak_bear"
    STRONG_BEAR = "strong_bear"


class VolatilityRegime(Enum):
    LOW = "low_vol"
    MEDIUM = "medium_vol"
    HIGH = "high_vol"
    EXTREME = "extreme_vol"


@dataclass
class RegimeState:
    """Current regime assessment."""
    trend_regime: RegimeType
    vol_regime: VolatilityRegime
    trend_strength: float  # 0-1
    volatility_percentile: float  # 0-1
    confidence: float  # 0-1
    timestamp: pd.Timestamp = None

    def is_trending(self) -> bool:
        return self.trend_regime in (RegimeType.STRONG_BULL, RegimeType.STRONG_BEAR)

    def is_high_vol(self) -> bool:
        return self.vol_regime in (VolatilityRegime.HIGH, VolatilityRegime.EXTREME)

    def to_dict(self) -> dict:
        return {
            "trend_regime": self.trend_regime.value,
            "vol_regime": self.vol_regime.value,
            "trend_strength": self.trend_strength,
            "volatility_percentile": self.volatility_percentile,
            "confidence": self.confidence,
            "timestamp": str(self.timestamp) if self.timestamp else None,
        }


class RegimeDetector(ABC):
    """Abstract base for regime detection."""

    name: str = "base"

    @abstractmethod
    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add regime columns to DataFrame. Must not use future data."""
        ...

    @abstractmethod
    def current_regime(self, df: pd.DataFrame) -> RegimeState:
        """Get the current regime state from the latest data."""
        ...


class RuleBasedRegimeDetector(RegimeDetector):
    """
    Simple, interpretable rule-based regime classifier.
    Uses SMA slope, ADX, volatility percentile.
    """

    name = "rule_based"

    def __init__(
        self,
        sma_period: int = 50,
        adx_period: int = 14,
        vol_period: int = 20,
        vol_lookback: int = 252,
    ):
        self.sma_period = sma_period
        self.adx_period = adx_period
        self.vol_period = vol_period
        self.vol_lookback = vol_lookback

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add regime columns to the DataFrame."""
        df = df.copy()

        # Ensure required columns exist
        if f"sma_{self.sma_period}" not in df.columns:
            df[f"sma_{self.sma_period}"] = df["close"].rolling(self.sma_period).mean()
        if "adx" not in df.columns:
            df = self._add_adx(df)
        if f"volatility_{self.vol_period}" not in df.columns:
            log_ret = np.log(df["close"] / df["close"].shift(1))
            df[f"volatility_{self.vol_period}"] = log_ret.rolling(self.vol_period).std() * np.sqrt(252)

        sma = df[f"sma_{self.sma_period}"]
        adx = df.get("adx", pd.Series(25, index=df.index))
        vol = df[f"volatility_{self.vol_period}"]

        # SMA slope (normalized)
        sma_slope = sma.pct_change(5)

        # Price vs SMA
        price_vs_sma = (df["close"] - sma) / sma.replace(0, np.nan)

        # Trend regime
        conditions = [
            (price_vs_sma > 0.02) & (sma_slope > 0.001) & (adx > 25),  # Strong bull
            (price_vs_sma > 0) & (sma_slope > 0),                       # Weak bull
            (price_vs_sma < -0.02) & (sma_slope < -0.001) & (adx > 25), # Strong bear
            (price_vs_sma < 0) & (sma_slope < 0),                       # Weak bear
        ]
        choices = [
            RegimeType.STRONG_BULL.value,
            RegimeType.WEAK_BULL.value,
            RegimeType.STRONG_BEAR.value,
            RegimeType.WEAK_BEAR.value,
        ]
        df["trend_regime"] = np.select(conditions, choices, default=RegimeType.SIDEWAYS.value)

        # Trend strength (0-1 based on ADX)
        df["trend_strength"] = (adx / 50).clip(0, 1)

        # Volatility regime (percentile-based)
        vol_pctile = vol.rolling(self.vol_lookback, min_periods=60).rank(pct=True)
        df["volatility_percentile"] = vol_pctile

        vol_conditions = [
            vol_pctile > 0.9,
            vol_pctile > 0.7,
            vol_pctile > 0.3,
        ]
        vol_choices = [
            VolatilityRegime.EXTREME.value,
            VolatilityRegime.HIGH.value,
            VolatilityRegime.MEDIUM.value,
        ]
        df["vol_regime"] = np.select(vol_conditions, vol_choices, default=VolatilityRegime.LOW.value)

        # Regime confidence (higher ADX = higher confidence in trend classification)
        df["regime_confidence"] = (adx / 40).clip(0.3, 1.0)

        return df

    def current_regime(self, df: pd.DataFrame) -> RegimeState:
        """Get the latest regime state."""
        df = self.detect(df)
        if df.empty:
            return RegimeState(
                trend_regime=RegimeType.SIDEWAYS,
                vol_regime=VolatilityRegime.MEDIUM,
                trend_strength=0.5,
                volatility_percentile=0.5,
                confidence=0.3,
            )

        last = df.iloc[-1]
        return RegimeState(
            trend_regime=RegimeType(last.get("trend_regime", "sideways")),
            vol_regime=VolatilityRegime(last.get("vol_regime", "medium_vol")),
            trend_strength=float(last.get("trend_strength", 0.5)),
            volatility_percentile=float(last.get("volatility_percentile", 0.5)),
            confidence=float(last.get("regime_confidence", 0.5)),
            timestamp=last.get("datetime"),
        )

    def _add_adx(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Add ADX if not present."""
        high, low, close = df["high"], df["low"], df["close"]
        plus_dm = high.diff().clip(lower=0)
        minus_dm = (-low.diff()).clip(lower=0)
        tr = np.maximum(high - low, np.maximum(abs(high - close.shift(1)), abs(low - close.shift(1))))
        atr = tr.rolling(period).mean()
        plus_di = 100 * plus_dm.rolling(period).mean() / atr.replace(0, np.nan)
        minus_di = 100 * minus_dm.rolling(period).mean() / atr.replace(0, np.nan)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
        df["adx"] = dx.rolling(period).mean()
        return df


class VolatilityRegimeDetector(RegimeDetector):
    """Volatility-only regime detector using rolling percentiles."""

    name = "volatility"

    def __init__(self, vol_period: int = 20, lookback: int = 252):
        self.vol_period = vol_period
        self.lookback = lookback

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        log_ret = np.log(df["close"] / df["close"].shift(1))
        realized_vol = log_ret.rolling(self.vol_period).std() * np.sqrt(252)

        vol_pctile = realized_vol.rolling(self.lookback, min_periods=60).rank(pct=True)
        df["realized_vol"] = realized_vol
        df["vol_percentile"] = vol_pctile

        conditions = [vol_pctile > 0.9, vol_pctile > 0.7, vol_pctile > 0.3]
        choices = ["extreme_vol", "high_vol", "medium_vol"]
        df["vol_regime"] = np.select(conditions, choices, default="low_vol")

        return df

    def current_regime(self, df: pd.DataFrame) -> RegimeState:
        df = self.detect(df)
        last = df.iloc[-1]
        return RegimeState(
            trend_regime=RegimeType.SIDEWAYS,
            vol_regime=VolatilityRegime(last.get("vol_regime", "medium_vol")),
            trend_strength=0.5,
            volatility_percentile=float(last.get("vol_percentile", 0.5)),
            confidence=0.7,
            timestamp=last.get("datetime"),
        )

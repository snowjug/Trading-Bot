"""
Strategy base class and signal definitions.
All strategies must implement this interface.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import pandas as pd
import numpy as np
from src.regime.detector import RegimeState
from src.utils.logging import setup_logging

logger = setup_logging("strategies.base")


class SignalDirection(Enum):
    LONG = 1
    SHORT = -1
    FLAT = 0


@dataclass
class Signal:
    """A trading signal with confidence and metadata."""
    symbol: str
    direction: SignalDirection
    confidence: float  # 0.0 to 1.0
    expected_return: float = 0.0
    expected_risk: float = 0.0
    strategy_name: str = ""
    timestamp: datetime = None
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    metadata: dict = field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        """Signal is actionable if confidence exceeds minimum threshold."""
        return self.direction != SignalDirection.FLAT and self.confidence > 0.5


@dataclass
class StrategyResult:
    """Result from running a strategy on historical data."""
    strategy_name: str
    signals: pd.DataFrame  # datetime, symbol, direction, confidence, entry, stop, target
    metadata: dict = field(default_factory=dict)


class Strategy(ABC):
    """
    Abstract base class for all trading strategies.
    
    Every strategy must:
    1. Generate signals based on features and regime
    2. Not use any future information
    3. Include an economic hypothesis for why it works
    4. Be testable and reproducible
    """

    name: str = "base_strategy"
    hypothesis: str = "No hypothesis defined"
    strategy_type: str = "unknown"  # trend, momentum, mean_reversion, breakout, etc.
    min_data_points: int = 200  # Minimum history needed

    @abstractmethod
    def generate_signals(
        self,
        df: pd.DataFrame,
        regime: RegimeState | None = None,
    ) -> pd.DataFrame:
        """
        Generate trading signals from feature-enriched OHLCV data.
        
        Must return DataFrame with columns:
        - datetime
        - signal: -1, 0, 1
        - confidence: 0.0 to 1.0
        - entry_price (optional)
        - stop_loss (optional)
        - take_profit (optional)
        """
        ...

    def validate_inputs(self, df: pd.DataFrame) -> bool:
        """Check that required columns exist."""
        required = {"datetime", "open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            logger.error(f"{self.name}: Missing columns: {missing}")
            return False
        if len(df) < self.min_data_points:
            logger.warning(f"{self.name}: Insufficient data ({len(df)} < {self.min_data_points})")
            return False
        return True

    def get_parameters(self) -> dict:
        """Return all tunable parameters for sensitivity testing."""
        return {}

    def describe(self) -> dict:
        """Return strategy description."""
        return {
            "name": self.name,
            "type": self.strategy_type,
            "hypothesis": self.hypothesis,
            "parameters": self.get_parameters(),
            "min_data_points": self.min_data_points,
        }


# =========================================================================
# BASELINE STRATEGY IMPLEMENTATIONS
# =========================================================================


class SMACrossoverStrategy(Strategy):
    """
    Strategy 1: SMA Crossover Trend Following
    Long when fast SMA > slow SMA, flat otherwise.
    """
    name = "sma_crossover"
    hypothesis = "Price trends persist due to behavioral momentum and institutional herding."
    strategy_type = "trend"

    def __init__(self, fast_period: int = 20, slow_period: int = 50):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.min_data_points = slow_period + 50

    def generate_signals(self, df: pd.DataFrame, regime: RegimeState | None = None) -> pd.DataFrame:
        if not self.validate_inputs(df):
            return pd.DataFrame()

        df = df.copy()
        fast_col = f"sma_{self.fast_period}"
        slow_col = f"sma_{self.slow_period}"

        if fast_col not in df.columns:
            df[fast_col] = df["close"].rolling(self.fast_period).mean()
        if slow_col not in df.columns:
            df[slow_col] = df["close"].rolling(self.slow_period).mean()

        # Signal: fast > slow = long
        df["signal"] = np.where(df[fast_col] > df[slow_col], 1, 0)

        # Confidence based on distance between MAs
        spread = (df[fast_col] - df[slow_col]) / df[slow_col].replace(0, np.nan)
        df["confidence"] = spread.abs().clip(0, 0.1) / 0.1  # Normalize to 0-1

        # Reduce confidence in sideways regime
        if regime and regime.trend_regime.value == "sideways":
            df["confidence"] *= 0.5

        signals = df[["datetime", "signal", "confidence"]].copy()
        signals["strategy"] = self.name
        return signals

    def get_parameters(self) -> dict:
        return {"fast_period": self.fast_period, "slow_period": self.slow_period}


class MomentumStrategy(Strategy):
    """
    Strategy 2: Momentum (N-day return)
    Long when N-day momentum is positive and above threshold.
    """
    name = "momentum"
    hypothesis = "Winners tend to keep winning due to slow information diffusion and behavioral biases."
    strategy_type = "momentum"

    def __init__(self, lookback: int = 20, threshold: float = 0.0):
        self.lookback = lookback
        self.threshold = threshold
        self.min_data_points = lookback + 50

    def generate_signals(self, df: pd.DataFrame, regime: RegimeState | None = None) -> pd.DataFrame:
        if not self.validate_inputs(df):
            return pd.DataFrame()

        df = df.copy()
        mom_col = f"momentum_{self.lookback}"
        if mom_col not in df.columns:
            df[mom_col] = df["close"].pct_change(self.lookback)

        df["signal"] = np.where(df[mom_col] > self.threshold, 1, 0)

        # Confidence based on momentum magnitude
        df["confidence"] = df[mom_col].clip(0, 0.2) / 0.2

        signals = df[["datetime", "signal", "confidence"]].copy()
        signals["strategy"] = self.name
        return signals

    def get_parameters(self) -> dict:
        return {"lookback": self.lookback, "threshold": self.threshold}


class RSIMeanReversionStrategy(Strategy):
    """
    Strategy 3: RSI Mean Reversion
    Buy when RSI < oversold, sell when RSI > overbought.
    """
    name = "rsi_mean_reversion"
    hypothesis = "Extreme short-term moves tend to revert due to liquidity and behavioral overreaction."
    strategy_type = "mean_reversion"

    def __init__(self, rsi_period: int = 14, oversold: float = 30, overbought: float = 70):
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.min_data_points = rsi_period + 50

    def generate_signals(self, df: pd.DataFrame, regime: RegimeState | None = None) -> pd.DataFrame:
        if not self.validate_inputs(df):
            return pd.DataFrame()

        df = df.copy()
        rsi_col = f"rsi_{self.rsi_period}"
        if rsi_col not in df.columns:
            delta = df["close"].diff()
            gain = delta.where(delta > 0, 0.0)
            loss = -delta.where(delta < 0, 0.0)
            avg_gain = gain.ewm(alpha=1/self.rsi_period, min_periods=self.rsi_period, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1/self.rsi_period, min_periods=self.rsi_period, adjust=False).mean()
            rs = avg_gain / avg_loss.replace(0, np.nan)
            df[rsi_col] = 100 - (100 / (1 + rs))

        rsi = df[rsi_col]
        df["signal"] = np.where(rsi < self.oversold, 1, np.where(rsi > self.overbought, -1, 0))

        # Confidence: how extreme the RSI
        df["confidence"] = np.where(
            rsi < self.oversold,
            (self.oversold - rsi) / self.oversold,
            np.where(rsi > self.overbought, (rsi - self.overbought) / (100 - self.overbought), 0.0),
        ).clip(0, 1)

        signals = df[["datetime", "signal", "confidence"]].copy()
        signals["strategy"] = self.name
        return signals

    def get_parameters(self) -> dict:
        return {"rsi_period": self.rsi_period, "oversold": self.oversold, "overbought": self.overbought}


class BollingerMeanReversionStrategy(Strategy):
    """
    Strategy 4: Bollinger Band Mean Reversion
    Buy at lower band, sell at upper band.
    """
    name = "bollinger_mean_reversion"
    hypothesis = "Price tends to revert to the mean after touching statistical extremes."
    strategy_type = "mean_reversion"

    def __init__(self, period: int = 20, num_std: float = 2.0):
        self.period = period
        self.num_std = num_std
        self.min_data_points = period + 50

    def generate_signals(self, df: pd.DataFrame, regime: RegimeState | None = None) -> pd.DataFrame:
        if not self.validate_inputs(df):
            return pd.DataFrame()

        df = df.copy()
        if "bb_upper" not in df.columns:
            mid = df["close"].rolling(self.period).mean()
            std = df["close"].rolling(self.period).std()
            df["bb_upper"] = mid + self.num_std * std
            df["bb_lower"] = mid - self.num_std * std

        df["signal"] = np.where(
            df["close"] < df["bb_lower"], 1,
            np.where(df["close"] > df["bb_upper"], -1, 0)
        )

        # Confidence based on distance beyond band
        bb_range = (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)
        beyond_lower = (df["bb_lower"] - df["close"]).clip(lower=0) / bb_range
        beyond_upper = (df["close"] - df["bb_upper"]).clip(lower=0) / bb_range
        df["confidence"] = (beyond_lower + beyond_upper).clip(0, 1).fillna(0)

        signals = df[["datetime", "signal", "confidence"]].copy()
        signals["strategy"] = self.name
        return signals

    def get_parameters(self) -> dict:
        return {"period": self.period, "num_std": self.num_std}


class DonchianBreakoutStrategy(Strategy):
    """
    Strategy 5: Donchian Channel Breakout
    Buy on breakout above N-day high, sell on breakdown below N-day low.
    """
    name = "donchian_breakout"
    hypothesis = "Breakouts from consolidation ranges signal the start of new trends."
    strategy_type = "breakout"

    def __init__(self, entry_period: int = 20, exit_period: int = 10):
        self.entry_period = entry_period
        self.exit_period = exit_period
        self.min_data_points = entry_period + 50

    def generate_signals(self, df: pd.DataFrame, regime: RegimeState | None = None) -> pd.DataFrame:
        if not self.validate_inputs(df):
            return pd.DataFrame()

        df = df.copy()
        entry_high = df["high"].rolling(self.entry_period).max().shift(1)
        entry_low = df["low"].rolling(self.entry_period).min().shift(1)
        exit_low = df["low"].rolling(self.exit_period).min().shift(1)
        exit_high = df["high"].rolling(self.exit_period).max().shift(1)

        # Signal logic: breakout above entry_high = long, below entry_low = short
        df["signal"] = 0
        df.loc[df["close"] > entry_high, "signal"] = 1
        df.loc[df["close"] < entry_low, "signal"] = -1

        # Confidence based on breakout strength
        range_size = (entry_high - entry_low).replace(0, np.nan)
        breakout_pct = (df["close"] - entry_high).clip(lower=0) / range_size
        breakdown_pct = (entry_low - df["close"]).clip(lower=0) / range_size
        df["confidence"] = (breakout_pct + breakdown_pct).clip(0, 1).fillna(0)

        signals = df[["datetime", "signal", "confidence"]].copy()
        signals["strategy"] = self.name
        return signals

    def get_parameters(self) -> dict:
        return {"entry_period": self.entry_period, "exit_period": self.exit_period}


class VWAPTrendStrategy(Strategy):
    """
    Strategy 6: VWAP Trend
    Long when price is above VWAP with positive slope.
    For daily data, uses rolling VWAP approximation.
    """
    name = "vwap_trend"
    hypothesis = "Institutional order flow anchors around VWAP; sustained deviations indicate directional conviction."
    strategy_type = "trend"

    def __init__(self, period: int = 20):
        self.period = period
        self.min_data_points = period + 50

    def generate_signals(self, df: pd.DataFrame, regime: RegimeState | None = None) -> pd.DataFrame:
        if not self.validate_inputs(df):
            return pd.DataFrame()

        df = df.copy()
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        cumvol = df["volume"].rolling(self.period).sum().replace(0, np.nan)
        df["vwap"] = (typical_price * df["volume"]).rolling(self.period).sum() / cumvol

        # Signal: price above VWAP = bullish
        vwap_dist = (df["close"] - df["vwap"]) / df["vwap"].replace(0, np.nan)
        df["signal"] = np.where(vwap_dist > 0.005, 1, np.where(vwap_dist < -0.005, -1, 0))

        df["confidence"] = vwap_dist.abs().clip(0, 0.05) / 0.05

        signals = df[["datetime", "signal", "confidence"]].copy()
        signals["strategy"] = self.name
        return signals

    def get_parameters(self) -> dict:
        return {"period": self.period}


class DualMomentumStrategy(Strategy):
    """
    Strategy 7: Dual Momentum (Absolute + Relative)
    Long when both absolute momentum (vs risk-free) and relative momentum
    (vs benchmark) are positive.
    """
    name = "dual_momentum"
    hypothesis = "Combining absolute and relative momentum filters noise and captures persistent trends."
    strategy_type = "momentum"

    def __init__(self, lookback: int = 60, rf_annual: float = 0.065):
        self.lookback = lookback
        self.rf_annual = rf_annual  # ~6.5% India T-bill proxy
        self.min_data_points = lookback + 50

    def generate_signals(self, df: pd.DataFrame, regime: RegimeState | None = None) -> pd.DataFrame:
        if not self.validate_inputs(df):
            return pd.DataFrame()

        df = df.copy()
        momentum = df["close"].pct_change(self.lookback)
        rf_period = self.rf_annual * (self.lookback / 252)  # Risk-free return for the lookback period

        # Absolute momentum: return > risk-free
        abs_mom = momentum > rf_period

        # For now, without benchmark data, use absolute momentum only
        df["signal"] = np.where(abs_mom, 1, 0)
        df["confidence"] = ((momentum - rf_period) / 0.1).clip(0, 1)

        signals = df[["datetime", "signal", "confidence"]].copy()
        signals["strategy"] = self.name
        return signals

    def get_parameters(self) -> dict:
        return {"lookback": self.lookback, "rf_annual": self.rf_annual}


class MACDStrategy(Strategy):
    """
    Strategy 8: MACD Crossover
    Long when MACD line crosses above signal line.
    """
    name = "macd_crossover"
    hypothesis = "MACD captures momentum shifts through exponential MA convergence/divergence."
    strategy_type = "momentum"

    def __init__(self, fast: int = 12, slow: int = 26, signal_period: int = 9):
        self.fast = fast
        self.slow = slow
        self.signal_period = signal_period
        self.min_data_points = slow + signal_period + 50

    def generate_signals(self, df: pd.DataFrame, regime: RegimeState | None = None) -> pd.DataFrame:
        if not self.validate_inputs(df):
            return pd.DataFrame()

        df = df.copy()
        if "macd" not in df.columns:
            ema_fast = df["close"].ewm(span=self.fast, adjust=False).mean()
            ema_slow = df["close"].ewm(span=self.slow, adjust=False).mean()
            df["macd"] = ema_fast - ema_slow
            df["macd_signal"] = df["macd"].ewm(span=self.signal_period, adjust=False).mean()
            df["macd_hist"] = df["macd"] - df["macd_signal"]

        # Signal on histogram direction
        df["signal"] = np.where(df["macd_hist"] > 0, 1, np.where(df["macd_hist"] < 0, -1, 0))

        # Confidence based on histogram magnitude
        hist_std = df["macd_hist"].rolling(50).std().replace(0, np.nan)
        df["confidence"] = (df["macd_hist"].abs() / hist_std).clip(0, 2) / 2

        signals = df[["datetime", "signal", "confidence"]].copy()
        signals["strategy"] = self.name
        return signals

    def get_parameters(self) -> dict:
        return {"fast": self.fast, "slow": self.slow, "signal_period": self.signal_period}


class ADXTrendStrategy(Strategy):
    """
    Strategy 9: ADX Trend Strength + Direction
    Trade in trend direction only when ADX confirms strong trend.
    """
    name = "adx_trend"
    hypothesis = "ADX identifies genuine trending markets, filtering out noise during sideways conditions."
    strategy_type = "trend"

    def __init__(self, adx_threshold: float = 25, sma_period: int = 50):
        self.adx_threshold = adx_threshold
        self.sma_period = sma_period
        self.min_data_points = max(50, sma_period) + 50

    def generate_signals(self, df: pd.DataFrame, regime: RegimeState | None = None) -> pd.DataFrame:
        if not self.validate_inputs(df):
            return pd.DataFrame()

        df = df.copy()
        if "adx" not in df.columns:
            # Simplified ADX
            high, low, close = df["high"], df["low"], df["close"]
            tr = np.maximum(high - low, np.maximum(abs(high - close.shift(1)), abs(low - close.shift(1))))
            atr = tr.rolling(14).mean()
            plus_dm = high.diff().clip(lower=0)
            minus_dm = (-low.diff()).clip(lower=0)
            plus_di = 100 * plus_dm.rolling(14).mean() / atr.replace(0, np.nan)
            minus_di = 100 * minus_dm.rolling(14).mean() / atr.replace(0, np.nan)
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
            df["adx"] = dx.rolling(14).mean()
            df["plus_di"] = plus_di
            df["minus_di"] = minus_di

        sma_col = f"sma_{self.sma_period}"
        if sma_col not in df.columns:
            df[sma_col] = df["close"].rolling(self.sma_period).mean()

        # Strong trend + direction from DI
        trending = df["adx"] > self.adx_threshold
        bullish = df["plus_di"] > df["minus_di"]

        df["signal"] = np.where(trending & bullish, 1, np.where(trending & ~bullish, -1, 0))

        # Confidence = ADX normalized
        df["confidence"] = (df["adx"] / 50).clip(0, 1)

        signals = df[["datetime", "signal", "confidence"]].copy()
        signals["strategy"] = self.name
        return signals

    def get_parameters(self) -> dict:
        return {"adx_threshold": self.adx_threshold, "sma_period": self.sma_period}


class MeanReversionGapStrategy(Strategy):
    """
    Strategy 10: Gap Mean Reversion
    Fade large overnight gaps, expecting partial reversion during the day.
    """
    name = "gap_mean_reversion"
    hypothesis = "Overnight gaps often overshoot due to thin liquidity; price partially reverts during regular hours."
    strategy_type = "mean_reversion"

    def __init__(self, gap_threshold: float = 0.015):
        self.gap_threshold = gap_threshold
        self.min_data_points = 50

    def generate_signals(self, df: pd.DataFrame, regime: RegimeState | None = None) -> pd.DataFrame:
        if not self.validate_inputs(df):
            return pd.DataFrame()

        df = df.copy()
        df["gap"] = (df["open"] - df["close"].shift(1)) / df["close"].shift(1).replace(0, np.nan)

        # Fade the gap: gap up → short, gap down → long
        df["signal"] = np.where(
            df["gap"] > self.gap_threshold, -1,
            np.where(df["gap"] < -self.gap_threshold, 1, 0)
        )

        # Confidence based on gap size
        df["confidence"] = (df["gap"].abs() / 0.05).clip(0, 1)

        signals = df[["datetime", "signal", "confidence"]].copy()
        signals["strategy"] = self.name
        return signals

    def get_parameters(self) -> dict:
        return {"gap_threshold": self.gap_threshold}


class VolatilityBreakoutStrategy(Strategy):
    """
    Strategy 11: Volatility Breakout (ATR-based)
    Enter when price moves beyond ATR-based channel from previous close.
    """
    name = "volatility_breakout"
    hypothesis = "Sharp ATR-based breakouts from the previous close signal genuine directional moves."
    strategy_type = "breakout"

    def __init__(self, atr_period: int = 14, atr_multiplier: float = 1.5):
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.min_data_points = atr_period + 50

    def generate_signals(self, df: pd.DataFrame, regime: RegimeState | None = None) -> pd.DataFrame:
        if not self.validate_inputs(df):
            return pd.DataFrame()

        df = df.copy()
        atr_col = f"atr_{self.atr_period}"
        if atr_col not in df.columns:
            tr = np.maximum(
                df["high"] - df["low"],
                np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1)))
            )
            df[atr_col] = tr.rolling(self.atr_period).mean()

        prev_close = df["close"].shift(1)
        upper = prev_close + self.atr_multiplier * df[atr_col]
        lower = prev_close - self.atr_multiplier * df[atr_col]

        df["signal"] = np.where(df["close"] > upper, 1, np.where(df["close"] < lower, -1, 0))

        breakout_dist = np.maximum(
            (df["close"] - upper).clip(lower=0),
            (lower - df["close"]).clip(lower=0),
        ) / df[atr_col].replace(0, np.nan)
        df["confidence"] = breakout_dist.clip(0, 2) / 2

        signals = df[["datetime", "signal", "confidence"]].copy()
        signals["strategy"] = self.name
        return signals

    def get_parameters(self) -> dict:
        return {"atr_period": self.atr_period, "atr_multiplier": self.atr_multiplier}


class ConsecutiveDaysStrategy(Strategy):
    """
    Strategy 12: Consecutive Days Mean Reversion
    Buy after N consecutive down days, sell after N consecutive up days.
    """
    name = "consecutive_days"
    hypothesis = "Streaks of consecutive up/down days tend to exhaust themselves and revert."
    strategy_type = "mean_reversion"

    def __init__(self, n_days: int = 3):
        self.n_days = n_days
        self.min_data_points = 100

    def generate_signals(self, df: pd.DataFrame, regime: RegimeState | None = None) -> pd.DataFrame:
        if not self.validate_inputs(df):
            return pd.DataFrame()

        df = df.copy()
        df["up"] = (df["close"] > df["close"].shift(1)).astype(int)
        df["down"] = (df["close"] < df["close"].shift(1)).astype(int)

        # Count consecutive ups/downs
        df["consec_up"] = df["up"] * (df["up"].groupby((df["up"] != df["up"].shift()).cumsum()).cumcount() + 1)
        df["consec_down"] = df["down"] * (df["down"].groupby((df["down"] != df["down"].shift()).cumsum()).cumcount() + 1)

        # Signal: fade after N consecutive days
        df["signal"] = np.where(
            df["consec_down"] >= self.n_days, 1,
            np.where(df["consec_up"] >= self.n_days, -1, 0)
        )

        # Confidence scales with streak length
        streak = np.maximum(df["consec_up"], df["consec_down"])
        df["confidence"] = ((streak - self.n_days + 1) / 3).clip(0, 1)

        signals = df[["datetime", "signal", "confidence"]].copy()
        signals["strategy"] = self.name
        return signals

    def get_parameters(self) -> dict:
        return {"n_days": self.n_days}


def get_all_baseline_strategies() -> list[Strategy]:
    """Return all baseline strategy instances."""
    return [
        SMACrossoverStrategy(fast_period=20, slow_period=50),
        MomentumStrategy(lookback=20),
        RSIMeanReversionStrategy(rsi_period=14, oversold=30, overbought=70),
        BollingerMeanReversionStrategy(period=20, num_std=2.0),
        DonchianBreakoutStrategy(entry_period=20, exit_period=10),
        VWAPTrendStrategy(period=20),
        DualMomentumStrategy(lookback=60),
        MACDStrategy(),
        ADXTrendStrategy(adx_threshold=25),
        MeanReversionGapStrategy(gap_threshold=0.015),
        VolatilityBreakoutStrategy(atr_period=14, atr_multiplier=1.5),
        ConsecutiveDaysStrategy(n_days=3),
    ]

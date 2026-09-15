"""
Adaptive Regime & Event-Aware Multi-Factor Fusion Strategy.
Combines:
1. Macro/Market Regime (Trend + Realized Volatility filter)
2. Quantitative Momentum & Price Action
3. Machine Learning Confidence Threshold P(return > 0) >= 0.52
4. Event Intelligence & Sentiment overlay
"""

from typing import Dict, Optional
import numpy as np
import pandas as pd

from src.strategies.base import Strategy, SignalDirection
from src.regime.detector import RegimeState, VolatilityRegime, TrendRegime
from src.ml.trainer import MLReturnClassifier
from src.events.store import EventStore
from src.utils.logging import get_logger

logger = get_logger("strategies.adaptive_fusion")


class AdaptiveFusionStrategy(Strategy):
    """
    Institutional Multi-Signal Ensemble:
    Trades only when quantitative momentum is confirmed by favorable market regime,
    statistically verified by ML confidence, and not vetoed by negative news/regulatory events.
    """

    name = "adaptive_regime_ml_fusion"
    strategy_type = "hybrid_ensemble"
    hypothesis = (
        "Multi-layer conditioning (regime filter + momentum signal + ML probability verification + "
        "event risk veto) eliminates false breakouts and significantly reduces tail risk drawdowns."
    )
    min_data_points = 250

    def __init__(
        self,
        lookback_momentum: int = 20,
        ma_filter: int = 50,
        ml_prob_threshold: float = 0.52,
        min_atr_multiple_stop: float = 2.0,
        ml_model: Optional[MLReturnClassifier] = None,
        event_store: Optional[EventStore] = None,
    ):
        self.lookback_momentum = lookback_momentum
        self.ma_filter = ma_filter
        self.ml_prob_threshold = ml_prob_threshold
        self.min_atr_multiple_stop = min_atr_multiple_stop
        self.ml_model = ml_model
        self.event_store = event_store

    def get_parameters(self) -> Dict:
        return {
            "lookback_momentum": self.lookback_momentum,
            "ma_filter": self.ma_filter,
            "ml_prob_threshold": self.ml_prob_threshold,
            "min_atr_multiple_stop": self.min_atr_multiple_stop,
        }

    def generate_signals(
        self,
        df: pd.DataFrame,
        regime: Optional[RegimeState] = None,
    ) -> pd.DataFrame:
        if not self.validate_inputs(df):
            return pd.DataFrame()

        data = df.copy()
        n = len(data)

        # Baseline indicators
        if f"sma_{self.ma_filter}" not in data.columns:
            data[f"sma_{self.ma_filter}"] = data["close"].rolling(self.ma_filter).mean()
        if "atr_14" not in data.columns:
            tr = np.maximum(
                data["high"] - data["low"],
                np.maximum(
                    abs(data["high"] - data["close"].shift(1)),
                    abs(data["low"] - data["close"].shift(1))
                )
            )
            data["atr_14"] = tr.rolling(14).mean()

        data["momentum"] = data["close"] / data["close"].shift(self.lookback_momentum) - 1.0

        signals = np.zeros(n, dtype=int)
        confidences = np.zeros(n, dtype=float)
        stops = np.full(n, np.nan)
        targets = np.full(n, np.nan)

        # Vectorized rule generation for efficiency
        close = data["close"].values
        sma = data[f"sma_{self.ma_filter}"].values
        mom = data["momentum"].values
        atr = data["atr_14"].fillna(0).values

        # Optional ML predictions
        ml_probs = np.full(n, 0.55)  # default prior
        if self.ml_model and self.ml_model.is_trained:
            try:
                X, _ = self.ml_model.prepare_dataset(data)
                # Avoid lookahead by predicting on X
                p_all = self.ml_model.model.predict_proba(X)[:, 1]
                # Align with data index
                valid_idx = X.index
                ml_probs[valid_idx] = p_all
            except Exception as e:
                logger.debug(f"ML prediction skipped: {e}")

        # Regime condition
        regime_bullish = True
        regime_extreme_vol = False
        if regime:
            regime_bullish = regime.trend_regime in [TrendRegime.BULL_STRONG, TrendRegime.BULL_WEAK]
            regime_extreme_vol = regime.vol_regime == VolatilityRegime.HIGH

        for i in range(self.min_data_points, n):
            # 1. Price Momentum Condition
            price_bullish = (close[i] > sma[i]) and (mom[i] > 0.02)
            price_bearish = (close[i] < sma[i]) and (mom[i] < -0.02)

            # 2. Volatility Gate
            if regime_extreme_vol:
                # In high volatility shocks, reduce exposure or abstain
                continue

            # 3. ML Confidence Gate
            prob = ml_probs[i]

            # 4. Long Entry
            if price_bullish and (prob >= self.ml_prob_threshold):
                # Check news sentiment if store exists
                if self.event_store:
                    dt = data["datetime"].iloc[i]
                    sent = self.event_store.get_aggregate_sentiment(dt, lookback_days=3)
                    if sent < -0.4:  # Strong adverse event veto
                        continue

                signals[i] = 1
                confidences[i] = min(1.0, 0.5 + (prob - 0.5) + (mom[i] * 2))
                stops[i] = close[i] - (self.min_atr_multiple_stop * atr[i])
                targets[i] = close[i] + (self.min_atr_multiple_stop * 2.0 * atr[i])

            # 5. Exit / Bearish condition
            elif price_bearish or (close[i] < sma[i]):
                signals[i] = 0  # Flat (delivery mode for equities)
                confidences[i] = 0.5

        result_df = pd.DataFrame({
            "datetime": data["datetime"],
            "signal": signals,
            "confidence": np.round(confidences, 3),
            "entry_price": data["close"],
            "stop_loss": stops,
            "take_profit": targets,
        })
        return result_df

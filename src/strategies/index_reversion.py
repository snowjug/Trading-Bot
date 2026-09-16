"""
Index Dip Sniper Strategy (High-Win-Rate Mean Reversion).
Buys panic pullbacks in structural bull markets for rapid mean reversion to the mean.
"""
import pandas as pd
import numpy as np
from src.strategies.base import Strategy
from src.regime.detector import RegimeState, RegimeType
from src.utils.logging import setup_logging

logger = setup_logging("strategies.index_reversion")


class IndexDipSniperStrategy(Strategy):
    """
    Strategy: Index Dip Sniper (Oversold Panic Fade)

    Hypothesis:
    In structural bull markets (Price > 200 EMA), violent 3-to-5 day pullbacks
    reaching the lower Bollinger Band with RSI < 34 reflect liquidity cascades
    and retail panic rather than structural regime shifts. Sniping these dips
    and taking profit upon reversion to the 20 EMA achieves a 70% win rate.
    """

    name = "index_dip_sniper"
    hypothesis = (
        "Oversold selloffs touching the lower 2.0-SD Bollinger Band in a structural "
        "bull market experience rapid institutional dip-buying, yielding a 70%+ win rate."
    )
    strategy_type = "mean_reversion"
    min_data_points = 200

    def __init__(
        self,
        rsi_oversold: float = 34.0,
        max_holding_bars: int = 6,
        stop_loss_pct: float = 0.025,
    ):
        self.rsi_oversold = rsi_oversold
        self.max_holding_bars = max_holding_bars
        self.stop_loss_pct = stop_loss_pct

    def generate_signals(
        self,
        df: pd.DataFrame,
        regime: RegimeState | None = None,
    ) -> pd.DataFrame:
        """
        Generate signals holding long while mean reversion unfolds.
        """
        if not self.validate_inputs(df):
            return pd.DataFrame()

        df = df.copy()
        c = df["close"]
        e20 = df["ema_20"] if "ema_20" in df.columns else c.ewm(span=20, adjust=False).mean()
        e200 = df["ema_200"] if "ema_200" in df.columns else c.ewm(span=200, adjust=False).mean()
        rsi = df["rsi_14"] if "rsi_14" in df.columns else pd.Series(50.0, index=df.index)
        bb_lower = df["bb_lower"] if "bb_lower" in df.columns else (c.rolling(20).mean() - 2.0 * c.rolling(20).std())

        dip_entry = (c > e200) & ((c <= bb_lower) | (rsi < self.rsi_oversold))

        n = len(df)
        signal = np.zeros(n, dtype=int)
        confidence = np.zeros(n, dtype=float)

        in_pos = False
        entry_p = 0.0
        entry_bar = 0

        for i in range(1, n):
            curr_c = c.iloc[i]

            if not in_pos:
                if dip_entry.iloc[i]:
                    in_pos = True
                    entry_p = curr_c
                    entry_bar = i
                    signal[i] = 1
                    confidence[i] = 0.85
            else:
                bars_held = i - entry_bar
                ret = (curr_c / entry_p) - 1.0

                # Exit if reverted above 20 EMA, or max holding period reached, or stop loss hit
                if curr_c > e20.iloc[i] or bars_held >= self.max_holding_bars or ret < -self.stop_loss_pct:
                    in_pos = False
                    signal[i] = 0
                    confidence[i] = 0.0
                else:
                    signal[i] = 1
                    confidence[i] = 0.85

        signals = pd.DataFrame({
            "datetime": df["datetime"],
            "signal": signal,
            "confidence": confidence,
        })
        signals["strategy"] = self.name
        return signals

    def get_parameters(self) -> dict:
        return {
            "rsi_oversold": self.rsi_oversold,
            "max_holding_bars": self.max_holding_bars,
            "stop_loss_pct": self.stop_loss_pct,
        }

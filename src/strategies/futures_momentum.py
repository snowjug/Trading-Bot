"""
BANK NIFTY Trend Acceleration Strategy (Leveraged Futures / Deep ITM Options).
Captures large directional moves in the high-beta banking sector with trailing risk control.
"""
import pandas as pd
import numpy as np
from src.strategies.base import Strategy
from src.regime.detector import RegimeState, RegimeType
from src.deriv.futures_engine import FuturesMarginEngine
from src.utils.logging import setup_logging

logger = setup_logging("strategies.futures_momentum")


class BankNiftyTrendFuturesStrategy(Strategy):
    """
    Strategy: BANK NIFTY Trend Acceleration (Leveraged Futures)

    Hypothesis:
    BANK NIFTY displays high trending persistence when Price > 20 EMA > 50 EMA
    and RSI > 54 due to institutional banking sector capital concentration.
    Riding these trends with 3.0x conservative F&O leverage and 2.0 ATR trailing
    stops generates high alpha with asymmetric risk/reward.
    """

    name = "banknifty_trend_futures"
    hypothesis = (
        "High-beta BANK NIFTY displays extreme trend continuation during Stage-2 "
        "expansions; leveraged futures execution with 2.0 ATR trailing stops unlocks "
        "superior CAGR with controlled drawdown."
    )
    strategy_type = "futures_trend"
    min_data_points = 200

    def __init__(
        self,
        leverage: float = 3.0,
        trail_atr: float = 2.0,
        rsi_min: float = 54.0,
        capital_allocation: float = 0.45,
    ):
        self.leverage = leverage
        self.trail_atr = trail_atr
        self.rsi_min = rsi_min
        self.capital_allocation = capital_allocation

    def generate_signals(
        self,
        df: pd.DataFrame,
        regime: RegimeState | None = None,
    ) -> pd.DataFrame:
        """
        Generate continuous trend signals for BANK NIFTY.
        """
        if not self.validate_inputs(df):
            return pd.DataFrame()

        df = df.copy()
        c = df["close"]
        e20 = df["ema_20"] if "ema_20" in df.columns else c.ewm(span=20, adjust=False).mean()
        e50 = df["ema_50"] if "ema_50" in df.columns else c.ewm(span=50, adjust=False).mean()
        rsi = df["rsi_14"] if "rsi_14" in df.columns else pd.Series(50.0, index=df.index)
        atr = df["atr_14"] if "atr_14" in df.columns else (df["high"] - df["low"]).rolling(14).mean()

        trend_entry = (c > e20) & (e20 > e50) & (rsi >= self.rsi_min)

        n = len(df)
        signal = np.zeros(n, dtype=int)
        confidence = np.zeros(n, dtype=float)

        in_pos = False
        highest_c = 0.0

        for i in range(1, n):
            curr_c = c.iloc[i]
            curr_a = atr.iloc[i] if not np.isnan(atr.iloc[i]) and atr.iloc[i] > 0 else curr_c * 0.015

            if not in_pos:
                if trend_entry.iloc[i]:
                    in_pos = True
                    highest_c = curr_c
                    signal[i] = 1
                    confidence[i] = min(0.95, 0.5 + float(rsi.iloc[i] / 100.0))
            else:
                highest_c = max(highest_c, curr_c)
                trail_stop = highest_c - (self.trail_atr * curr_a)

                if curr_c < trail_stop or curr_c < e50.iloc[i]:
                    in_pos = False
                    signal[i] = 0
                    confidence[i] = 0.0
                else:
                    signal[i] = 1
                    confidence[i] = min(0.95, 0.5 + float(rsi.iloc[i] / 100.0))

        signals = pd.DataFrame({
            "datetime": df["datetime"],
            "signal": signal,
            "confidence": confidence,
        })
        signals["strategy"] = self.name
        return signals

    def get_parameters(self) -> dict:
        return {
            "leverage": self.leverage,
            "trail_atr": self.trail_atr,
            "rsi_min": self.rsi_min,
            "capital_allocation": self.capital_allocation,
        }

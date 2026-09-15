"""
Price-based technical features.
All features are computed point-in-time — no future information leakage.
"""
import pandas as pd
import numpy as np
from src.utils.logging import setup_logging

logger = setup_logging("features.price")


class PriceFeatures:
    """Compute price-based features from OHLCV data."""

    @staticmethod
    def compute_all(df: pd.DataFrame) -> pd.DataFrame:
        """Compute all price features. Input must have: datetime, open, high, low, close, volume."""
        df = df.copy()
        df = df.sort_values("datetime").reset_index(drop=True)

        # Returns
        df["return_1d"] = df["close"].pct_change(1)
        df["return_5d"] = df["close"].pct_change(5)
        df["return_10d"] = df["close"].pct_change(10)
        df["return_20d"] = df["close"].pct_change(20)
        df["log_return_1d"] = np.log(df["close"] / df["close"].shift(1))

        # Moving averages
        for w in [5, 10, 20, 50, 100, 200]:
            df[f"sma_{w}"] = df["close"].rolling(w).mean()
            df[f"ema_{w}"] = df["close"].ewm(span=w, adjust=False).mean()

        # Price relative to MAs
        for w in [20, 50, 200]:
            df[f"close_vs_sma_{w}"] = (df["close"] / df[f"sma_{w}"]) - 1

        # Bollinger Bands (20, 2)
        df["bb_mid"] = df["sma_20"]
        df["bb_std"] = df["close"].rolling(20).std()
        df["bb_upper"] = df["bb_mid"] + 2 * df["bb_std"]
        df["bb_lower"] = df["bb_mid"] - 2 * df["bb_std"]
        df["bb_pct"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"].replace(0, np.nan)

        # ATR (Average True Range)
        df["tr"] = np.maximum(
            df["high"] - df["low"],
            np.maximum(
                abs(df["high"] - df["close"].shift(1)),
                abs(df["low"] - df["close"].shift(1)),
            ),
        )
        for w in [14, 20]:
            df[f"atr_{w}"] = df["tr"].rolling(w).mean()
            df[f"atr_pct_{w}"] = df[f"atr_{w}"] / df["close"].replace(0, np.nan)

        # RSI
        for w in [14, 21]:
            df[f"rsi_{w}"] = PriceFeatures._compute_rsi(df["close"], w)

        # MACD
        ema12 = df["close"].ewm(span=12, adjust=False).mean()
        ema26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = ema12 - ema26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]

        # ADX (Average Directional Index)
        df = PriceFeatures._compute_adx(df, period=14)

        # Donchian Channel
        for w in [20, 50]:
            df[f"donchian_high_{w}"] = df["high"].rolling(w).max()
            df[f"donchian_low_{w}"] = df["low"].rolling(w).min()
            df[f"donchian_mid_{w}"] = (df[f"donchian_high_{w}"] + df[f"donchian_low_{w}"]) / 2
            df[f"donchian_pct_{w}"] = (df["close"] - df[f"donchian_low_{w}"]) / (
                df[f"donchian_high_{w}"] - df[f"donchian_low_{w}"]
            ).replace(0, np.nan)

        # Momentum
        for w in [5, 10, 20, 60]:
            df[f"momentum_{w}"] = df["close"] / df["close"].shift(w) - 1

        # Volatility
        for w in [10, 20, 60]:
            df[f"volatility_{w}"] = df["log_return_1d"].rolling(w).std() * np.sqrt(252)

        # Gap
        df["gap_pct"] = (df["open"] - df["close"].shift(1)) / df["close"].shift(1).replace(0, np.nan)

        # Trend slope (linear regression slope of close over window)
        for w in [20, 50]:
            df[f"trend_slope_{w}"] = PriceFeatures._rolling_slope(df["close"], w)

        # Range
        df["daily_range_pct"] = (df["high"] - df["low"]) / df["close"].replace(0, np.nan)

        return df

    @staticmethod
    def _compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
        """Compute RSI."""
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _compute_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Compute ADX, +DI, -DI."""
        high = df["high"]
        low = df["low"]
        close = df["close"]

        plus_dm = high.diff()
        minus_dm = -low.diff()

        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

        tr = df["tr"] if "tr" in df.columns else np.maximum(
            high - low,
            np.maximum(abs(high - close.shift(1)), abs(low - close.shift(1))),
        )

        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr.replace(0, np.nan))
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr.replace(0, np.nan))

        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
        df["adx"] = dx.rolling(period).mean()
        df["plus_di"] = plus_di
        df["minus_di"] = minus_di

        return df

    @staticmethod
    def _rolling_slope(series: pd.Series, window: int) -> pd.Series:
        """Compute rolling linear regression slope (normalized)."""
        def slope_func(x):
            if len(x) < window:
                return np.nan
            y = x.values
            t = np.arange(len(y))
            try:
                coef = np.polyfit(t, y, 1)
                return coef[0] / np.mean(y) if np.mean(y) != 0 else np.nan
            except Exception:
                return np.nan

        return series.rolling(window).apply(slope_func, raw=False)

"""
Unit tests for Micro-Capital (₹10,000) Options Buying Strategies:
- Strategy 3: Confluence Gamma Scalper (src/strategies/confluence_scalper.py)
- Strategy 4: Golden Micro-Trend Option Buyer (src/strategies/golden_trend_buyer.py)
- Strategy 4b: Gold Macro Trend Rider (src/strategies/gold_trend_rider.py)
"""
import pytest
import pandas as pd
import numpy as np
from src.strategies.confluence_scalper import ConfluenceGammaScalperStrategy
from src.strategies.golden_trend_buyer import GoldenTrendOptionBuyerStrategy
from src.strategies.gold_trend_rider import GoldMacroTrendStrategy


def create_synthetic_nifty(n_bars: int = 150) -> pd.DataFrame:
    """Generate synthetic Nifty OHLCV with a squeeze and subsequent breakout."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="B")
    
    base = 22000.0
    returns = np.random.normal(0.0003, 0.005, n_bars)
    returns[40:60] = np.random.normal(0.0001, 0.001, 20)  # Squeeze phase
    returns[60:70] = np.random.normal(0.008, 0.002, 10)   # Breakout surge
    
    price = base * np.cumprod(1 + returns)
    high = price * (1 + np.random.uniform(0.002, 0.008, n_bars))
    low = price * (1 - np.random.uniform(0.002, 0.008, n_bars))
    open_p = (price + np.random.uniform(-10, 10, n_bars))
    volume = np.random.randint(150000, 300000, n_bars)
    volume[60:70] = volume[60:70] * 2  # Volume surge on breakout
    
    return pd.DataFrame({
        "datetime": dates,
        "open": open_p,
        "high": high,
        "low": low,
        "close": price,
        "volume": volume,
    })


def create_synthetic_gold(n_bars: int = 400) -> pd.DataFrame:
    """Generate synthetic daily Gold ETF bars over 400 days."""
    np.random.seed(101)
    dates = pd.date_range("2023-01-01", periods=n_bars, freq="B")
    
    drift = 0.0006
    vol = 0.008
    returns = np.random.normal(drift, vol, n_bars)
    price = 50.0 * np.cumprod(1 + returns)
    price[100] = 0.52  # Data glitch
    
    high = price * 1.005
    low = price * 0.995
    open_p = price * 1.001
    volume = np.random.randint(500000, 2000000, n_bars)
    
    return pd.DataFrame({
        "datetime": dates,
        "open": open_p,
        "high": high,
        "low": low,
        "close": price,
        "volume": volume,
    })


# ---------------------------------------------------------------------------
# Strategy 3: Confluence Gamma Scalper Tests
# ---------------------------------------------------------------------------

def test_confluence_scalper_indicators():
    strategy = ConfluenceGammaScalperStrategy()
    df = create_synthetic_nifty(100)
    calc_df = strategy.compute_indicators(df)

    assert "ema_9" in calc_df.columns
    assert "ema_20" in calc_df.columns
    assert "ema_50" in calc_df.columns
    assert "vwap_20" in calc_df.columns
    assert "bb_upper" in calc_df.columns
    assert "bb_lower" in calc_df.columns
    assert "bb_squeeze" in calc_df.columns
    assert "rsi_14" in calc_df.columns
    assert len(calc_df) == 100


def test_confluence_scalper_signals():
    strategy = ConfluenceGammaScalperStrategy()
    df = create_synthetic_nifty(120)
    signals_df = strategy.generate_signals(df)

    assert "datetime" in signals_df.columns
    assert "signal" in signals_df.columns
    assert "confidence" in signals_df.columns
    assert set(signals_df["signal"].unique()).issubset({-1, 0, 1})


def test_confluence_scalper_simulation():
    strategy = ConfluenceGammaScalperStrategy(initial_capital=10000.0)
    df = create_synthetic_nifty(150)
    res = strategy.run_simulation(df)

    assert "initial_capital" in res
    assert res["initial_capital"] == 10000.0
    assert "final_capital" in res
    assert "win_rate" in res
    assert "total_trades" in res
    assert res["final_capital"] > 0


# ---------------------------------------------------------------------------
# Strategy 4: Golden Micro-Trend Option Buyer Tests
# ---------------------------------------------------------------------------

def test_golden_trend_buyer_indicators():
    strategy = GoldenTrendOptionBuyerStrategy()
    df = create_synthetic_nifty(100)
    calc_df = strategy.compute_indicators(df)

    assert "ema_9" in calc_df.columns
    assert "ema_20" in calc_df.columns
    assert "ema_50" in calc_df.columns
    assert "vwap_20" in calc_df.columns
    assert "atr_14" in calc_df.columns
    assert "rsi_14" in calc_df.columns


def test_golden_trend_buyer_signals():
    strategy = GoldenTrendOptionBuyerStrategy()
    df = create_synthetic_nifty(120)
    signals_df = strategy.generate_signals(df)

    assert "datetime" in signals_df.columns
    assert "signal" in signals_df.columns
    assert "confidence" in signals_df.columns
    assert set(signals_df["signal"].unique()).issubset({-1, 0, 1})


def test_golden_trend_buyer_simulation():
    strategy = GoldenTrendOptionBuyerStrategy(initial_capital=10000.0)
    df = create_synthetic_nifty(150)
    res = strategy.run_simulation(df)

    assert "initial_capital" in res
    assert res["initial_capital"] == 10000.0
    assert "final_capital" in res
    assert "win_rate" in res
    assert "target_hits" in res
    assert res["final_capital"] > 0


# ---------------------------------------------------------------------------
# Strategy 4b: Gold Macro Trend Rider Tests
# ---------------------------------------------------------------------------

def test_gold_clean_data_glitch():
    strategy = GoldMacroTrendStrategy()
    df = create_synthetic_gold(150)
    cleaned = strategy.clean_gold_data(df)

    assert cleaned.loc[100, "close"] > 5.0
    assert (cleaned["close"] > 10.0).all()


def test_gold_resample_weekly():
    strategy = GoldMacroTrendStrategy()
    df = create_synthetic_gold(200)
    weekly = strategy.resample_to_weekly(df)

    assert "ema_fast" in weekly.columns
    assert "ema_slow" in weekly.columns
    assert "sma_macro" in weekly.columns
    assert len(weekly) < len(df)


def test_gold_simulation():
    strategy = GoldMacroTrendStrategy(initial_capital=10000.0)
    df = create_synthetic_gold(350)
    res = strategy.run_simulation(df)

    assert "initial_capital" in res
    assert res["initial_capital"] == 10000.0
    assert "final_capital" in res
    assert res["final_capital"] > 5000.0

"""
Unit tests for Strategy 5: Active Dual-Index Momentum Option Scalper (3-5 trades/week).
"""
import pytest
import pandas as pd
import numpy as np
from src.strategies.active_momentum_scalper import ActiveMomentumOptionScalperStrategy


def create_synthetic_bars(n_bars: int = 250, seed: int = 42, base_price: float = 22000.0) -> pd.DataFrame:
    """Generate synthetic daily OHLCV bars."""
    np.random.seed(seed)
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="B")
    
    returns = np.random.normal(0.0004, 0.008, n_bars)
    price = base_price * np.cumprod(1 + returns)
    high = price * (1 + np.random.uniform(0.003, 0.012, n_bars))
    low = price * (1 - np.random.uniform(0.003, 0.012, n_bars))
    open_p = price * (1 + np.random.uniform(-0.005, 0.005, n_bars))
    volume = np.random.randint(200000, 500000, n_bars)
    
    return pd.DataFrame({
        "datetime": dates,
        "open": open_p,
        "high": high,
        "low": low,
        "close": price,
        "volume": volume,
    })


def test_active_scalper_indicators():
    strategy = ActiveMomentumOptionScalperStrategy()
    df = create_synthetic_bars(100)
    calc_df = strategy.compute_indicators(df)

    assert "ema_9" in calc_df.columns
    assert "ema_20" in calc_df.columns
    assert "atr_14" in calc_df.columns
    assert "rsi_14" in calc_df.columns
    assert len(calc_df) == 100


def test_active_scalper_signals():
    strategy = ActiveMomentumOptionScalperStrategy()
    df = create_synthetic_bars(120)
    signals_df = strategy.generate_signals(df)

    assert "datetime" in signals_df.columns
    assert "signal" in signals_df.columns
    assert "confidence" in signals_df.columns
    assert set(signals_df["signal"].unique()).issubset({-1, 0, 1})


def test_active_scalper_single_simulation():
    strategy = ActiveMomentumOptionScalperStrategy(initial_capital=10000.0)
    df = create_synthetic_bars(150)
    trades = strategy.run_single_simulation(df, symbol="NIFTY", lot_default=50)

    assert isinstance(trades, list)
    assert len(trades) > 0
    first_trade = trades[0]
    assert "date" in first_trade
    assert "option_type" in first_trade
    assert "net_pnl" in first_trade
    assert "exit_reason" in first_trade


def test_active_scalper_dual_simulation():
    strategy = ActiveMomentumOptionScalperStrategy(initial_capital=10000.0)
    nifty_df = create_synthetic_bars(200, seed=42, base_price=22000.0)
    bank_df = create_synthetic_bars(200, seed=101, base_price=48000.0)

    res = strategy.run_simulation(nifty_df, bank_df)

    assert "initial_capital" in res
    assert res["initial_capital"] == 10000.0
    assert "final_capital" in res
    assert "trades_per_week" in res
    assert "win_rate" in res
    assert "total_friction_paid" in res
    assert res["total_trades"] > 50
    assert res["final_capital"] > 0

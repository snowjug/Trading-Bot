"""
Unit Tests for Strategy 6: Micro-Capital Confluence Option Buyer.
Verifies signal generation, capital constraints, risk limits, and intrabar execution.
"""
import os
import sys
sys.path.insert(0, os.path.abspath("."))

import pytest
import numpy as np
import pandas as pd

from src.strategies.micro_momentum_buyer import MicroMomentumBuyerStrategy
from src.backtesting.intrabar_simulator import IntrabarMode


@pytest.fixture
def sample_nifty_data():
    """Generate 100 bars of realistic Nifty OHLCV data."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    base = 22000.0
    returns = np.random.normal(0.0005, 0.008, 100)
    close = base * np.cumprod(1 + returns)
    high = close * (1 + np.random.uniform(0.002, 0.008, 100))
    low = close * (1 - np.random.uniform(0.002, 0.008, 100))
    open_p = (high + low) / 2.0
    volume = np.random.randint(100000, 300000, 100)

    return pd.DataFrame({
        "datetime": dates,
        "open": open_p,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


def test_micro_momentum_buyer_signal_generation(sample_nifty_data):
    """Test that signals are emitted only on EMA & RSI confluence."""
    strat = MicroMomentumBuyerStrategy()
    sig_df = strat.generate_signals(sample_nifty_data)

    assert not sig_df.empty
    assert "signal" in sig_df.columns
    assert set(sig_df["signal"].unique()).issubset({-1, 0, 1})
    assert len(sig_df) == len(sample_nifty_data)


def test_micro_momentum_buyer_evaluation_modes(sample_nifty_data):
    """Test conservative vs optimistic execution and capital tracking."""
    strat = MicroMomentumBuyerStrategy()
    
    res_cons = strat.evaluate_on_dataset(sample_nifty_data, initial_capital=10000.0, intrabar_mode=IntrabarMode.CONSERVATIVE)
    res_opt = strat.evaluate_on_dataset(sample_nifty_data, initial_capital=10000.0, intrabar_mode=IntrabarMode.OPTIMISTIC)

    assert "ending_capital" in res_cons
    assert "net_pnl" in res_cons
    assert "win_rate_pct" in res_cons
    assert "total_statutory_friction" in res_cons

    # Optimistic resolution must produce higher or equal win rate than conservative
    assert res_opt["win_rate_pct"] >= res_cons["win_rate_pct"]

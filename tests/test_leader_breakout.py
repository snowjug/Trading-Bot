"""Unit tests for LeaderBreakoutStrategy and multi-stock high-alpha portfolio logic."""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.strategies.leader_breakout import LeaderBreakoutStrategy
from src.features.price_features import PriceFeatures


@pytest.fixture
def sample_market_data():
    """Create 300 days of trending synthetic OHLCV data."""
    dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(300)]
    prices = 100.0 * np.cumprod(1 + np.random.normal(0.002, 0.015, 300))
    df = pd.DataFrame({
        "datetime": dates,
        "open": prices * 0.995,
        "high": prices * 1.015,
        "low": prices * 0.985,
        "close": prices,
        "volume": np.random.randint(100000, 500000, 300),
    })
    df = PriceFeatures.compute_all(df)
    df["relative_volume_20"] = 1.3
    df["dist_from_ath"] = -0.05
    return df


def test_leader_breakout_initialization():
    strat = LeaderBreakoutStrategy(mom_period=60, trail_atr=2.5)
    params = strat.get_parameters()
    assert params["mom_period"] == 60
    assert params["trail_atr"] == 2.5
    assert strat.name == "leader_breakout"
    assert strat.strategy_type == "high_alpha_momentum"


def test_leader_breakout_signal_generation(sample_market_data):
    strat = LeaderBreakoutStrategy()
    signals = strat.generate_signals(sample_market_data)
    assert not signals.empty
    assert "signal" in signals.columns
    assert "confidence" in signals.columns
    assert set(signals["signal"].unique()).issubset({0, 1})
    assert len(signals) == len(sample_market_data)


def test_leader_breakout_portfolio_simulation(sample_market_data):
    strat = LeaderBreakoutStrategy()
    idx_df = sample_market_data.copy()
    universe = {
        "STOCK_A": sample_market_data.copy(),
        "STOCK_B": sample_market_data.copy(),
    }
    res = strat.simulate_universe_portfolio(
        universe, idx_df, n_positions=2, initial_capital=1000000.0
    )
    assert "total_return_pct" in res
    assert "cagr" in res
    assert "sharpe_ratio" in res
    assert "max_drawdown_pct" in res
    assert "trades" in res

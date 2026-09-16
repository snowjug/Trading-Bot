"""Unit tests for Strategy 2: CurvatureCreditSpreadStrategy (Zen Credit Model)."""

import pytest
import numpy as np
import pandas as pd
from src.strategies.curvature_credit_spread import CurvatureCreditSpreadStrategy


def _create_dummy_df(n_bars: int = 250, base_price: float = 22000.0) -> pd.DataFrame:
    dates = pd.date_range("2023-01-01", periods=n_bars, freq="B")
    np.random.seed(42)
    prices = base_price * (1.0 + np.cumsum(np.random.normal(0.0005, 0.008, n_bars)))

    df = pd.DataFrame({
        "datetime": dates,
        "open": prices * 0.998,
        "high": prices * 1.006,
        "low": prices * 0.994,
        "close": prices,
        "volume": np.random.randint(100000, 500000, n_bars),
    })
    df["rsi_14"] = 52.0
    df["vix"] = 14.5
    return df


def test_curvature_spread_initialization():
    strat = CurvatureCreditSpreadStrategy(short_sd=1.3, max_lots=20)
    params = strat.get_parameters()
    assert params["short_sd"] == 1.3
    assert params["max_lots"] == 20
    assert strat.name == "curvature_credit_spread"


def test_curvature_spread_signals():
    df = _create_dummy_df(250)
    strat = CurvatureCreditSpreadStrategy()
    signals = strat.generate_signals(df)
    assert not signals.empty
    assert "signal" in signals.columns
    assert set(signals["signal"].unique()).issubset({0, 1})


def test_curvature_spread_simulation():
    nifty = _create_dummy_df(260, base_price=22000.0)
    vix = pd.DataFrame({
        "datetime": nifty["datetime"],
        "close": 14.0,
    })
    res = CurvatureCreditSpreadStrategy.simulate_curvature_fund(
        nifty_df=nifty,
        vix_df=vix,
        initial_capital=100000.0,
        max_lots=5,
    )
    assert "win_rate" in res
    assert "cagr" in res
    assert "sharpe_ratio" in res
    assert "max_drawdown_pct" in res
    assert "final_capital" in res
    assert res["initial_capital"] == 100000.0
    assert len(res["equity_curve"]) > 0

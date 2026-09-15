"""Unit tests for Regime Detector, Paper Execution, and Safety Constraints."""

import pytest
import numpy as np
import pandas as pd
from src.config import Config
from src.regime.detector import RuleBasedRegimeDetector
from src.execution.paper_broker import PaperBroker, Order, OrderSide
from src.execution.paper_engine import PaperExecutionEngine
from src.strategies.base import DualMomentumStrategy


def test_safety_live_trading_disabled():
    assert Config.LIVE_TRADING_ENABLED is False
    # Calling assert_no_live_trading should succeed without raising
    Config.assert_no_live_trading()


def test_paper_broker_execution(tmp_path):
    broker = PaperBroker(initial_capital=500_000.0, state_dir=tmp_path)
    order = Order(
        order_id="",
        symbol="INFY",
        side=OrderSide.BUY,
        quantity=50,
        price=1800.0,
        order_type="MARKET",
    )
    filled = broker.place_order(order)
    assert filled.status.value == "filled"
    assert filled.filled_quantity == 50
    assert len(broker.get_positions()) == 1
    assert broker.positions["INFY"].quantity == 50
    # Cash should decrease by position cost
    assert broker.cash < 500_000.0



def test_regime_detection():
    detector = RuleBasedRegimeDetector()

    np.random.seed(42)
    # Generate 250 bars
    dates = pd.date_range("2022-01-01", periods=250, freq="B")
    close = 1000.0 + np.cumsum(np.random.normal(1.0, 5.0, 250))
    df = pd.DataFrame({
        "datetime": dates,
        "open": close * 0.99,
        "high": close * 1.01,
        "low": close * 0.98,
        "close": close,
        "volume": np.random.randint(100000, 500000, 250),
    })

    regime = detector.current_regime(df)
    assert regime.vol_regime is not None
    assert regime.trend_regime is not None

"""Unit tests for Quantitative Risk Engine & Kill Switch."""

import pytest
from src.risk.risk_engine import RiskEngine


def test_position_sizing():
    risk = RiskEngine()
    capital = 1_000_000.0
    price = 2_000.0
    atr = 40.0

    qty = risk.calculate_position_size(capital, price, atr, confidence=0.8)
    assert qty > 0
    # Total position value should not exceed max allocation limit (e.g. 15-20%)
    pos_value = qty * price
    assert pos_value <= capital * 0.25


def test_kill_switch_activation():
    risk = RiskEngine()
    capital = 1_000_000.0

    # Normal state allows trading
    assert risk.can_trade(capital) is True

    # Manual kill switch triggers halt
    risk.trip_kill_switch("High unexpected API slippage")
    assert risk.can_trade(capital) is False

    # Reset allows resumption
    risk.reset_kill_switch()
    assert risk.can_trade(capital) is True


def test_drawdown_limit_breach():
    risk = RiskEngine()
    initial_cap = 1_000_000.0
    risk.state.peak_equity = initial_cap

    # 16% drawdown breach (down to 840,000 against 1,000,000)
    current_equity = 840_000.0
    can_trade = risk.can_trade(current_equity)
    assert can_trade is False


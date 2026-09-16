"""Unit tests for Indian Market Friction & Cost Models."""

import pytest
from datetime import datetime
from src.backtesting.cost_model import (
    IndianCostModel, CostScenario, OrderType, SlippageModelType
)


def test_cost_model_scenarios():
    base_model = IndianCostModel(CostScenario.BASE)
    optimistic_model = IndianCostModel(CostScenario.OPTIMISTIC)
    stress_model = IndianCostModel(CostScenario.STRESS)

    base_cost = base_model.round_trip_cost_pct(order_type=OrderType.INTRADAY)
    opt_cost = optimistic_model.round_trip_cost_pct(order_type=OrderType.INTRADAY)
    stress_cost = stress_model.round_trip_cost_pct(order_type=OrderType.INTRADAY)

    assert stress_cost > base_cost > opt_cost
    assert opt_cost > 0


def test_delivery_vs_intraday_stt():
    model = IndianCostModel(CostScenario.BASE)
    trade_value = 100_000.0  # Rs 1 Lakh

    # Delivery sell vs Intraday sell
    cost_del_sell = model.compute_cost(trade_value=trade_value, order_type=OrderType.DELIVERY, is_buy=False)
    cost_intra_sell = model.compute_cost(trade_value=trade_value, order_type=OrderType.INTRADAY, is_buy=False)

    # STT on delivery sell (0.1% = 100) vs intraday sell (0.025% = 25)
    assert cost_del_sell.stt > cost_intra_sell.stt
    assert cost_del_sell.total > cost_intra_sell.total


def test_brokerage_cap():
    model = IndianCostModel(CostScenario.BASE)
    trade_value = 10_000_000.0
    cost = model.compute_cost(trade_value=trade_value, order_type=OrderType.DELIVERY, is_buy=True)
    assert cost.brokerage <= 20.0


def test_versioned_stt_rates_pre_post_oct_2024():
    """Verify STT hike on F&O effective October 1, 2024."""
    model = IndianCostModel()
    
    # 1. Options STT: 0.0625% pre-Oct 2024 vs 0.100% post-Oct 2024
    pre_cost = model.compute_cost(
        trade_value=10000.0,
        order_type=OrderType.OPTIONS,
        is_buy=False,
        trade_date=datetime(2024, 8, 15),
    )
    post_cost = model.compute_cost(
        trade_value=10000.0,
        order_type=OrderType.OPTIONS,
        is_buy=False,
        trade_date=datetime(2024, 10, 15),
    )
    assert pre_cost.stt == 6.25, f"Expected 6.25 STT, got {pre_cost.stt}"
    assert post_cost.stt == 10.00, f"Expected 10.00 STT, got {post_cost.stt}"

    # 2. Futures STT: 0.0125% pre-Oct 2024 vs 0.020% post-Oct 2024
    pre_fut = model.compute_cost(
        trade_value=100000.0,
        order_type=OrderType.FUTURES,
        is_buy=False,
        trade_date=datetime(2024, 8, 15),
    )
    post_fut = model.compute_cost(
        trade_value=100000.0,
        order_type=OrderType.FUTURES,
        is_buy=False,
        trade_date=datetime(2024, 10, 15),
    )
    assert pre_fut.stt == 12.50
    assert post_fut.stt == 20.00


def test_volatility_adjusted_slippage():
    """Verify slippage increases during high volatility (ATR)."""
    model = IndianCostModel(slippage_model=SlippageModelType.VOLATILITY_ADJUSTED, slippage_bps=5.0)
    
    # Normal volatility: ATR = 1.5% of price
    normal_cost = model.compute_cost(trade_value=10000.0, price=100.0, atr=1.5)
    # High panic volatility: ATR = 4.5% of price (3x normal)
    panic_cost = model.compute_cost(trade_value=10000.0, price=100.0, atr=4.5)
    
    assert panic_cost.slippage > normal_cost.slippage

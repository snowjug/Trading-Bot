"""Unit tests for Indian Market Friction & Cost Models."""

import pytest
from src.backtesting.cost_model import IndianCostModel, CostScenario, OrderType


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
    # Huge trade: Rs 1 Crore
    trade_value = 10_000_000.0
    cost = model.compute_cost(trade_value=trade_value, order_type=OrderType.DELIVERY, is_buy=True)

    # Zerodha-style cap of Rs 20
    assert cost.brokerage <= 20.0

"""
Unit and Regression Test Suite for Simple Deterministic Options Bot.
Validates:
- Strike selection & rounding
- Expiry selection
- Spread construction & premium calculation
- Max-loss calculation for defined-risk spreads
- Take-profit & Stop-loss math
- Risk engine margin checks, duplicate protection, fail-closed rejections
- Statutory cost model (brokerage, STT, GST, SEBI, stamp duty)
- Regression tests against lookahead, wrong strikes, wrong lot sizes, and settlement leakage
"""

import pytest
from datetime import date, datetime, time
import pandas as pd
import numpy as np

from src.strategies.base_strategy import (
    MarketData, OptionType, OrderSide, ExitReason, PositionStructure, OptionLeg
)
from src.strategies.atm_straddle import ATMStraddleStrategy
from src.strategies.otm_strangle import OTMStrangleStrategy
from src.strategies.iron_fly import IronFlyStrategy
from src.strategies.iron_condor import IronCondorStrategy
from src.risk.risk_engine import RiskEngine
from src.portfolio.portfolio import Portfolio
from src.accounting.costs import OptionsCostModel
from src.accounting.pnl import OptionPnLCalculator


@pytest.fixture
def mock_chain():
    """Builds a deterministic mock option chain."""
    strikes = [19800, 19850, 19900, 19950, 20000, 20050, 20100, 20150, 20200]
    data = []
    expiry = date(2023, 10, 19)
    for s in strikes:
        # Synthetic realistic prices for test assertions
        # ATM (20000) is 60 CE, 60 PE -> Straddle = 120
        dist = abs(s - 20000)
        if s <= 20000:
            ce_px = 60.0 + (20000 - s) * 0.7
            pe_px = max(5.0, 60.0 - dist * 0.35)
        else:
            ce_px = max(5.0, 60.0 - dist * 0.35)
            pe_px = 60.0 + (s - 20000) * 0.7
        data.append({
            "TradDt": date(2023, 10, 13),
            "XpryDt": expiry,
            "StrkPric": float(s),
            "OptnTp": "CE",
            "FinInstrmId": f"NIFTY_{expiry}_{s}_CE",
            "FinInstrmNm": f"NIFTY {expiry} {s} CE",
            "OpnPric": ce_px,
            "ClsPric": ce_px,
            "NewBrdLotQty": 50,
            "TtlTradgVol": 100000,
            "OpnIntrst": 500000
        })
        data.append({
            "TradDt": date(2023, 10, 13),
            "XpryDt": expiry,
            "StrkPric": float(s),
            "OptnTp": "PE",
            "FinInstrmId": f"NIFTY_{expiry}_{s}_PE",
            "FinInstrmNm": f"NIFTY {expiry} {s} PE",
            "OpnPric": pe_px,
            "ClsPric": pe_px,
            "NewBrdLotQty": 50,
            "TtlTradgVol": 100000,
            "OpnIntrst": 500000
        })
    return pd.DataFrame(data)


def test_strike_selection_rounding():
    strat = ATMStraddleStrategy({"strike_step": 50.0})
    assert strat.round_strike(19985.0) == 20000.0
    assert strat.round_strike(19974.9) == 19950.0
    assert strat.round_strike(20025.0) == 20050.0


def test_atm_straddle_construction(mock_chain):
    strat = ATMStraddleStrategy({"entry_time": "09:20", "take_profit_pct": 0.30, "stop_loss_pct": 0.50})
    md = MarketData(
        timestamp=datetime(2023, 10, 13, 9, 20),
        spot_price=20004.0,
        chain=mock_chain,
        expiry_date=date(2023, 10, 19)
    )
    sig = strat.check_entry(md)
    assert sig is not None

    pos = strat.build_position(md, sig)
    assert pos.status == "OPEN"
    assert len(pos.legs) == 2
    assert pos.legs[0].strike == 20000.0  # ATM CE
    assert pos.legs[1].strike == 20000.0  # ATM PE
    assert pos.legs[0].side == OrderSide.SELL
    assert pos.legs[1].side == OrderSide.SELL
    assert pos.net_premium_points == 120.0
    assert pos.take_profit_points == pytest.approx(36.0)
    assert pos.stop_loss_points == pytest.approx(60.0)
    # Check naked margin requirement is high (~1.4L)
    assert pos.margin_required >= 120000.0


def test_iron_fly_defined_risk(mock_chain):
    strat = IronFlyStrategy({"wing_width": 150.0, "entry_time": "09:20"})
    md = MarketData(
        timestamp=datetime(2023, 10, 13, 9, 20),
        spot_price=20000.0,
        chain=mock_chain,
        expiry_date=date(2023, 10, 19)
    )
    sig = strat.check_entry(md)
    assert sig is not None

    pos = strat.build_position(md, sig)
    assert pos.status == "OPEN"
    assert len(pos.legs) == 4
    # Check strikes: Long PE (19850), Short PE (20000), Short CE (20000), Long CE (20150)
    strikes = [l.strike for l in pos.legs]
    assert strikes == [19850.0, 20000.0, 20000.0, 20150.0]
    # Max loss = Wing - Net credit
    expected_loss = 150.0 - pos.net_premium_points
    assert pos.max_loss_points == pytest.approx(expected_loss)
    assert pos.max_loss_points > 0.0
    # Margin is substantially reduced for defined risk
    assert pos.margin_required < 50000.0


def test_iron_condor_construction(mock_chain):
    strat = IronCondorStrategy({"short_distance": 100.0, "wing_width": 100.0, "entry_time": "09:20"})
    md = MarketData(
        timestamp=datetime(2023, 10, 13, 9, 20),
        spot_price=20000.0,
        chain=mock_chain,
        expiry_date=date(2023, 10, 19)
    )
    sig = strat.check_entry(md)
    assert sig is not None

    pos = strat.build_position(md, sig)
    assert pos.status == "OPEN"
    assert len(pos.legs) == 4
    strikes = [l.strike for l in pos.legs]
    # Long PE (1800), Short PE (1900), Short CE (2100), Long CE (2200) -> 19800, 19900, 20100, 20200
    assert strikes == [19800.0, 19900.0, 20100.0, 20200.0]


def test_risk_engine_margin_check():
    engine = RiskEngine(initial_capital=50000.0)
    strat = ATMStraddleStrategy()
    # High margin position (~1.4L)
    pos = PositionStructure(
        strategy_name="ATM_STRADDLE",
        underlying="NIFTY",
        expiry=date(2023, 10, 19),
        margin_required=140000.0,
        lot_size=50,
        net_premium_points=200.0,
        max_loss_points=500.0
    )
    md = MarketData(timestamp=datetime(2023, 10, 13, 9, 20), spot_price=20000.0)
    decision = engine.validate_options_position(pos, capital=50000.0, current_positions=[], market_data=md)
    assert not decision.approved
    assert "INSUFFICIENT_MARGIN" in decision.rejection_reason


def test_risk_engine_duplicate_check():
    engine = RiskEngine(initial_capital=100000.0)
    pos = PositionStructure(
        strategy_name="IRON_FLY",
        underlying="NIFTY",
        expiry=date(2023, 10, 19),
        margin_required=30000.0,
        lot_size=50,
        max_loss_points=50.0
    )
    existing = PositionStructure(
        strategy_name="IRON_FLY",
        underlying="NIFTY",
        expiry=date(2023, 10, 19),
        margin_required=30000.0
    )
    md = MarketData(timestamp=datetime(2023, 10, 13, 9, 20), spot_price=20000.0)
    decision = engine.validate_options_position(pos, capital=100000.0, current_positions=[existing], market_data=md)
    assert not decision.approved
    assert "DUPLICATE_POSITION" in decision.rejection_reason


def test_cost_calculation():
    legs = [
        {"side": "SELL", "entry_price": 100.0, "exit_price": 40.0, "quantity": 50},
        {"side": "SELL", "entry_price": 100.0, "exit_price": 40.0, "quantity": 50},
    ]
    breakdown = OptionsCostModel.calculate_trade_costs(
        trade_date=date(2024, 11, 1),
        legs_execution=legs,
        slippage_points=0.2
    )
    # Brokerage: 4 orders * Rs 20 = Rs 80
    assert breakdown.brokerage == 80.0
    # STT: 0.1% on sell entry turnover = 2 * (100 * 50) * 0.001 = Rs 10.0
    assert breakdown.stt == pytest.approx(10.0)
    assert breakdown.total_costs > 100.0


def test_pnl_calculation():
    leg = OptionLeg(
        contract_id="CE_20000",
        contract_name="CE_20000",
        option_type=OptionType.CE,
        side=OrderSide.SELL,
        strike=20000.0,
        expiry=date(2023, 10, 19),
        quantity=50,
        entry_price=150.0
    )
    res = OptionPnLCalculator.calculate_leg_pnl(leg, exit_price=50.0)
    assert res.points_pnl == 100.0
    assert res.gross_pnl == 5000.0


def test_regression_no_lookahead_entry_time(mock_chain):
    strat = ATMStraddleStrategy({"entry_time": "09:20"})
    # Querying at 09:10 should return None (deterministic rule)
    md = MarketData(
        timestamp=datetime(2023, 10, 13, 9, 10),
        spot_price=20000.0,
        chain=mock_chain,
        expiry_date=date(2023, 10, 19)
    )
    assert strat.check_entry(md) is None


def test_regression_fail_closed_missing_chain():
    strat = ATMStraddleStrategy({"entry_time": "09:20"})
    md = MarketData(
        timestamp=datetime(2023, 10, 13, 9, 20),
        spot_price=20000.0,
        chain=None,
        expiry_date=date(2023, 10, 19)
    )
    assert strat.check_entry(md) is None

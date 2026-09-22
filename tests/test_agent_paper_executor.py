"""
Executor tests. These pin the claim that an order cannot exist without an approved
verdict, and that live mode is refused structurally rather than by convention.
"""

import os
import sys
from datetime import datetime, time as dtime

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agent.decision_schema import AgentDecision
from src.execution.agent_paper_executor import (
    AgentPaperExecutor, LiveTradingRefused, UnapprovedOrderRefused,
)
from src.options.structures import Leg, build
from src.risk.structure_risk import PricedLeg, RiskVerdict

NOW = datetime(2026, 9, 21, 11, 30)


def _legs(structure="BULL_PUT_SPREAD"):
    out = []
    for L in build(structure, 23000.0, width_steps=4, otm_steps=2):
        px = 60.0 if L.side == "SELL" else 25.0
        out.append(PricedLeg(L, px, px * (0.99 if L.side == "SELL" else 1.01),
                             5000.0, 0.01))
    return out


def _dec(**kw):
    base = dict(action="BUY", decision="EXECUTE", underlying="NIFTY",
                direction="BULLISH", structure="BULL_PUT_SPREAD",
                setup_quality="HIGH", direction_score=0.7,
                expected_move_points=80.0, expected_move_horizon_minutes=5,
                estimated_horizon_minutes=60, max_hold_minutes=120,
                stop_type="PREMIUM_PTS", stop_value=20.0,
                take_profit_type="R_MULTIPLE", take_profit_value=2.0,
                invalidation_conditions=[], reason_codes=["X"], rationale="")
    base.update(kw)
    return AgentDecision(**base)


def _approved(lots=2):
    return RiskVerdict(approved=True, lots=lots, capital_at_risk=20000.0,
                       margin_or_debit=20000.0, max_loss_pts=140.0,
                       net_credit_pts=34.0, expected_edge_pts=30.0)


def test_executor_refuses_to_construct_in_live_mode():
    with pytest.raises(LiveTradingRefused):
        AgentPaperExecutor(1_000_000.0, live_trading_enabled=True)


def test_place_refuses_in_live_mode_even_with_an_approved_verdict():
    ex = AgentPaperExecutor(1_000_000.0)
    with pytest.raises(LiveTradingRefused):
        ex.place(_dec(), _approved(), _legs(), now=NOW, lot_size=75, spot=23000.0,
                 live_trading_enabled=True)


def test_place_refuses_an_unapproved_verdict_loudly():
    ex = AgentPaperExecutor(1_000_000.0)
    bad = RiskVerdict(approved=False, lots=0, gate_failed="CAPITAL_INSUFFICIENT")
    with pytest.raises(UnapprovedOrderRefused):
        ex.place(_dec(), bad, _legs(), now=NOW, lot_size=75, spot=23000.0)


def test_place_refuses_an_approved_verdict_with_zero_lots():
    ex = AgentPaperExecutor(1_000_000.0)
    with pytest.raises(UnapprovedOrderRefused):
        ex.place(_dec(), _approved(lots=0), _legs(), now=NOW, lot_size=75, spot=23000.0)


def test_place_refuses_a_second_position():
    ex = AgentPaperExecutor(1_000_000.0)
    ex.place(_dec(), _approved(), _legs(), now=NOW, lot_size=75, spot=23000.0)
    with pytest.raises(UnapprovedOrderRefused):
        ex.place(_dec(), _approved(), _legs(), now=NOW, lot_size=75, spot=23000.0)


def test_order_carries_full_identity_for_every_leg():
    ex = AgentPaperExecutor(1_000_000.0)
    o = ex.place(_dec(), _approved(lots=3), _legs(), now=NOW, lot_size=75,
                 spot=23000.0, state_hash="abc123")
    assert o.client_order_id and o.strategy_id and o.decision_id == "abc123"
    assert o.mode == "PAPER" and o.lots == 3 and o.lot_size == 75
    assert len(o.legs) == 2
    for L in o.legs:
        for k in ("option_type", "side", "strike", "quantity", "fill_price",
                  "reference_price", "volume_at_entry"):
            assert k in L, k
        assert abs(L["quantity"]) == 3 * 75
    assert len(ex.state.fills) == 2


def test_an_unmarkable_position_is_recorded_not_priced():
    ex = AgentPaperExecutor(1_000_000.0)
    ex.place(_dec(), _approved(), _legs(), now=NOW, lot_size=75, spot=23000.0)
    eq_before = ex.state.equity
    rec = ex.close(NOW.replace(hour=13), mark_pts=None, exit_prices=[],
                   reason="DATA_LOSS")
    assert rec["closed"] and rec["resolved"] is False
    assert rec["net_rupees"] is None
    assert ex.state.equity == eq_before, "equity must not move on an unpriced exit"
    assert ex.state.open_position is None


def test_a_marked_exit_updates_equity_and_journals_both_events():
    ex = AgentPaperExecutor(1_000_000.0)
    ex.place(_dec(), _approved(lots=1), _legs(), now=NOW, lot_size=75, spot=23000.0)
    rec = ex.close(NOW.replace(hour=13), mark_pts=10.0, exit_prices=[10.0, 0.5],
                   reason="TARGET_HIT")
    assert rec["resolved"] and rec["net_rupees"] is not None
    assert ex.state.equity == pytest.approx(1_000_000.0 + rec["net_rupees"])
    events = [r["event"] for r in ex.state.journal]
    assert events == ["ENTRY", "EXIT"]
    assert all("access_token" not in json_str.lower()
               for json_str in (str(r) for r in ex.state.journal))


def test_session_exit_and_max_hold_are_enforced_by_the_executor():
    ex = AgentPaperExecutor(1_000_000.0, session_exit=dtime(15, 15))
    ex.place(_dec(max_hold_minutes=30), _approved(), _legs(), now=NOW,
             lot_size=75, spot=23000.0)
    assert ex.check_exit(NOW.replace(hour=15, minute=20), 10.0, 23000.0) == "SESSION_EXIT"
    assert ex.check_exit(NOW.replace(hour=12, minute=30), 10.0, 23000.0) == "MAX_HOLD"
    assert ex.check_exit(NOW.replace(hour=11, minute=45), 10.0, 23000.0) is None


def test_data_loss_is_an_exit_not_a_hold():
    ex = AgentPaperExecutor(1_000_000.0)
    ex.place(_dec(), _approved(), _legs(), now=NOW, lot_size=75, spot=23000.0)
    assert ex.check_exit(NOW.replace(hour=12), None, 23000.0) == "DATA_LOSS"


def test_summary_never_contains_a_credential():
    ex = AgentPaperExecutor(1_000_000.0)
    s = str(ex.summary()).lower()
    for bad in ("token", "secret", "password", "access-token"):
        assert bad not in s

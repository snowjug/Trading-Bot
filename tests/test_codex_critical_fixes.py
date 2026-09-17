"""
Regression + adversarial suite for the Codex XHigh findings.

CRITICAL #1 — Bot 6 (and every other bot) could not bypass the RiskEngine.
CRITICAL #2 — Broker reconciliation must distinguish FLAT / POSITIONS /
              UNAVAILABLE / MALFORMED and fail closed on the latter two.
HIGH  #7    — Multi-leg positions are modelled leg-by-leg, not as one contract.
"""
import ast
import json
from datetime import datetime, time as dtime
from unittest.mock import MagicMock, patch

import pytest

from src.execution import live_market_bars, position_reconciler
from src.execution.live_paper_session import MultiBotLiveSession
from src.execution.live_strategy_adapter import LiveSignal
from src.execution.position_reconciler import (
    BrokerPosition,
    BrokerSnapshot,
    BrokerStateStatus,
    parse_broker_payload,
    reconcile_snapshot,
)
from src.risk.risk_engine import RiskEngine

BOT6 = "Strategy 6: Micro Momentum Sniper"
BOT5 = "Strategy 5: Velocity-5 Momentum Scalper"

SESSION_BAR = {
    "open": 23201.6, "high": 23284.75, "low": 23116.1,
    "close": 23217.6, "volume": 250000.0, "source": "TEST_INTRADAY",
}


def _make_session(tmp_path, risk=None, **kw):
    live_market_bars.clear_session_bar_cache()
    return MultiBotLiveSession(
        state_file=str(tmp_path / "session.json"),
        reports_dir=tmp_path,
        risk_engine=risk or RiskEngine(kill_switch_file=tmp_path / "ks.json"),
        **kw,
    )


def _mkt():
    return {
        "nifty": {"last": 23217.6, "open": 23201.6},
        "bank": {"last": 56292.4, "open": 56007.6},
        "vix": 13.2, "timestamp": None,
    }


def _contract(sec_id="88888", bid=99.5, ask=100.0):
    return {
        "security_id": sec_id, "custom_symbol": "NIFTY TEST", "trading_symbol": "T",
        "lot_size": 65, "bid": bid, "ask": ask, "ltp": 99.8,
        "quote_timestamp": datetime.now().isoformat(),
    }


def _open_trade(sec_id="56983", qty=65, price=136.5):
    return {
        "id": "T1", "contract": "NIFTY 23250 CE", "security_id": sec_id, "side": "BUY",
        "qty": qty, "entry_fill": price, "entry_premium": price,
        "status": "OPEN", "trade_state": "OPEN", "valuation_status": "LIVE_QUOTE",
        "unrealized_pnl": 0.0,
    }


def _run_bot6(session, direction, resolve=None):
    """Drives one cycle with only Bot 6 actionable in the given direction."""
    def sig(bot, **kw):
        return LiveSignal(bot, "X", direction if bot == BOT6 else 0, 0.85, "NIFTY",
                          reason="STRATEGY_SIGNAL")

    with patch.object(live_market_bars, "get_today_session_bar", return_value=SESSION_BAR), \
         patch.object(session.strategy_adapter, "evaluate", side_effect=sig), \
         patch("src.execution.live_paper_session.DhanContractResolver.resolve_option_contract",
               side_effect=resolve or (lambda spot, vix, ot, **k: _contract())):
        session.evaluate_all_bots(_mkt(), current_time=dtime(11, 0))


# ─────────────────── CRITICAL #1: NO ENTRY MAY BYPASS RISK ───────────────────

def test_c1_every_entry_assignment_routes_through_the_central_gate():
    """Structural proof: no bot may assign active_trade from a raw dict."""
    src = open("src/execution/live_paper_session.py", encoding="utf-8").read()
    tree = ast.parse(src)
    gated = ungated = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            if (isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant)
                    and t.slice.value == "active_trade"):
                v = node.value
                if (isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute)
                        and v.func.attr == "_risk_gated_entry"):
                    gated += 1
                elif isinstance(v, ast.Dict):
                    ungated += 1
    assert ungated == 0, f"{ungated} entry path(s) bypass the risk gate"
    assert gated == 8, f"expected 8 gated entry paths, found {gated}"


@pytest.mark.parametrize("direction,label", [(1, "CE"), (-1, "PE")])
def test_c1_bot6_cannot_enter_when_risk_rejects(tmp_path, direction, label):
    """Bot 6 must not create a position on EITHER branch when risk rejects."""
    session = _make_session(tmp_path)
    with patch.object(session, "evaluate_entry_risk",
                      return_value=(False, "RISK_REJECTED: injected")):
        _run_bot6(session, direction)
    assert session.bot_states[BOT6]["active_trade"] is None, \
        f"Bot 6 {label} branch created a position despite a risk rejection"


@pytest.mark.parametrize("direction,label", [(1, "CE"), (-1, "PE")])
def test_c1_bot6_enters_when_risk_approves(tmp_path, direction, label):
    """Control: the gate is not a blanket block — approval still trades."""
    session = _make_session(tmp_path)
    _run_bot6(session, direction)
    assert session.bot_states[BOT6]["active_trade"] is not None, \
        f"Bot 6 {label} branch failed to trade on an approved signal"


@pytest.mark.parametrize("direction", [1, -1])
def test_c1_bot6_blocked_by_kill_switch(tmp_path, direction):
    risk = RiskEngine(kill_switch_file=tmp_path / "ks.json")
    session = _make_session(tmp_path, risk=risk)
    risk.trip_kill_switch("adversarial halt")
    _run_bot6(session, direction)
    assert session.bot_states[BOT6]["active_trade"] is None


@pytest.mark.parametrize("direction", [1, -1])
def test_c1_bot6_blocked_by_max_drawdown(tmp_path, direction):
    session = _make_session(tmp_path)
    session.sync_risk_state()
    session.bot_states[BOT5]["closed_trades"] = [
        {"id": "L", "gross_pnl": -40000.0, "statutory_friction": 0.0, "net_pnl": -40000.0}
    ]
    _run_bot6(session, direction)
    assert session.bot_states[BOT6]["active_trade"] is None


@pytest.mark.parametrize("direction", [1, -1])
def test_c1_bot6_blocked_by_daily_loss_limit(tmp_path, direction):
    risk = RiskEngine(kill_switch_file=tmp_path / "ks.json", max_portfolio_drawdown=0.95)
    session = _make_session(tmp_path, risk=risk)
    session.sync_risk_state()
    session.bot_states[BOT5]["closed_trades"] = [
        {"id": "L", "gross_pnl": -5000.0, "statutory_friction": 0.0, "net_pnl": -5000.0}
    ]
    _run_bot6(session, direction)
    assert session.bot_states[BOT6]["active_trade"] is None


@pytest.mark.parametrize("direction", [1, -1])
def test_c1_bot6_blocked_by_weekly_loss_limit(tmp_path, direction):
    risk = RiskEngine(kill_switch_file=tmp_path / "ks.json",
                      max_portfolio_drawdown=0.95, daily_loss_limit=0.95)
    session = _make_session(tmp_path, risk=risk)
    session.sync_risk_state()
    session.bot_states[BOT5]["closed_trades"] = [
        {"id": "L", "gross_pnl": -7000.0, "statutory_friction": 0.0, "net_pnl": -7000.0}
    ]
    _run_bot6(session, direction)
    assert session.bot_states[BOT6]["active_trade"] is None


@pytest.mark.parametrize("direction", [1, -1])
def test_c1_bot6_blocked_by_max_positions(tmp_path, direction):
    risk = RiskEngine(kill_switch_file=tmp_path / "ks.json", max_simultaneous_positions=1)
    session = _make_session(tmp_path, risk=risk)
    session.bot_states[BOT5]["active_trade"] = _open_trade(sec_id="57023")
    _run_bot6(session, direction)
    assert session.bot_states[BOT6]["active_trade"] is None


@pytest.mark.parametrize("direction", [1, -1])
def test_c1_bot6_blocked_by_position_size_cap(tmp_path, direction):
    """A lot whose notional exceeds the position-value cap must be refused."""
    session = _make_session(tmp_path)
    huge = _contract(bid=4999.0, ask=5000.0)
    _run_bot6(session, direction, resolve=lambda spot, vix, ot, **k: huge)
    assert session.bot_states[BOT6]["active_trade"] is None


@pytest.mark.parametrize("direction", [1, -1])
def test_c1_bot6_blocked_by_portfolio_concentration(tmp_path, direction):
    """Another strategy already in the contract blocks Bot 6 on both branches."""
    session = _make_session(tmp_path)
    session.bot_states[BOT5]["active_trade"] = _open_trade(sec_id="88888")
    _run_bot6(session, direction)
    assert session.bot_states[BOT6]["active_trade"] is None


def test_c1_rejected_entry_is_not_recorded_as_executed(tmp_path):
    """A gated-out entry must not leave an EXECUTED audit record behind."""
    session = _make_session(tmp_path)
    with patch.object(session, "evaluate_entry_risk",
                      return_value=(False, "RISK_REJECTED: injected")):
        _run_bot6(session, 1)
    executed = [s for s in session.signals if s.get("status") == "EXECUTED"]
    assert not executed, f"rejected entry still recorded as EXECUTED: {executed}"


def test_c1_gate_refuses_trade_without_resolvable_owner(tmp_path):
    session = _make_session(tmp_path)
    assert session._risk_gated_entry(session.bot_states[BOT6], {"qty": 65}) is None


def test_c1_gate_refuses_trade_without_security_ids(tmp_path):
    session = _make_session(tmp_path)
    trade = {"strategy": BOT6, "qty": 65, "entry_fill": 100.0, "security_id": ""}
    assert session._risk_gated_entry(session.bot_states[BOT6], trade) is None


def test_c1_no_dead_duplicate_risk_branch_remains():
    """The unreachable duplicate elif in Bot 6 must be gone."""
    src = open("src/execution/live_paper_session.py", encoding="utf-8").read()
    bot6 = src[src.index("BOT 6: MICRO MOMENTUM SNIPER"):]
    assert bot6.count("entry blocked by risk engine") <= 1, \
        "duplicate/unreachable risk branch still present in Bot 6"


# ─────────────── CRITICAL #2: RECONCILIATION STATE CORRECTNESS ───────────────

def test_c2_matching_positions_reconcile(tmp_path):
    session = _make_session(tmp_path)
    session.bot_states[BOT5]["active_trade"] = _open_trade(sec_id="56983", qty=65)
    snap = parse_broker_payload([{"securityId": "56983", "netQty": 65}])
    result = reconcile_snapshot(session.bot_states, snap)
    assert result.reconciled is True
    assert result.halt_required is False


def test_c2_quantity_mismatch_halts(tmp_path):
    session = _make_session(tmp_path)
    session.bot_states[BOT5]["active_trade"] = _open_trade(sec_id="56983", qty=65)
    snap = parse_broker_payload([{"securityId": "56983", "netQty": 130}])
    result = reconcile_snapshot(session.bot_states, snap)
    assert result.halt_required is True
    assert "local 65 vs broker 130" in result.reason


def test_c2_unexpected_broker_position_halts(tmp_path):
    session = _make_session(tmp_path)
    snap = parse_broker_payload([{"securityId": "99999", "netQty": 75}])
    result = reconcile_snapshot(session.bot_states, snap)
    assert result.halt_required is True
    assert "NO local position" in result.reason


def test_c2_security_id_mismatch_halts(tmp_path):
    """Right quantity, wrong contract, is still a mismatch."""
    session = _make_session(tmp_path)
    session.bot_states[BOT5]["active_trade"] = _open_trade(sec_id="56983", qty=65)
    snap = parse_broker_payload([{"securityId": "57023", "netQty": 65}])
    result = reconcile_snapshot(session.bot_states, snap)
    assert result.halt_required is True
    assert "57023" in result.reason


def test_c2_duplicate_broker_rows_are_aggregated():
    """Two rows for one contract net together rather than overwriting."""
    snap = parse_broker_payload([
        {"securityId": "56983", "netQty": 25},
        {"securityId": "56983", "netQty": 40},
    ])
    assert snap.status is BrokerStateStatus.AVAILABLE_POSITIONS
    assert snap.as_quantity_map() == {"56983": 65.0}


def test_c2_empty_valid_response_is_flat_not_unknown():
    snap = parse_broker_payload([])
    assert snap.status is BrokerStateStatus.AVAILABLE_FLAT
    assert snap.is_trustworthy is True


def test_c2_api_error_is_unavailable_not_flat():
    """The core defect: an error must never look like an empty book."""
    snap = parse_broker_payload(None)
    assert snap.status is BrokerStateStatus.UNAVAILABLE
    assert snap.is_trustworthy is False


@pytest.mark.parametrize("payload", [
    [{"netQty": 65}],                              # no security id
    [{"securityId": "56983"}],                     # no quantity
    [{"securityId": "56983", "netQty": "abc"}],    # unparseable quantity
    ["not-a-position"],                            # wrong row type
    {"unexpected": "envelope"},                    # wrong container
])
def test_c2_malformed_payload_fails_closed(payload):
    """Unparseable rows must poison the whole snapshot, never be skipped."""
    snap = parse_broker_payload(payload)
    assert snap.status is BrokerStateStatus.MALFORMED
    assert snap.is_trustworthy is False


def test_c2_malformed_snapshot_halts_trading(tmp_path):
    session = _make_session(tmp_path)
    snap = parse_broker_payload([{"netQty": 65}])
    result = reconcile_snapshot(session.bot_states, snap)
    assert result.halt_required is True
    assert "MALFORMED" in result.reason


def test_c2_unavailable_during_active_position_halts(tmp_path):
    """The dangerous case: we hold a position and cannot see the broker book."""
    session = _make_session(tmp_path)
    session.bot_states[BOT5]["active_trade"] = _open_trade()
    snap = BrokerSnapshot(status=BrokerStateStatus.UNAVAILABLE, error="timeout")
    result = reconcile_snapshot(session.bot_states, snap)
    assert result.halt_required is True
    assert result.broker_available is False
    assert result.local_positions, "local exposure must still be reported while halted"


def test_c2_typed_paper_position_is_not_silently_skipped():
    """
    The original defect: PaperPosition objects were skipped by an isinstance
    check, so the broker always looked flat. Such a row must now either parse
    or make the snapshot MALFORMED — never vanish.
    """
    from src.execution.paper_broker import PaperPosition

    snap = parse_broker_payload([PaperPosition(symbol="NIFTY", quantity=65, avg_price=100.0)])
    assert snap.status is BrokerStateStatus.MALFORMED, \
        "a position row lacking a security id must fail closed, not be skipped"


def test_c2_canonical_broker_position_round_trips():
    snap = parse_broker_payload([BrokerPosition(security_id="56983", net_qty=65)])
    assert snap.status is BrokerStateStatus.AVAILABLE_POSITIONS
    assert snap.as_quantity_map() == {"56983": 65.0}


def test_c2_adapter_http_error_maps_to_unavailable():
    from src.execution.broker_adapters.dhan import DhanBrokerAdapter

    adapter = DhanBrokerAdapter(client_id="x", access_token="y")
    resp = MagicMock(status_code=500, text="server error")
    with patch.object(adapter.session, "get", return_value=resp):
        snap = adapter.fetch_positions_snapshot()
    assert snap.status is BrokerStateStatus.UNAVAILABLE
    assert snap.is_trustworthy is False


def test_c2_adapter_exception_maps_to_unavailable():
    from src.execution.broker_adapters.dhan import DhanBrokerAdapter

    adapter = DhanBrokerAdapter(client_id="x", access_token="y")
    with patch.object(adapter.session, "get", side_effect=TimeoutError("timeout")):
        snap = adapter.fetch_positions_snapshot()
    assert snap.status is BrokerStateStatus.UNAVAILABLE


def test_c2_adapter_bad_json_maps_to_malformed():
    from src.execution.broker_adapters.dhan import DhanBrokerAdapter

    adapter = DhanBrokerAdapter(client_id="x", access_token="y")
    resp = MagicMock(status_code=200)
    resp.json.side_effect = ValueError("not json")
    with patch.object(adapter.session, "get", return_value=resp):
        snap = adapter.fetch_positions_snapshot()
    assert snap.status is BrokerStateStatus.MALFORMED


def test_c2_adapter_preserves_security_id():
    """securityId must survive; PaperPosition dropped it entirely."""
    from src.execution.broker_adapters.dhan import DhanBrokerAdapter

    adapter = DhanBrokerAdapter(client_id="x", access_token="y")
    resp = MagicMock(status_code=200)
    resp.json.return_value = [{"securityId": "56983", "netQty": 65, "tradingSymbol": "NIFTY"}]
    with patch.object(adapter.session, "get", return_value=resp):
        snap = adapter.fetch_positions_snapshot()
    assert snap.positions[0].security_id == "56983"
    assert snap.positions[0].trading_symbol == "NIFTY"


def test_c2_startup_and_cycle_use_the_same_corrected_state(tmp_path):
    """Both gates must consume the canonical snapshot path."""
    src = open("src/execution/live_paper_session.py", encoding="utf-8").read()
    assert "fetch_broker_snapshot" in src, "session must use the canonical snapshot fetch"

    session = _make_session(tmp_path)
    bad = BrokerSnapshot(status=BrokerStateStatus.MALFORMED, error="garbage")
    with patch.object(position_reconciler, "broker_source_configured", return_value=True), \
         patch.object(position_reconciler, "fetch_broker_snapshot", return_value=bad):
        result = session.reconcile_cycle()
    assert result.halt_required is True
    assert session.requires_reconciliation is True


def test_c2_reconciliation_is_read_only():
    src = open("src/execution/position_reconciler.py", encoding="utf-8").read()
    for banned in [".post(", ".put(", ".patch(", ".delete(", "place_order", "cancel_order"]:
        assert banned not in src, f"reconciler must stay read-only: {banned}"


def test_c2_adapter_snapshot_uses_get_only():
    src = open("src/execution/broker_adapters/dhan.py", encoding="utf-8").read()
    body = src[src.index("def fetch_positions_snapshot"):src.index("def get_orders")]
    assert "session.get(" in body
    for banned in [".post(", ".put(", ".patch(", ".delete("]:
        assert banned not in body, f"snapshot fetch must be read-only: {banned}"


# ─────────────────── HIGH #7: MULTI-LEG POSITION MODEL ───────────────────

def test_h7_strangle_decomposes_into_two_legs(tmp_path):
    session = _make_session(tmp_path)
    trade = {
        "strategy": "Strategy 1: Apex VRP Engine", "side": "SELL", "qty": 65,
        "call_security_id": "57023", "put_security_id": "56948",
        "entry_fill": 70.0, "security_id": "57023 / 56948",
    }
    legs = session.extract_trade_legs(trade)
    assert len(legs) == 2
    assert {l["security_id"] for l in legs} == {"57023", "56948"}
    assert all(l["side"] == "SELL" for l in legs)
    assert all(l["qty"] == 65 for l in legs)


def test_h7_vertical_spread_has_opposing_legs(tmp_path):
    session = _make_session(tmp_path)
    trade = {
        "strategy": "Strategy 2: Zen Curvature Overnight", "side": "SELL", "qty": 65,
        "short_security_id": "57023", "long_security_id": "57100", "entry_fill": 20.0,
    }
    legs = session.extract_trade_legs(trade)
    sides = {l["leg_role"]: l["side"] for l in legs}
    assert sides == {"short": "SELL", "long": "BUY"}


def test_h7_exposure_distinguishes_gross_and_net(tmp_path):
    session = _make_session(tmp_path)
    session.bot_states["Strategy 2: Zen Curvature Overnight"]["active_trade"] = {
        "strategy": "Strategy 2: Zen Curvature Overnight", "side": "SELL", "qty": 65,
        "short_security_id": "57023", "long_security_id": "57100",
        "entry_fill": 20.0, "status": "OPEN",
    }
    summary = session.leg_exposure_summary()
    assert summary["leg_count"] == 2
    assert summary["gross_exposure"] > abs(summary["net_exposure"]), \
        "a hedged spread must show net exposure below gross"


def test_h7_margin_is_declared_unavailable_not_fabricated(tmp_path):
    session = _make_session(tmp_path)
    summary = session.leg_exposure_summary()
    assert summary["span_margin"] is None, "SPAN margin must never be invented"
    assert "UNAVAILABLE" in summary["margin_basis"]


def test_h7_risk_gate_checks_every_leg(tmp_path):
    """A rejection on ANY leg must reject the whole multi-leg entry."""
    session = _make_session(tmp_path)
    trade = {
        "strategy": "Strategy 1: Apex VRP Engine", "side": "SELL", "qty": 65,
        "call_security_id": "57023", "put_security_id": "56948", "entry_fill": 70.0,
    }
    seen = []

    def gate(bot, sec_id, qty, price):
        seen.append(sec_id)
        return (sec_id != "56948", "RISK_REJECTED: put leg" if sec_id == "56948" else "RISK_APPROVED")

    with patch.object(session, "evaluate_entry_risk", side_effect=gate):
        result = session._risk_gated_entry(session.bot_states["Strategy 1: Apex VRP Engine"], trade)

    assert result is None, "a failing leg must reject the whole structure"
    assert "57023" in seen and "56948" in seen, "every leg must be risk-checked"

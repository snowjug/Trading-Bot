"""
Regression suite for blockers B5, B6, B7, B9, B12 and B14.

B5: a new trading day must never silently resume yesterday's session.
B6: only one process may own the live state file.
B7: positions left open past 15:35 are squared off on restart.
B9: local/broker position disagreement halts trading.
B12: every state-changing HTTP verb against production order routes is blocked.
B14: the live entry path enforces the full microstructure gate.
"""
import json
from datetime import datetime, timedelta, time as dtime
from unittest.mock import patch

import pytest

from src.config import Config
from src.execution import live_market_bars
from src.execution.broker_adapters.dhan import DhanBrokerAdapter
from src.execution.dhan_paper_trader import DhanPaperSandbox
from src.execution.live_paper_session import MultiBotLiveSession
from src.execution.position_reconciler import (
    ReconciliationResult,
    extract_local_positions,
    reconcile_positions,
)
from src.risk.risk_engine import RiskEngine

BOT5 = "Strategy 5: Velocity-5 Momentum Scalper"


def _make_session(tmp_path, name="session.json"):
    live_market_bars.clear_session_bar_cache()
    return MultiBotLiveSession(
        state_file=str(tmp_path / name),
        reports_dir=tmp_path,
        risk_engine=RiskEngine(kill_switch_file=tmp_path / "ks.json"),
    )


def _open_trade(sec_id="56983", qty=65, price=136.5):
    return {
        "id": "T1", "contract": "NIFTY 23250 CE", "security_id": sec_id, "side": "BUY",
        "qty": qty, "entry_fill": price, "entry_premium": price, "current_bid": price,
        "current_ask": price + 0.5, "target_premium": price * 1.3, "stop_premium": price * 0.85,
        "status": "OPEN", "trade_state": "OPEN", "valuation_status": "LIVE_QUOTE",
        "unrealized_pnl": 0.0, "quote_timestamp": datetime.now().isoformat(),
    }


# ─── B5: NEW-DAY ROLLOVER ───

def test_b5_session_date_is_persisted(tmp_path):
    session = _make_session(tmp_path)
    session.save_session()
    data = json.loads((tmp_path / "session.json").read_text())
    assert data["session_date"] == datetime.now().date().isoformat()


def test_b5_yesterday_closed_trades_are_not_carried_into_today(tmp_path):
    """Yesterday's settled trades must not block today's bots or inflate today's P&L."""
    state_file = tmp_path / "session.json"
    yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()
    state_file.write_text(json.dumps({
        "session_date": yesterday,
        "bot_states": {
            BOT5: {
                "allocated_capital": 16000.0, "current_capital": 16000.0,
                "status": "SQUARED_OFF", "active_trade": None,
                "closed_trades": [{"id": "OLD", "net_pnl": 2818.25, "gross_pnl": 2863.25}],
                "net_pnl": 2818.25,
            }
        },
        "session_log": ["[10:00:00] yesterday"], "signals": [], "rejected_signals": [],
    }))

    session = MultiBotLiveSession(
        state_file=str(state_file), reports_dir=tmp_path,
        risk_engine=RiskEngine(kill_switch_file=tmp_path / "ks.json"),
    )

    assert session.bot_states[BOT5]["closed_trades"] == []
    assert session.bot_states[BOT5]["net_pnl"] == 0.0
    assert session.session_log == []
    assert session.previous_session_date == yesterday
    assert session.requires_reconciliation is False  # nothing was left open


def test_b5_prior_day_open_position_halts_trading_for_reconciliation(tmp_path):
    """An unreconciled prior-day position must halt trading, not silently resume."""
    state_file = tmp_path / "session.json"
    yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()
    state_file.write_text(json.dumps({
        "session_date": yesterday,
        "bot_states": {BOT5: {
            "allocated_capital": 16000.0, "current_capital": 16000.0,
            "status": "IN_POSITION", "active_trade": _open_trade(),
            "closed_trades": [], "net_pnl": 0.0,
        }},
        "session_log": [], "signals": [], "rejected_signals": [],
    }))

    session = MultiBotLiveSession(
        state_file=str(state_file), reports_dir=tmp_path,
        risk_engine=RiskEngine(kill_switch_file=tmp_path / "ks.json"),
    )

    assert session.requires_reconciliation is True
    assert "UNRECONCILED_PRIOR_DAY_POSITIONS" in session.reconciliation_reason
    assert BOT5 in session.carried_over_positions
    assert session.bot_states[BOT5]["active_trade"] is None, "stale position must not be resumed"

    approved, reason = session.evaluate_entry_risk(BOT5, "56983", 65, 136.5)
    assert approved is False
    assert "TRADING_HALTED" in reason


def test_b5_previous_day_state_is_archived(tmp_path):
    state_file = tmp_path / "session.json"
    yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()
    state_file.write_text(json.dumps({
        "session_date": yesterday,
        "bot_states": {}, "session_log": [], "signals": [], "rejected_signals": [],
    }))
    MultiBotLiveSession(
        state_file=str(state_file), reports_dir=tmp_path,
        risk_engine=RiskEngine(kill_switch_file=tmp_path / "ks.json"),
    )
    assert (tmp_path / f"archive_session_{yesterday}.json").exists()


def test_b5_same_day_state_still_resumes_normally(tmp_path):
    """Intraday restart on the SAME day must resume the open position."""
    state_file = tmp_path / "session.json"
    state_file.write_text(json.dumps({
        "session_date": datetime.now().date().isoformat(),
        "bot_states": {BOT5: {
            "allocated_capital": 16000.0, "current_capital": 16000.0,
            "status": "IN_POSITION", "active_trade": _open_trade(),
            "closed_trades": [], "net_pnl": 0.0,
        }},
        "session_log": [], "signals": [], "rejected_signals": [],
    }))
    session = MultiBotLiveSession(
        state_file=str(state_file), reports_dir=tmp_path,
        risk_engine=RiskEngine(kill_switch_file=tmp_path / "ks.json"),
    )
    assert session.bot_states[BOT5]["active_trade"] is not None
    assert session.requires_reconciliation is False


# ─── B6: MULTI-INSTANCE SAFETY ───

def test_b6_second_session_refuses_to_start(tmp_path):
    """Session B must fail safely while session A owns the state file."""
    a = _make_session(tmp_path)
    a.acquire_session_lock()
    try:
        b = _make_session(tmp_path)
        with pytest.raises(RuntimeError) as exc:
            b.acquire_session_lock()
        assert "SESSION LOCK HELD" in str(exc.value)
    finally:
        a.release_session_lock()


def test_b6_lock_is_released_and_reacquirable(tmp_path):
    a = _make_session(tmp_path)
    a.acquire_session_lock()
    a.release_session_lock()
    assert not a.lock_file.exists()

    b = _make_session(tmp_path)
    b.acquire_session_lock()  # must not raise
    b.release_session_lock()


def test_b6_lock_records_owning_pid(tmp_path):
    import os
    a = _make_session(tmp_path)
    a.acquire_session_lock()
    try:
        assert f"pid={os.getpid()}" in a.lock_file.read_text()
    finally:
        a.release_session_lock()


# ─── B7: OVERDUE EOD ───

def test_b7_startup_after_eod_squares_off_open_position(tmp_path):
    """A process starting after 15:35 must flatten a position left open."""
    session = _make_session(tmp_path)
    session.bot_states[BOT5]["active_trade"] = _open_trade()

    closed = session.handle_overdue_eod(current_time=dtime(15, 50))

    assert closed == 1
    assert session.bot_states[BOT5]["active_trade"] is None
    trades = session.bot_states[BOT5]["closed_trades"]
    assert len(trades) == 1
    assert "EOD_FORCED_EXIT" in trades[0]["exit_reason"]


def test_b7_before_eod_boundary_is_a_noop(tmp_path):
    session = _make_session(tmp_path)
    session.bot_states[BOT5]["active_trade"] = _open_trade()
    assert session.handle_overdue_eod(current_time=dtime(11, 0)) == 0
    assert session.bot_states[BOT5]["active_trade"] is not None


def test_b7_overdue_eod_without_quote_leaves_position_unresolved(tmp_path):
    """
    No executable quote -> the position must NOT be closed at a fabricated price.

    It stays OPEN, is flagged unresolved with null P&L, and halts new entries.
    """
    session = _make_session(tmp_path)
    trade = _open_trade()
    trade["current_bid"] = None
    trade["current_ask"] = None
    trade["current_premium"] = None
    trade["quote_timestamp"] = None
    trade["valuation_status"] = "DATA_UNAVAILABLE"
    session.bot_states[BOT5]["active_trade"] = trade

    session.handle_overdue_eod(current_time=dtime(15, 50))

    assert session.bot_states[BOT5]["closed_trades"] == [],         "a position with no executable quote must never enter the realised ledger"
    still_open = session.bot_states[BOT5]["active_trade"]
    assert still_open is not None
    assert still_open["status"] == "UNRESOLVED_EOD"
    assert still_open["exit_reason"] == "EOD_UNRESOLVED_NO_EXECUTABLE_QUOTE"
    assert still_open["net_pnl"] is None and still_open["gross_pnl"] is None
    assert session.requires_reconciliation is True


def test_b7_stale_quote_cannot_produce_an_eod_fill(tmp_path):
    """A stale quote is not executable, so it must not be used to close."""
    session = _make_session(tmp_path)
    trade = _open_trade()
    trade["quote_timestamp"] = (datetime.now() - timedelta(seconds=3600)).isoformat()
    session.bot_states[BOT5]["active_trade"] = trade

    session.handle_overdue_eod(current_time=dtime(15, 50))
    assert session.bot_states[BOT5]["closed_trades"] == []
    assert session.bot_states[BOT5]["active_trade"]["status"] == "UNRESOLVED_EOD"


# ─── B9: BROKER RECONCILIATION ───

def test_b9_local_position_extraction_ignores_strategy_labels(tmp_path):
    session = _make_session(tmp_path)
    session.bot_states[BOT5]["active_trade"] = _open_trade(sec_id="56983", qty=65)
    session.bot_states["Strategy 3: Confluence Gamma Scalper"]["active_trade"] = _open_trade(sec_id="56983", qty=65)
    local = extract_local_positions(session.bot_states)
    assert local == {"56983": 130.0}


def test_b9_broker_position_with_no_local_counterpart_halts_trading(tmp_path):
    """A broker position this system never opened is always a hard mismatch."""
    session = _make_session(tmp_path)
    result = session.reconcile_with_broker(
        broker_positions=[{"securityId": "99999", "netQty": 75}], broker_available=True,
    )
    assert result.reconciled is False
    assert result.halt_required is True
    assert "NO local position" in result.reason
    assert session.requires_reconciliation is True

    approved, reason = session.evaluate_entry_risk(BOT5, "56983", 65, 136.5)
    assert approved is False
    assert "TRADING_HALTED" in reason


def test_b9_unavailable_broker_state_halts_trading(tmp_path):
    session = _make_session(tmp_path)
    result = session.reconcile_with_broker(broker_positions=None, broker_available=False)
    assert result.halt_required is True
    assert "BROKER_STATE_UNAVAILABLE" in result.reason
    assert session.requires_reconciliation is True


def test_b9_paper_mode_empty_broker_book_is_reconciled(tmp_path):
    """In paper mode the broker book is legitimately empty; that is not a mismatch."""
    assert Config.LIVE_TRADING_ENABLED is False
    session = _make_session(tmp_path)
    session.bot_states[BOT5]["active_trade"] = _open_trade()

    result = session.reconcile_with_broker(broker_positions=[], broker_available=True)
    assert result.reconciled is True
    assert session.requires_reconciliation is False


def test_b9_reconciler_sends_no_orders():
    """The reconciler must be read-only."""
    src = open("src/execution/position_reconciler.py", encoding="utf-8").read()
    for banned in [".post(", ".put(", ".patch(", ".delete(", "place_order"]:
        assert banned not in src, f"Reconciler must never mutate broker state: {banned}"


# ─── B12: PRODUCTION HTTP METHOD SAFETY ───

@pytest.mark.parametrize("verb", ["post", "put", "patch", "delete"])
def test_b12_all_mutating_verbs_blocked_on_broker_adapter(verb):
    adapter = DhanBrokerAdapter(client_id="x", access_token="y")
    with pytest.raises(RuntimeError) as exc:
        getattr(adapter.session, verb)("https://api.dhan.co/v2/orders/12345")
    assert "CRITICAL SAFETY LOCK TRIGGERED" in str(exc.value)


@pytest.mark.parametrize("verb", ["post", "put", "patch", "delete"])
def test_b12_all_mutating_verbs_blocked_on_paper_sandbox(verb, tmp_path):
    sandbox = DhanPaperSandbox(client_id="x", access_token="y", env="prod", state_dir=str(tmp_path))
    with pytest.raises(RuntimeError) as exc:
        getattr(sandbox.session, verb)("https://api.dhan.co/v2/orders")
    assert "CRITICAL SAFETY LOCK TRIGGERED" in str(exc.value)


def test_b12_cancel_order_cannot_reach_production(tmp_path):
    """cancel_order used an unguarded DELETE; it must now be blocked."""
    adapter = DhanBrokerAdapter(client_id="x", access_token="y")
    assert adapter.cancel_order("12345") is False, "cancel must fail closed, not reach production"


def test_b12_market_data_reads_are_not_blocked():
    """The barrier must not break legitimate read-only market data calls."""
    adapter = DhanBrokerAdapter(client_id="x", access_token="y")
    with patch.object(type(adapter.session), "request", return_value=None):
        try:
            adapter.session.post("https://api.dhan.co/v2/marketfeed/quote", json={})
        except RuntimeError as e:
            pytest.fail(f"Market data POST must not be blocked: {e}")
        except Exception:
            pass  # network failure is fine; only the safety lock matters here


# ─── B14: LIVE MICROSTRUCTURE GATE ───

def test_b14_inverted_book_rejected_by_live_gate():
    ok, reason = MultiBotLiveSession.validate_entry_microstructure(
        bid=105.0, ask=100.0, quote_timestamp=datetime.now().isoformat())
    assert ok is False
    assert "INVERTED_MARKET_SPREAD" in reason


def test_b14_excessive_spread_rejected_by_live_gate():
    ok, reason = MultiBotLiveSession.validate_entry_microstructure(
        bid=10.0, ask=100.0, quote_timestamp=datetime.now().isoformat())
    assert ok is False
    assert "EXCESSIVE_SPREAD_WIDTH" in reason


def test_b14_stale_quote_rejected_by_live_gate():
    stale = (datetime.now() - timedelta(seconds=600)).isoformat()
    ok, reason = MultiBotLiveSession.validate_entry_microstructure(
        bid=99.5, ask=100.0, quote_timestamp=stale)
    assert ok is False
    assert "DATA_UNAVAILABLE" in reason


def test_b14_missing_executable_side_rejected():
    ok, reason = MultiBotLiveSession.validate_entry_microstructure(
        bid=99.5, ask=None, quote_timestamp=datetime.now().isoformat())
    assert ok is False
    assert "Missing executable ASK" in reason


def test_b14_healthy_quote_accepted():
    ok, reason = MultiBotLiveSession.validate_entry_microstructure(
        bid=99.5, ask=100.0, quote_timestamp=datetime.now().isoformat())
    assert ok is True
    assert reason == "MICROSTRUCTURE_OK"


def test_b14_live_entry_path_uses_the_shared_gate():
    src = open("src/execution/live_paper_session.py", encoding="utf-8").read()
    assert src.count("validate_entry_microstructure(") >= 6, \
        "Every single-leg live entry must run the shared microstructure gate"

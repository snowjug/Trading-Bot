"""
Regression suite for blockers B2 (risk engine wiring) and B13 (portfolio
exposure aggregation), plus B10 (kill-switch restart persistence).

Before the fix the live session instantiated a RiskEngine and then never
consulted it: loss limits, drawdown limits and position caps were inert, and
every audit record hardcoded risk_decision="APPROVED". Multiple bots could also
hold the identical contract because exposure was tracked per strategy label.
"""
from datetime import time as dtime
from unittest.mock import patch

import pytest

from src.config import Config
from src.execution import live_market_bars
from src.execution.live_paper_session import MultiBotLiveSession
from src.execution.live_strategy_adapter import LiveSignal
from src.risk.risk_engine import RiskEngine

SESSION_BAR = {
    "open": 23201.6, "high": 23284.75, "low": 23116.1,
    "close": 23217.6, "volume": 250000.0, "source": "TEST_INTRADAY",
}
BOT5 = "Strategy 5: Velocity-5 Momentum Scalper"


def _mkt():
    return {
        "nifty": {"last": 23217.6, "open": 23201.6},
        "bank": {"last": 56292.4, "open": 56007.6},
        "vix": 13.2,
        "timestamp": None,
    }


def _make_session(tmp_path, **kw):
    live_market_bars.clear_session_bar_cache()
    return MultiBotLiveSession(
        state_file=str(tmp_path / "session.json"),
        reports_dir=tmp_path,
        risk_engine=kw.pop("risk_engine", RiskEngine(kill_switch_file=tmp_path / "ks.json")),
        **kw,
    )


def _open_trade(sec_id="56983", qty=65, price=136.5, contract="NIFTY 23250 CE"):
    return {
        "id": "T1", "contract": contract, "security_id": sec_id, "side": "BUY",
        "qty": qty, "entry_fill": price, "entry_premium": price,
        "target_premium": price * 1.3, "stop_premium": price * 0.85,
        "status": "OPEN", "trade_state": "OPEN", "valuation_status": "LIVE_QUOTE",
        "unrealized_pnl": 0.0,
    }


# ─── B2: RISK ENGINE IS ACTUALLY CONSULTED ───

def test_b2_no_hardcoded_approved_remains_in_source():
    """The hardcoded risk_decision="APPROVED" literal must be gone."""
    src = open("src/execution/live_paper_session.py", encoding="utf-8").read()
    assert 'risk_decision="APPROVED"' not in src


def test_b2_risk_state_is_updated_from_live_portfolio(tmp_path):
    """update_state must receive the real portfolio snapshot."""
    session = _make_session(tmp_path)
    session.bot_states[BOT5]["active_trade"] = _open_trade()
    snap = session.sync_risk_state()

    assert snap["open_positions"] == 1
    assert session.risk_engine.state.open_positions == 1
    assert session.risk_engine.state.equity == snap["equity"]
    assert session.risk_engine.state.last_updated is not None


def test_b2_risk_baseline_uses_deployed_capital_not_engine_default(tmp_path):
    """Peak equity must be seeded from deployed capital, not RiskEngine's default."""
    session = _make_session(tmp_path)
    snap = session.sync_risk_state()
    assert session.risk_engine.state.peak_equity == pytest.approx(snap["allocated_capital"])
    assert session.risk_engine.state.current_drawdown_pct < 0.01


def test_b2_kill_switch_blocks_entry_through_risk_gate(tmp_path):
    risk = RiskEngine(kill_switch_file=tmp_path / "ks.json")
    session = _make_session(tmp_path, risk_engine=risk)
    risk.trip_kill_switch("unit test halt")

    approved, reason = session.evaluate_entry_risk(BOT5, "56983", 65, 136.5)
    assert approved is False
    assert "Kill switch active" in reason


def test_b2_max_drawdown_breach_rejects_entry(tmp_path):
    """A real equity drawdown from settled losses must block new entries."""
    session = _make_session(tmp_path)
    session.sync_risk_state()  # seeds peak equity at deployed capital
    session.bot_states[BOT5]["closed_trades"] = [
        {"id": "L1", "gross_pnl": -40000.0, "statutory_friction": 0.0, "net_pnl": -40000.0}
    ]

    approved, reason = session.evaluate_entry_risk(BOT5, "56983", 65, 136.5)
    assert approved is False
    assert "drawdown" in reason.lower()


def test_b2_daily_loss_limit_breach_rejects_entry(tmp_path):
    """Settled losses past the daily limit must block new entries."""
    risk = RiskEngine(kill_switch_file=tmp_path / "ks.json", max_portfolio_drawdown=0.95)
    session = _make_session(tmp_path, risk_engine=risk)
    session.sync_risk_state()
    session.bot_states[BOT5]["closed_trades"] = [
        {"id": "L1", "gross_pnl": -5000.0, "statutory_friction": 0.0, "net_pnl": -5000.0}
    ]

    approved, reason = session.evaluate_entry_risk(BOT5, "56983", 65, 136.5)
    assert approved is False
    assert "loss limit" in reason.lower()


def test_b2_weekly_loss_limit_breach_rejects_entry(tmp_path):
    """The weekly loss limit is enforced from real settled P&L."""
    risk = RiskEngine(
        kill_switch_file=tmp_path / "ks.json",
        max_portfolio_drawdown=0.95,
        daily_loss_limit=0.95,
    )
    session = _make_session(tmp_path, risk_engine=risk)
    session.sync_risk_state()
    session.bot_states[BOT5]["closed_trades"] = [
        {"id": "L1", "gross_pnl": -7000.0, "statutory_friction": 0.0, "net_pnl": -7000.0}
    ]

    approved, reason = session.evaluate_entry_risk(BOT5, "56983", 65, 136.5)
    assert approved is False
    assert "loss limit" in reason.lower()


def test_b2_max_simultaneous_positions_rejects_entry(tmp_path):
    """The open-position cap is enforced from real open positions."""
    risk = RiskEngine(kill_switch_file=tmp_path / "ks.json", max_simultaneous_positions=1)
    session = _make_session(tmp_path, risk_engine=risk)
    session.bot_states["Strategy 3: Confluence Gamma Scalper"]["active_trade"] = _open_trade(sec_id="57023")

    approved, reason = session.evaluate_entry_risk(BOT5, "56983", 65, 136.5)
    assert approved is False
    assert "Max positions" in reason


def test_b2_clean_state_approves_entry(tmp_path):
    """A clean portfolio must still be tradable — the gate is not a blanket block."""
    session = _make_session(tmp_path)
    approved, reason = session.evaluate_entry_risk(BOT5, "56983", 65, 136.5)
    assert approved is True
    assert reason == "RISK_APPROVED"


def test_b2_risk_rejection_reaches_the_audit_trail(tmp_path):
    """A risk rejection must be recorded with its real reason, not APPROVED."""
    risk = RiskEngine(kill_switch_file=tmp_path / "ks.json")
    session = _make_session(tmp_path, risk_engine=risk)
    session.evaluate_entry_risk(BOT5, "56983", 65, 136.5)
    assert session._last_risk_decision() == "APPROVED"

    risk.trip_kill_switch("halt for audit trail test")
    session._risk_verdict_cache = {}
    session.evaluate_entry_risk(BOT5, "56983", 65, 136.5)
    decision = session._last_risk_decision()
    assert decision.startswith("REJECTED")
    assert "Kill switch" in decision


def test_b2_decision_is_not_evaluated_when_gate_never_ran(tmp_path):
    """Pre-risk rejections must not claim an approval that never happened."""
    session = _make_session(tmp_path)
    assert session._last_risk_decision() == "NOT_EVALUATED"


# ─── B13: PORTFOLIO EXPOSURE AGGREGATION ───

def test_b13_exposure_aggregates_across_strategy_labels(tmp_path):
    """Two bots in the same contract must aggregate into one exposure entry."""
    session = _make_session(tmp_path)
    session.bot_states[BOT5]["active_trade"] = _open_trade()
    session.bot_states["Strategy 3: Confluence Gamma Scalper"]["active_trade"] = _open_trade()

    snap = session.portfolio_snapshot()
    exposure = snap["contract_exposure"]["56983"]
    assert len(exposure["bots"]) == 2
    assert exposure["qty"] == 130
    assert exposure["notional"] == pytest.approx(2 * 65 * 136.5)


def test_b13_second_bot_in_same_contract_is_rejected(tmp_path):
    """The exact concentration that occurred in the 2026-09-17 session is blocked."""
    session = _make_session(tmp_path)
    session.bot_states["Strategy 3: Confluence Gamma Scalper"]["active_trade"] = _open_trade()

    approved, reason = session.evaluate_entry_risk(BOT5, "56983", 65, 136.5)
    assert approved is False
    assert "PORTFOLIO_CONCENTRATION" in reason
    assert "Strategy 3" in reason


def test_b13_different_contract_is_still_allowed(tmp_path):
    """Concentration control must not block genuine diversification."""
    session = _make_session(tmp_path)
    session.bot_states["Strategy 3: Confluence Gamma Scalper"]["active_trade"] = _open_trade(sec_id="56983")

    approved, reason = session.evaluate_entry_risk(BOT5, "57023", 65, 136.5)
    assert approved is True, reason


def test_b13_single_contract_notional_cap_enforced(tmp_path):
    """Cumulative exposure to one contract is capped even across strategies."""
    session = _make_session(tmp_path)
    # Allow several bots per contract so the NOTIONAL cap is what binds here
    with patch.object(Config, "MAX_BOTS_PER_CONTRACT", 99):
        # Existing 65 x 170 = 11,050 in contract 57023
        session.bot_states["Strategy 3: Confluence Gamma Scalper"]["active_trade"] = _open_trade(
            sec_id="57023", qty=65, price=170.0)
        # A further 65 x 150 = 9,750 (itself under the 10% per-position cap)
        # takes the contract to 20,800 > 20% of 100,000
        approved, reason = session.evaluate_entry_risk(BOT5, "57023", 65, 150.0)

    assert approved is False
    assert "PORTFOLIO_CONCENTRATION" in reason


def test_b13_total_open_exposure_cap_enforced(tmp_path):
    """Aggregate open exposure across all strategies is capped."""
    risk = RiskEngine(kill_switch_file=tmp_path / "ks.json", max_simultaneous_positions=99)
    session = _make_session(tmp_path, risk_engine=risk)
    # Four distinct contracts at 9,750 each = 39,000, each under the 10% cap
    for i, bot in enumerate([
        "Strategy 1: Apex VRP Engine",
        "Strategy 2: Zen Curvature Overnight",
        "Strategy 3: Confluence Gamma Scalper",
        "Strategy 4: Golden Trend Runner",
    ]):
        session.bot_states[bot]["active_trade"] = _open_trade(sec_id=f"9000{i}", qty=65, price=150.0)

    # A fifth takes the book to 48,750 > 40% of 100,000
    approved, reason = session.evaluate_entry_risk(BOT5, "99999", 65, 150.0)
    assert approved is False
    assert "PORTFOLIO_EXPOSURE" in reason


def test_b13_risk_gate_blocks_the_actual_entry_path(tmp_path):
    """End to end: a concentrated contract must not produce a second position."""
    session = _make_session(tmp_path)
    session.bot_states["Strategy 3: Confluence Gamma Scalper"]["active_trade"] = _open_trade(sec_id="88888")

    bullish = lambda bot, **kw: LiveSignal(
        bot, "X", 1 if bot == BOT5 else 0, 0.85, "NIFTY", reason="STRATEGY_SIGNAL")

    def fake_resolve(spot, vix, option_type, **kwargs):
        return {
            "security_id": "88888", "custom_symbol": "NIFTY TEST CE",
            "trading_symbol": "T", "lot_size": 65, "bid": 99.5, "ask": 100.0,
            "ltp": 99.8, "quote_timestamp": __import__("datetime").datetime.now().isoformat(),
        }

    with patch.object(live_market_bars, "get_today_session_bar", return_value=SESSION_BAR), \
         patch.object(session.strategy_adapter, "evaluate", side_effect=bullish), \
         patch("src.execution.live_paper_session.DhanContractResolver.resolve_option_contract",
               side_effect=fake_resolve):
        session.evaluate_all_bots(_mkt(), current_time=dtime(11, 0))

    assert session.bot_states[BOT5]["active_trade"] is None, \
        "Risk gate must stop a second strategy entering the same contract"
    rejects = [r for r in session.rejected_signals if "PORTFOLIO_CONCENTRATION" in str(r.get("reason"))]
    assert rejects, "Portfolio rejection must appear in the audit trail"


# ─── B10: KILL-SWITCH RESTART PERSISTENCE ───

def test_b10_kill_switch_survives_process_restart(tmp_path):
    """Trip -> persist -> restart -> still active and still blocking entries."""
    ks_file = tmp_path / "ks.json"

    risk1 = RiskEngine(kill_switch_file=ks_file)
    assert risk1.state.is_kill_switch_active is False
    risk1.trip_kill_switch("catastrophic data loss")
    assert ks_file.exists(), "Kill switch must be persisted to disk"

    # Simulate a completely fresh process
    risk2 = RiskEngine(kill_switch_file=ks_file)
    assert risk2.state.is_kill_switch_active is True, "Kill switch must survive restart"
    assert "catastrophic data loss" in risk2.state.kill_switch_reason

    # And it must still block trading after the restart
    assert risk2.can_trade(100000.0) is False
    decision = risk2.evaluate_trade("NIFTY", 1, 100.0)
    assert decision.approved is False
    assert "Kill switch active" in decision.rejection_reason

    session = _make_session(tmp_path, risk_engine=risk2)
    approved, reason = session.evaluate_entry_risk(BOT5, "56983", 65, 136.5)
    assert approved is False
    assert "Kill switch" in reason


def test_b10_explicit_reset_clears_persisted_state(tmp_path):
    """Only an explicit reset may clear the persisted kill switch."""
    ks_file = tmp_path / "ks.json"
    risk1 = RiskEngine(kill_switch_file=ks_file)
    risk1.trip_kill_switch("halt")
    risk1.reset_kill_switch()

    risk2 = RiskEngine(kill_switch_file=ks_file)
    assert risk2.state.is_kill_switch_active is False

"""
Regression suite for the first clean forward paper session.

Covers exactly two preparation requirements:
  1. Bots 1 and 2 have enough AUTHENTIC history to evaluate (min_data_points=200
     is unchanged; the history was extended, not the requirement lowered).
  2. Broker reconciliation runs automatically on every live-paper cycle, stays
     read-only, and halts new entries on mismatch or broker unavailability.
"""
from datetime import date, datetime, time as dtime
from unittest.mock import patch

import pandas as pd
import pytest

from src.execution import live_market_bars
from src.execution.live_paper_session import MultiBotLiveSession
from src.execution.live_strategy_adapter import STRATEGY_BINDINGS, LiveStrategyAdapter
from src.risk.risk_engine import RiskEngine

BOT1 = "Strategy 1: Apex VRP Engine"
BOT2 = "Strategy 2: Zen Curvature Overnight"
BOT5 = "Strategy 5: Velocity-5 Momentum Scalper"

SESSION_BAR = {
    "open": 23201.6, "high": 23284.75, "low": 23116.1,
    "close": 23217.6, "volume": 250000.0, "source": "TEST_INTRADAY",
}


def _make_session(tmp_path, **kw):
    live_market_bars.clear_session_bar_cache()
    return MultiBotLiveSession(
        state_file=str(tmp_path / "session.json"),
        reports_dir=tmp_path,
        risk_engine=RiskEngine(kill_switch_file=tmp_path / "ks.json"),
        **kw,
    )


def _mkt():
    return {
        "nifty": {"last": 23217.6, "open": 23201.6},
        "bank": {"last": 56292.4, "open": 56007.6},
        "vix": 13.2, "timestamp": None,
    }


def _open_trade(sec_id="56983", qty=65, price=136.5):
    return {
        "id": "T1", "contract": "NIFTY 23250 CE", "security_id": sec_id, "side": "BUY",
        "qty": qty, "entry_fill": price, "entry_premium": price,
        "target_premium": price * 1.3, "stop_premium": price * 0.85,
        "status": "OPEN", "trade_state": "OPEN", "valuation_status": "LIVE_QUOTE",
        "unrealized_pnl": 0.0, "quote_timestamp": datetime.now().isoformat(),
        "current_bid": price, "current_ask": price + 0.5,
    }


# ─── HISTORY DEPTH FOR BOTS 1 AND 2 ───

@pytest.mark.parametrize("symbol", ["NIFTY", "BANKNIFTY", "INDIAVIX"])
def test_index_history_has_at_least_200_bars(symbol):
    """Every index series must clear the deepest strategy requirement."""
    hist = live_market_bars.load_daily_history(symbol, before_day=date(2026, 9, 17))
    assert hist is not None
    assert len(hist) >= 200, f"{symbol} has only {len(hist)} bars; need >= 200"


def test_min_data_points_were_not_lowered():
    """The requirement must be met by more data, never by weakening the strategy."""
    from src.strategies.curvature_credit_spread import CurvatureCreditSpreadStrategy
    from src.strategies.options_theta import NiftyWeeklyIronCondorStrategy

    assert NiftyWeeklyIronCondorStrategy.min_data_points == 200
    assert CurvatureCreditSpreadStrategy.min_data_points == 200


@pytest.mark.parametrize("bot", [BOT1, BOT2])
def test_bots_1_and_2_history_blocker_is_resolved(bot):
    """
    The HISTORY blocker is gone: these bots no longer fail for lack of bars.

    They are now blocked by the separate, deliberate STRATEGY_PARITY_UNRESOLVED
    gate (Codex CRITICAL #3/#4) — a different and explicitly documented reason.
    """
    adapter = LiveStrategyAdapter()
    sig = adapter.evaluate(
        bot, session_bar=SESSION_BAR, today_vix=13.2, trading_day=date(2026, 9, 17)
    )
    assert "authentic bar/VIX state unavailable" not in sig.reason,         "history depth must no longer be the blocker"
    assert sig.reason.startswith("STRATEGY_PARITY_UNRESOLVED")
    assert sig.direction == 0, "a parity-unresolved bot must never emit a tradable signal"


@pytest.mark.parametrize("bot", [BOT1, BOT2])
def test_bots_1_and_2_have_sufficient_history_when_parity_gate_lifted(bot):
    """
    Proves the underlying data requirement is genuinely satisfied: with the
    parity gate bypassed the strategy evaluates on real bars instead of
    reporting DATA_UNAVAILABLE.
    """
    from src.execution.live_strategy_adapter import STRATEGY_BINDINGS

    adapter = LiveStrategyAdapter()
    binding = dict(STRATEGY_BINDINGS[bot])
    binding["parity"] = "PASS"
    with patch.dict(STRATEGY_BINDINGS, {bot: binding}):
        sig = adapter.evaluate(
            bot, session_bar=SESSION_BAR, today_vix=13.2, trading_day=date(2026, 9, 17)
        )
    assert "authentic bar/VIX state unavailable" not in sig.reason
    assert sig.reason in ("STRATEGY_SIGNAL", "NO_SIGNAL: strategy flat")


def test_all_six_bots_can_evaluate():
    adapter = LiveStrategyAdapter()
    for bot in STRATEGY_BINDINGS:
        sig = adapter.evaluate(
            bot, session_bar=SESSION_BAR, today_vix=13.2, trading_day=date(2026, 9, 17)
        )
        assert "authentic bar/VIX state unavailable" not in sig.reason,             f"{bot} still blocked by insufficient history"


@pytest.mark.parametrize("symbol", ["NIFTY", "BANKNIFTY", "INDIAVIX"])
def test_history_is_causal_sorted_and_unfabricated(symbol):
    """Extended history must stay strictly historical, ordered and unfabricated."""
    hist = live_market_bars.load_daily_history(symbol, before_day=date(2026, 9, 17))
    assert hist is not None
    dates = pd.to_datetime(hist["datetime"]).dt.date
    assert (dates < date(2026, 9, 17)).all(), "history must stop before the trading day"
    assert list(dates) == sorted(dates), "history must be chronological"
    assert not hist["datetime"].duplicated().any(), "duplicate bars indicate a bad merge"
    assert hist[["open", "high", "low", "close"]].notna().all().all(), "no empty OHLC rows"
    assert (hist[["open", "high", "low", "close"]] > 0).all().all(), "no zero/negative prices"


def test_backfill_script_is_backward_only():
    """The backfill must never be able to introduce future bars."""
    src = open("scripts/backfill_index_history.py", encoding="utf-8").read()
    assert "end=earliest" in src, "fetch window must terminate at the earliest existing bar"
    assert "< earliest" in src, "backfill must filter to strictly earlier bars"


# ─── AUTOMATIC PER-CYCLE RECONCILIATION ───

def test_reconciliation_runs_every_cycle(tmp_path):
    """evaluate_all_bots must invoke reconciliation on each cycle."""
    session = _make_session(tmp_path)
    calls = []
    with patch.object(session, "reconcile_cycle", side_effect=lambda: calls.append(1)), \
         patch.object(live_market_bars, "get_today_session_bar", return_value=SESSION_BAR):
        session.evaluate_all_bots(_mkt(), current_time=dtime(11, 0))
        session.evaluate_all_bots(_mkt(), current_time=dtime(11, 0))
    assert len(calls) == 2, "reconciliation must run on every cycle, not once"


def test_reconcile_cycle_queries_broker_when_configured(tmp_path):
    session = _make_session(tmp_path)
    from src.execution import position_reconciler

    flat = position_reconciler.BrokerSnapshot(
        status=position_reconciler.BrokerStateStatus.AVAILABLE_FLAT)
    with patch.object(position_reconciler, "broker_source_configured", return_value=True), \
         patch.object(position_reconciler, "fetch_broker_snapshot",
                      return_value=flat) as fetch:
        result = session.reconcile_cycle()

    assert fetch.called, "a configured broker source must actually be queried"
    assert result is not None and result.reconciled is True


def test_auto_reconcile_can_be_disabled_explicitly(tmp_path):
    session = _make_session(tmp_path, auto_reconcile=False)
    assert session.reconcile_cycle() is None


def test_cycle_mismatch_halts_new_entries(tmp_path):
    """A broker position with no local counterpart must halt entries mid-session."""
    session = _make_session(tmp_path)
    from src.execution import position_reconciler

    with patch.object(position_reconciler, "broker_source_configured", return_value=True), \
         patch.object(position_reconciler, "fetch_broker_positions_readonly",
                      return_value=([{"securityId": "99999", "netQty": 75}], True)), \
         patch.object(live_market_bars, "get_today_session_bar", return_value=SESSION_BAR):
        session.evaluate_all_bots(_mkt(), current_time=dtime(11, 0))

    assert session.requires_reconciliation is True
    approved, reason = session.evaluate_entry_risk(BOT5, "56983", 65, 136.5)
    assert approved is False
    assert "TRADING_HALTED" in reason


def test_cycle_broker_outage_halts_new_entries(tmp_path):
    """An outage while credentials exist is a real failure and must halt entries."""
    session = _make_session(tmp_path)
    from src.execution import position_reconciler

    with patch.object(position_reconciler, "broker_source_configured", return_value=True), \
         patch.object(position_reconciler, "fetch_broker_positions_readonly",
                      return_value=(None, False)):
        result = session.reconcile_cycle()

    assert result.halt_required is True
    assert "BROKER_STATE_UNAVAILABLE" in result.reason
    assert session.requires_reconciliation is True


def test_reconciliation_halt_does_not_block_eod_squareoff(tmp_path):
    """A halt must stop NEW entries, never the closing of an existing position."""
    session = _make_session(tmp_path)
    session.bot_states[BOT5]["active_trade"] = _open_trade()
    session.requires_reconciliation = True
    session.reconciliation_reason = "POSITION_MISMATCH: injected"

    closed = session.handle_overdue_eod(current_time=dtime(15, 50))
    assert closed == 1
    assert session.bot_states[BOT5]["active_trade"] is None


def test_reconciliation_remains_read_only():
    """The reconciliation path must contain no order-mutating call."""
    src = open("src/execution/position_reconciler.py", encoding="utf-8").read()
    for banned in [".post(", ".put(", ".patch(", ".delete(", "place_order", "cancel_order"]:
        assert banned not in src, f"reconciler must stay read-only: found {banned}"


def test_runner_refuses_to_start_without_broker_source(tmp_path, monkeypatch):
    """A session that cannot be reconciled must not start at all."""
    import src.execution.live_paper_session as lps
    from src.execution import position_reconciler

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(position_reconciler, "broker_source_configured", lambda: False)

    with pytest.raises(RuntimeError) as exc:
        lps.run_multi_bot_monitor(duration_seconds=1)
    assert "BROKER SOURCE NOT CONFIGURED" in str(exc.value)

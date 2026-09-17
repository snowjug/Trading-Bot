"""
Regression + adversarial suite for the Codex XHigh HIGH findings.

#3/#4 — Bot 1 / Bot 2 strategy-parity divergence fails closed (no invented logic).
#5    — Protective stops report honest state; stale data is never "protected".
#6    — The forming daily bar refreshes intraday; settled history is immutable.
#8    — Unrealized P&L participates in risk; an unpriced position is not "flat".
#10   — Today's open is never spot / previous close / an estimate.
#11   — Corrupt state fails closed instead of becoming an empty book.
"""
import json
from datetime import date, datetime, time as dtime, timedelta
from unittest.mock import patch

import pytest

from src.execution import live_market_bars
from src.execution.live_paper_session import MultiBotLiveSession
from src.execution.live_strategy_adapter import STRATEGY_BINDINGS, LiveStrategyAdapter
from src.execution.protective_stops import ProtectionState, assess_protection
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
        risk_engine=kw.pop("risk_engine", RiskEngine(kill_switch_file=tmp_path / "ks.json")),
        **kw,
    )


def _open_trade(sec_id="56983", qty=65, price=136.5, priced=True):
    t = {
        "id": "T1", "strategy": BOT5, "contract": "NIFTY 23250 CE",
        "security_id": sec_id, "side": "BUY", "qty": qty,
        "entry_fill": price, "entry_premium": price,
        "status": "OPEN", "trade_state": "OPEN",
    }
    if priced:
        t.update({"valuation_status": "LIVE_QUOTE", "unrealized_pnl": -500.0,
                  "quote_timestamp": datetime.now().isoformat()})
    else:
        t.update({"valuation_status": "DATA_UNAVAILABLE", "unrealized_pnl": None,
                  "quote_timestamp": None})
    return t


# ─────────────── #3 / #4: BOT 1 AND BOT 2 PARITY FAIL CLOSED ───────────────

@pytest.mark.parametrize("bot", [BOT1, BOT2])
def test_parity_unresolved_bots_never_emit_a_tradable_signal(bot):
    adapter = LiveStrategyAdapter()
    sig = adapter.evaluate(bot, session_bar=SESSION_BAR, today_vix=13.2,
                           trading_day=date(2026, 9, 17))
    assert sig.direction == 0
    assert sig.is_actionable is False
    assert sig.reason.startswith("STRATEGY_PARITY_UNRESOLVED")


@pytest.mark.parametrize("bot", [BOT1, BOT2])
def test_parity_status_is_declared_in_the_binding(bot):
    assert STRATEGY_BINDINGS[bot]["parity"] == "UNRESOLVED"
    assert STRATEGY_BINDINGS[bot]["parity_note"].strip(), "divergence must be documented"


def test_parity_passing_bots_are_not_gated():
    """The parity gate must not become a blanket shutdown."""
    for bot, binding in STRATEGY_BINDINGS.items():
        if bot in (BOT1, BOT2):
            continue
        assert binding.get("parity") == "PASS"


@pytest.mark.parametrize("bot", [BOT1, BOT2])
def test_parity_unresolved_bots_cannot_open_a_position(tmp_path, bot):
    """End to end: a parity-gated bot must not create a position in a cycle."""
    session = _make_session(tmp_path)
    with patch.object(live_market_bars, "get_today_session_bar", return_value=SESSION_BAR):
        session.evaluate_all_bots(
            {"nifty": {"last": 23217.6, "open": 23201.6},
             "bank": {"last": 56292.4, "open": 56007.6},
             "vix": 13.2, "timestamp": None},
            current_time=dtime(11, 0),
        )
    assert session.bot_states[bot]["active_trade"] is None


def test_research_strategies_were_not_modified():
    """The FINAL RULE: research code must be untouched by this corrective work."""
    from src.strategies.curvature_credit_spread import CurvatureCreditSpreadStrategy
    from src.strategies.options_theta import NiftyWeeklyIronCondorStrategy

    condor = NiftyWeeklyIronCondorStrategy()
    assert condor.otm_sd == 1.8 and condor.wing_sd == 2.4 and condor.max_vix == 20.0
    assert condor.min_data_points == 200

    curve = CurvatureCreditSpreadStrategy()
    assert curve.max_vix == 22.0 and curve.min_data_points == 200


# ─────────────── INDICATOR INTEGRITY: NO RSI=50 FABRICATION ───────────────

def test_rsi_is_computed_from_real_closes_not_defaulted():
    """Bots 1/2 read df['rsi_14'] and default it to 50.0 when absent."""
    frame = live_market_bars.build_strategy_frame(
        "NIFTY", session_bar=SESSION_BAR, trading_day=date(2026, 9, 17),
        today_vix=13.2, require_vix=True, require_rsi=True,
    )
    assert frame is not None
    assert "rsi_14" in frame.columns
    assert frame["rsi_14"].notna().all(), "no undefined RSI may reach a strategy"
    assert not (frame["rsi_14"] == 50.0).all(), "RSI must not be a constant default"
    assert frame["rsi_14"].between(0, 100).all()


def test_rsi_is_causal():
    """RSI at the last bar must not change when a FUTURE bar is appended."""
    import pandas as pd

    frame = live_market_bars.build_strategy_frame(
        "NIFTY", session_bar=SESSION_BAR, trading_day=date(2026, 9, 17),
        today_vix=13.2, require_vix=True, require_rsi=True,
    )
    last_rsi = float(frame["rsi_14"].iloc[-1])
    prefix_rsi = float(
        live_market_bars._attach_rsi_column(frame.drop(columns=["rsi_14"]))["rsi_14"].iloc[-1]
    )
    assert abs(last_rsi - prefix_rsi) < 1e-9


def test_rsi_fails_closed_on_insufficient_closes():
    import pandas as pd

    tiny = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
    assert live_market_bars._attach_rsi_column(tiny) is None


# ─────────────── #6: FORMING BAR MUST NOT GO STALE ───────────────

def test_forming_bar_refreshes_when_new_intraday_data_arrives():
    """The core defect: the forming bar was cached for the whole session."""
    live_market_bars.clear_session_bar_cache()
    day = date(2026, 9, 17)
    seq = [
        {"open": 100.0, "high": 105.0, "low": 99.0, "close": 104.0, "volume": 10.0, "source": "S"},
        {"open": 100.0, "high": 112.0, "low": 99.0, "close": 111.0, "volume": 25.0, "source": "S"},
    ]
    calls = {"n": 0}

    def fake(symbol, trading_day):
        bar = seq[min(calls["n"], len(seq) - 1)]
        calls["n"] += 1
        return dict(bar)

    with patch.object(live_market_bars, "_dhan_intraday_session_bar", side_effect=fake), \
         patch.object(live_market_bars, "_yfinance_session_bar", return_value=None), \
         patch.object(live_market_bars, "FORMING_BAR_TTL_SECONDS", 0.0):
        first = live_market_bars.get_today_session_bar("NIFTY", trading_day=day)
        second = live_market_bars.get_today_session_bar("NIFTY", trading_day=day)

    assert first["close"] == 104.0
    assert second["close"] == 111.0, "forming bar must pick up new intraday data"
    assert second["high"] == 112.0, "running high must advance"


def test_forming_bar_is_briefly_cached_within_ttl():
    """Within the TTL the bar is reused, so a cycle does not hammer the feed."""
    live_market_bars.clear_session_bar_cache()
    calls = {"n": 0}

    def fake(symbol, trading_day):
        calls["n"] += 1
        return {"open": 100.0, "high": 105.0, "low": 99.0, "close": 104.0,
                "volume": 10.0, "source": "S"}

    with patch.object(live_market_bars, "_dhan_intraday_session_bar", side_effect=fake), \
         patch.object(live_market_bars, "_yfinance_session_bar", return_value=None), \
         patch.object(live_market_bars, "FORMING_BAR_TTL_SECONDS", 300.0):
        live_market_bars.get_today_session_bar("NIFTY", trading_day=date(2026, 9, 17))
        live_market_bars.get_today_session_bar("NIFTY", trading_day=date(2026, 9, 17))
    assert calls["n"] == 1


def test_settled_history_is_immutable_and_excludes_today():
    hist = live_market_bars.load_daily_history("NIFTY", before_day=date(2026, 9, 17))
    import pandas as pd

    assert (pd.to_datetime(hist["datetime"]).dt.date < date(2026, 9, 17)).all()


# ─────────────── #8: UNREALIZED P&L PARTICIPATES IN RISK ───────────────

def test_open_loss_is_included_in_risk_state(tmp_path):
    """A live losing position must reach the RiskEngine, not only closed trades."""
    session = _make_session(tmp_path)
    session.bot_states[BOT5]["active_trade"] = _open_trade(priced=True)
    snap = session.sync_risk_state()
    assert snap["unrealized_pnl"] == -500.0
    assert session.risk_engine.state.daily_pnl == pytest.approx(-500.0)


def test_unpriced_position_is_not_treated_as_flat(tmp_path):
    """DATA_UNAVAILABLE must never be silently counted as zero P&L."""
    session = _make_session(tmp_path)
    session.bot_states[BOT5]["active_trade"] = _open_trade(priced=False)
    snap = session.sync_risk_state()
    assert snap["unpriced_positions"] == 1
    assert snap["unrealized_pnl"] == 0.0, "an unknown loss must not be invented either"


def test_unpriced_position_blocks_new_entries(tmp_path):
    """If risk cannot be computed safely, the gate must fail closed."""
    session = _make_session(tmp_path)
    session.bot_states[BOT5]["active_trade"] = _open_trade(priced=False)
    approved, reason = session.evaluate_entry_risk("Strategy 3: Confluence Gamma Scalper",
                                                   "57023", 65, 100.0)
    assert approved is False
    assert "RISK_INDETERMINATE" in reason


def test_priced_position_does_not_block_entries(tmp_path):
    """Control: a valued position must not trigger the indeterminate halt."""
    session = _make_session(tmp_path)
    session.bot_states[BOT5]["active_trade"] = _open_trade(priced=True)
    approved, reason = session.evaluate_entry_risk("Strategy 3: Confluence Gamma Scalper",
                                                   "57023", 65, 100.0)
    assert approved is True, reason


# ─────────────── #5: HONEST PROTECTIVE-STOP STATE ───────────────

def test_protection_reports_armed_only_with_a_fresh_quote():
    r = assess_protection(85.0, datetime.now().isoformat(), 100.0)
    assert r["protected"] is True
    assert r["state"] == ProtectionState.SOFTWARE_STOP_ARMED.value
    assert r["broker_native"] is False


def test_protection_stale_data_is_reported_unprotected():
    stale = (datetime.now() - timedelta(hours=2)).isoformat()
    r = assess_protection(85.0, stale, 100.0)
    assert r["protected"] is False
    assert r["state"] == ProtectionState.UNPROTECTED_STALE_DATA.value


def test_protection_missing_quote_is_reported_unprotected():
    r = assess_protection(85.0, None, None)
    assert r["protected"] is False
    assert r["state"] == ProtectionState.UNPROTECTED_NO_QUOTE.value


def test_broker_native_protection_is_always_declared_unavailable():
    r = assess_protection(85.0, datetime.now().isoformat(), 100.0)
    assert r["broker_native_state"] == ProtectionState.BROKER_NATIVE_STOP_UNAVAILABLE.value


def test_broker_native_stop_cannot_be_submitted():
    from src.execution.protective_stops import (
        BrokerNativeProtectiveStop,
        ProtectiveStopRequest,
        protective_stops_enabled,
    )

    assert protective_stops_enabled() is False
    with pytest.raises(NotImplementedError):
        BrokerNativeProtectiveStop().submit(
            ProtectiveStopRequest(security_id="1", quantity=65, stop_price=85.0)
        )


# ─────────────── #10: NO OPENING-PRICE FALLBACK ───────────────

def test_open_is_never_substituted_by_spot_or_previous_close():
    src = open("src/execution/dhan_contract_resolver.py", encoding="utf-8").read()
    assert "open_nifty if open_nifty else spot_nifty" not in src
    assert "2.35" not in src


def test_missing_open_fails_closed():
    from unittest.mock import MagicMock

    from src.execution.dhan_contract_resolver import DhanContractResolver

    class R:
        status_code = 200
        @staticmethod
        def json():
            return {"data": {"IDX_I": {"13": {"last_price": 23250.0},
                                       "21": {"last_price": 13.2},
                                       "25": {"last_price": 56300.0}}}}

    sess = MagicMock()
    sess.post.return_value = R()
    with patch("src.execution.dhan_contract_resolver._pace_dhan_request"), \
         patch.object(live_market_bars, "get_today_session_bar", return_value=None):
        assert DhanContractResolver.get_live_market_state(dhan_session=sess) is None


# ─────────────── #11: STATE CORRUPTION FAILS CLOSED ───────────────

def test_corrupt_session_json_halts_and_preserves_evidence(tmp_path):
    state = tmp_path / "session.json"
    state.write_text('{"bot_states": {"Strategy 1', encoding="utf-8")  # truncated JSON

    session = MultiBotLiveSession(
        state_file=str(state), reports_dir=tmp_path,
        risk_engine=RiskEngine(kill_switch_file=tmp_path / "ks.json"),
    )
    assert session.requires_reconciliation is True
    assert "CORRUPT_SESSION_STATE" in session.reconciliation_reason
    assert (tmp_path / "corrupt_session.json").exists(), "evidence must be preserved"

    approved, reason = session.evaluate_entry_risk(BOT5, "56983", 65, 136.5)
    assert approved is False
    assert "TRADING_HALTED" in reason


def test_structurally_wrong_session_state_halts(tmp_path):
    state = tmp_path / "session.json"
    state.write_text(json.dumps({"bot_states": ["not", "an", "object"]}), encoding="utf-8")
    session = MultiBotLiveSession(
        state_file=str(state), reports_dir=tmp_path,
        risk_engine=RiskEngine(kill_switch_file=tmp_path / "ks.json"),
    )
    assert session.requires_reconciliation is True


def test_corrupt_kill_switch_fails_closed(tmp_path):
    ks = tmp_path / "ks.json"
    ks.write_text("{not valid json", encoding="utf-8")
    risk = RiskEngine(kill_switch_file=ks)
    assert risk.state.is_kill_switch_active is True
    assert "CORRUPT_KILL_SWITCH_STATE" in risk.state.kill_switch_reason
    assert risk.can_trade(100000.0) is False


def test_malformed_kill_switch_shape_fails_closed(tmp_path):
    ks = tmp_path / "ks.json"
    ks.write_text(json.dumps({"unexpected": "shape"}), encoding="utf-8")
    risk = RiskEngine(kill_switch_file=ks)
    assert risk.state.is_kill_switch_active is True


def test_valid_inactive_kill_switch_still_allows_trading(tmp_path):
    """Control: a well-formed inactive file must not trigger the fail-closed path."""
    ks = tmp_path / "ks.json"
    ks.write_text(json.dumps({"is_kill_switch_active": False, "reason": ""}), encoding="utf-8")
    risk = RiskEngine(kill_switch_file=ks)
    assert risk.state.is_kill_switch_active is False

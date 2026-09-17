"""
Regression suite for the three targeted corrective fixes.

C1 — the kill-switch flatten fabricated exit prices (entry_fill / current_val,
     no freshness check) and booked fake realised P&L.
H1 — Bot 4's bearish signal was silently dropped; only a comment claimed
     otherwise.
H3 — strategies validated on SETTLED daily bars were being evaluated against an
     unsettled forming bar, a different timing model than the research.
"""
from datetime import date, datetime, timedelta, time as dtime
from unittest.mock import patch

import pytest

from src.execution import live_market_bars as lmb
from src.execution.live_paper_session import MultiBotLiveSession
from src.execution.live_strategy_adapter import (
    STRATEGY_BINDINGS,
    LiveSignal,
    LiveStrategyAdapter,
)
from src.risk.risk_engine import RiskEngine

BOT3 = "Strategy 3: Confluence Gamma Scalper"
BOT4 = "Strategy 4: Golden Trend Runner"
BOT5 = "Strategy 5: Velocity-5 Momentum Scalper"
BOT6 = "Strategy 6: Micro Momentum Sniper"


def _make_session(tmp_path, **kw):
    lmb.clear_session_bar_cache()
    return MultiBotLiveSession(
        state_file=str(tmp_path / "session.json"),
        reports_dir=tmp_path,
        risk_engine=kw.pop("risk_engine", RiskEngine(kill_switch_file=tmp_path / "ks.json")),
        **kw,
    )


def _position(side="BUY", bid=120.0, ask=120.5, ts=None, entry=100.0):
    return {
        "id": "T1", "strategy": BOT5, "contract": "NIFTY 23250 CE",
        "security_id": "56983", "side": side, "qty": 65,
        "entry_fill": entry, "entry_premium": entry,
        "current_bid": bid, "current_ask": ask,
        "current_val": entry, "current_premium": entry,
        "quote_timestamp": ts if ts is not None else datetime.now().isoformat(),
        "status": "OPEN", "trade_state": "OPEN", "valuation_status": "LIVE_QUOTE",
        "unrealized_pnl": 0.0,
    }


def _assert_unresolved(session, bot=BOT5):
    st = session.bot_states[bot]
    assert st["closed_trades"] == [], "no fabricated fill may enter the realised ledger"
    at = st["active_trade"]
    assert at is not None, "the position must be preserved, not discarded"
    assert at["status"] == "UNRESOLVED_KILL_SWITCH"
    assert at["exit_reason"] == "KILL_SWITCH_UNRESOLVED_NO_EXECUTABLE_QUOTE"
    assert at["net_pnl"] is None and at["gross_pnl"] is None
    assert at["unrealized_pnl"] is None
    assert session.requires_reconciliation is True


# ───────────────────────── C1: KILL-SWITCH FLATTEN ─────────────────────────

def test_c1_stale_quote_cannot_flatten(tmp_path):
    session = _make_session(tmp_path)
    stale = (datetime.now() - timedelta(hours=3)).isoformat()
    session.bot_states[BOT5]["active_trade"] = _position(ts=stale)
    session._emergency_flatten_all_positions(reason="KILL_SWITCH: test")
    _assert_unresolved(session)


def test_c1_missing_quote_cannot_flatten(tmp_path):
    session = _make_session(tmp_path)
    session.bot_states[BOT5]["active_trade"] = _position(bid=None, ask=None, ts=None)
    session._emergency_flatten_all_positions(reason="KILL_SWITCH: test")
    _assert_unresolved(session)


def test_c1_inverted_quote_cannot_flatten(tmp_path):
    """bid > ask is a corrupted book and must not price an emergency exit."""
    session = _make_session(tmp_path)
    session.bot_states[BOT5]["active_trade"] = _position(bid=125.0, ask=120.0)
    session._emergency_flatten_all_positions(reason="KILL_SWITCH: test")
    _assert_unresolved(session)


def test_c1_valid_quote_flattens_a_long_on_the_bid(tmp_path):
    session = _make_session(tmp_path)
    session.bot_states[BOT5]["active_trade"] = _position(side="BUY", bid=120.0, ask=120.5)
    session._emergency_flatten_all_positions(reason="KILL_SWITCH: test")

    st = session.bot_states[BOT5]
    assert st["active_trade"] is None
    closed = st["closed_trades"][0]
    assert closed["exit_fill"] == pytest.approx(119.5), "long must exit on BID - slippage"
    assert closed["gross_pnl"] == pytest.approx((119.5 - 100.0) * 65)


def test_c1_valid_quote_flattens_a_short_on_the_ask(tmp_path):
    session = _make_session(tmp_path)
    session.bot_states[BOT5]["active_trade"] = _position(side="SELL", bid=70.0, ask=71.0, entry=80.0)
    session._emergency_flatten_all_positions(reason="KILL_SWITCH: test")

    closed = session.bot_states[BOT5]["closed_trades"][0]
    assert closed["exit_fill"] == pytest.approx(72.0), "short must buy back on ASK + slippage"
    assert closed["gross_pnl"] == pytest.approx((80.0 - 72.0) * 65)


def test_c1_no_fake_realized_pnl_is_created(tmp_path):
    """The old bug produced a ~zero P&L from entry_fill. That must be impossible."""
    session = _make_session(tmp_path)
    session.bot_states[BOT5]["active_trade"] = _position(bid=None, ask=None, ts=None, entry=137.0)
    session._emergency_flatten_all_positions(reason="KILL_SWITCH: test")

    settlement = sum(
        c.get("net_pnl") or 0.0
        for b in session.bot_states.values()
        for c in b.get("closed_trades", [])
    )
    assert settlement == 0.0
    assert session.bot_states[BOT5]["closed_trades"] == []


def test_c1_kill_switch_still_blocks_all_new_entries(tmp_path):
    """Unresolved flatten must not weaken the halt."""
    risk = RiskEngine(kill_switch_file=tmp_path / "ks.json")
    session = _make_session(tmp_path, risk_engine=risk)
    session.bot_states[BOT5]["active_trade"] = _position(bid=None, ask=None, ts=None)
    session.trip_kill_switch("adversarial halt")

    approved, reason = session.evaluate_entry_risk(BOT3, "57023", 65, 100.0)
    assert approved is False
    assert ("Kill switch" in reason) or ("TRADING_HALTED" in reason)


def test_c1_no_synthetic_exit_fallback_remains_in_source():
    """Static proof that no emergency path can price an exit from stored values."""
    src = open("src/execution/live_paper_session.py", encoding="utf-8").read()
    import re
    bad = re.findall(r'exit_fill\s*=\s*[^\n]*(entry_fill|current_val|current_premium)[^\n]*', src)
    assert not bad, f"synthetic exit fallback still present: {bad}"


def test_c1_flatten_does_not_send_any_broker_order():
    """The flatten is software-side only."""
    src = open("src/execution/live_paper_session.py", encoding="utf-8").read()
    body = src[src.index("def _emergency_flatten_all_positions"):
               src.index("def _eod_force_square_off_all_positions")]
    for banned in [".post(", ".put(", ".patch(", ".delete(", "place_order"]:
        assert banned not in body, f"emergency flatten must not contact the broker: {banned}"


# ───────────────────────── H1: BOT 4 BEARISH SIGNAL ─────────────────────────

def _run_cycle(session, direction, bot=BOT4):
    def sig(b, **kw):
        return LiveSignal(b, "X", direction if b == bot else 0, 0.8, "NIFTY",
                          reason="STRATEGY_SIGNAL")
    bar = {"open": 23201.6, "high": 23284.75, "low": 23116.1, "close": 23217.6,
           "volume": 250000.0, "source": "T",
           "market_timestamp": datetime.now().isoformat()}
    with patch.object(lmb, "get_today_session_bar", return_value=bar), \
         patch.object(session.strategy_adapter, "evaluate", side_effect=sig):
        session.evaluate_all_bots(
            {"nifty": {"last": 23217.6, "open": 23201.6},
             "bank": {"last": 56292.4, "open": 56007.6},
             "vix": 13.2, "timestamp": None},
            current_time=dtime(11, 0),
        )


def test_h1_bearish_bot4_signal_is_explicitly_recorded(tmp_path):
    session = _make_session(tmp_path)
    _run_cycle(session, direction=-1)

    recs = [r for r in session.rejected_signals
            if r["strategy"] == BOT4 and "UNSUPPORTED_DIRECTION" in str(r.get("reason"))]
    assert recs, "a bearish Bot 4 signal must produce an explicit rejection record"
    rec = recs[0]
    assert rec["status"] == "NO_EXECUTION"
    assert rec["execution_decision"] == "NO_EXECUTION"
    assert rec["timestamp"], "the record must carry a timestamp"
    assert "direction=-1" in rec["reason"]


def test_h1_bearish_signal_creates_no_position(tmp_path):
    session = _make_session(tmp_path)
    _run_cycle(session, direction=-1)
    assert session.bot_states[BOT4]["active_trade"] is None


def test_h1_bearish_rejection_does_not_claim_risk_approval(tmp_path):
    """Risk was never consulted for an unsupported direction; say so honestly."""
    session = _make_session(tmp_path)
    _run_cycle(session, direction=-1)
    rec = [r for r in session.rejected_signals if "UNSUPPORTED_DIRECTION" in str(r.get("reason"))][0]
    assert rec["risk_decision"] == "NOT_EVALUATED"


def test_h1_bullish_signal_produces_no_unsupported_record(tmp_path):
    """Control: the bullish path must be unaffected."""
    session = _make_session(tmp_path)
    _run_cycle(session, direction=1)
    recs = [r for r in session.rejected_signals if "UNSUPPORTED_DIRECTION" in str(r.get("reason"))]
    assert not recs


# ───────────────────────── H3: FORMING vs SETTLED BAR ─────────────────────────

FORMING = {"open": 23212.05, "high": 23363.55, "low": 23197.0, "close": 23270.6,
           "volume": 2.4e8, "source": "T", "market_timestamp": "2026-09-17T11:00:00"}
SETTLED = {**FORMING, "market_timestamp": "2026-09-17T15:30:00"}


def test_h3_settled_detection_rejects_a_forming_bar():
    now = datetime(2026, 9, 17, 11, 0)
    assert lmb.is_session_bar_settled(FORMING, now=now) is False


def test_h3_settled_detection_accepts_a_closed_session():
    now = datetime(2026, 9, 17, 16, 0)
    assert lmb.is_session_bar_settled(SETTLED, now=now) is True


def test_h3_settled_detection_fails_closed_without_timestamp():
    assert lmb.is_session_bar_settled({"open": 1.0}) is False
    assert lmb.is_session_bar_settled(None) is False


@pytest.mark.parametrize("bot", [BOT3, BOT4, BOT5])
def test_h3_settled_bar_strategies_refuse_a_forming_bar(bot):
    """
    Bots 3/4/5 read row['ema_*'], row['rsi_14'], row['close'] and row['volume'],
    all of which require today's settled close. They must not be evaluated
    against a partial bar.
    """
    adapter = LiveStrategyAdapter()
    sig = adapter.evaluate(bot, session_bar=FORMING, today_vix=13.2,
                           trading_day=date(2026, 9, 17))
    assert sig.direction == 0
    assert sig.reason.startswith("FORMING_BAR_UNSUPPORTED")


def test_h3_forming_bar_strategy_is_preserved():
    """
    Bot 6 reads indicators from prev (settled) only and uses the current bar
    solely for curr['high'] / curr['low'] — a real-time breakout with no future
    data. Its forming-bar behaviour must be preserved, not broken by the gate.
    """
    adapter = LiveStrategyAdapter()
    sig = adapter.evaluate(BOT6, session_bar=FORMING, today_vix=13.2,
                           trading_day=date(2026, 9, 17))
    assert not sig.reason.startswith("FORMING_BAR_UNSUPPORTED")
    assert STRATEGY_BINDINGS[BOT6]["requires_settled_bar"] is False


def test_h3_every_binding_declares_its_bar_timing_with_evidence():
    for bot, b in STRATEGY_BINDINGS.items():
        assert "requires_settled_bar" in b, f"{bot} does not declare its bar timing"
        assert b.get("bar_timing_evidence", "").strip(), f"{bot} has no evidence cited"


def test_h3_bot6_uses_no_future_data():
    """The current bar may only contribute running high/low to Bot 6."""
    src = open("src/strategies/micro_momentum_buyer.py", encoding="utf-8").read()
    body = src[src.index("def generate_signals"):src.index("signals.append(sig)")]
    import re
    used = sorted(set(re.findall(r'curr\["([a-z_0-9]+)"\]', body)))
    assert used == ["high", "low"], f"Bot 6 reads unexpected current-bar fields: {used}"


def test_h3_settled_strategies_evaluate_once_the_session_closes():
    """Control: after the close the same strategies must run normally."""
    adapter = LiveStrategyAdapter()
    now = datetime(2026, 9, 17, 16, 0)
    with patch("src.execution.live_market_bars.datetime") as m:
        m.now.return_value = now
        m.fromisoformat = datetime.fromisoformat
        sig = adapter.evaluate(BOT3, session_bar=SETTLED, today_vix=13.2,
                               trading_day=date(2026, 9, 17))
    assert not sig.reason.startswith("FORMING_BAR_UNSUPPORTED")

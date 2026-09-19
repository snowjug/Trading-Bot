"""
Bot 8 (price action / market structure) and the operational dashboard.

The properties defended here are the ones that decide whether Bot 8's signal means
anything: a swing is never read before the bars that confirm it exist, a break is
only traded on its retest, a failed break is called failed, and every state carries
the structure that produced it. For the dashboard: it must never present stale or
absent data as live.
"""
import json
from datetime import date, datetime, time as dtime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.execution import bot8_price_action as B8
from src.execution import bot_signals as BS


def rising_then_pullback(level: float = 23300.0):
    """
    Break of a confirmed swing high, pullback into the retest zone, then resumption.

    The geometry is chosen so the detector sees what the test claims: the swing
    high at index 4 and the swing low at index 6 are both confirmed (k bars either
    side), while the breakout extreme at index 10 falls inside the final k bars and
    is deliberately NOT confirmed — so the ORIGINAL level stays the operative one.
    The base is deep enough that the measured-move target clears the R:R floor.
    """
    L = level
    return [L - 180, L - 220, L - 150, L - 40, L, L - 60, L - 200,
            L - 40, L - 10, L + 55, L + 58, L + 16, L + 22]


def falling_then_pullback(level: float = 23300.0):
    """Mirror image of `rising_then_pullback`."""
    L = level
    return [L + 180, L + 220, L + 150, L + 40, L, L + 60, L + 200,
            L + 40, L + 10, L - 55, L - 58, L - 16, L - 22]


# ════════════════════ SWING DETECTION / CHRONOLOGY ════════════════════

def test_a_swing_is_never_confirmed_before_its_confirming_bars_exist():
    """
    The core no-hindsight property.

    A pivot at index i requires k bars after it. Truncating the series just after
    the pivot must NOT report it; appending the confirming bars must.
    """
    k = 3
    prices = [100, 101, 102, 110, 103, 102, 101, 100, 99]   # peak at index 3
    early = B8.find_swings(prices[:5], k)[0]
    assert 3 not in early, "a pivot was reported before its confirming bars printed"
    later = B8.find_swings(prices, k)[0]
    assert 3 in later, "the pivot must appear once confirmation exists"


def test_swing_scan_never_reads_the_final_k_bars():
    prices = list(np.linspace(100, 200, 40))
    hi, lo = B8.find_swings(prices, k=3)
    for idx in hi + lo:
        assert idx <= len(prices) - 4


def test_trend_needs_two_confirmed_swings_on_each_leg():
    """
    UPTREND requires a higher high AND a higher low, both confirmed.

    Anything short of that is UNDEFINED or RANGE — a single spike must never be
    promoted to a trend.
    """
    flat = [100, 95, 105, 95, 105, 95, 105, 95, 105, 95, 105, 95, 105]
    assert B8.read_structure(flat, k=2).trend in ("RANGE", "UNDEFINED")
    one_swing = rising_then_pullback()
    st = B8.read_structure(one_swing, k=3)
    assert st.swing_high is not None and st.swing_low is not None
    assert st.prior_swing_high is None
    assert st.trend == "UNDEFINED", "one swing per leg is not a trend"


def test_daily_bias_from_completed_closes():
    up = pd.Series(np.linspace(100, 200, 120))
    assert B8.daily_bias_from(up) == "UPTREND"
    dn = pd.Series(np.linspace(200, 100, 120))
    assert B8.daily_bias_from(dn) == "DOWNTREND"
    assert B8.daily_bias_from(pd.Series([100.0] * 10)) == "UNDEFINED"


# ════════════════════ STATE MACHINE ════════════════════

def test_break_then_retest_then_resume_produces_a_long_entry():
    sig = B8.evaluate(rising_then_pullback(), atr=200.0, vix=12.0,
                      now=dtime(11, 0), daily_bias="UPTREND", k=3)
    assert sig.state == "LONG_ENTRY"
    assert sig.direction == 1
    assert sig.setup_type == "BREAKOUT_RETEST_LONG"
    assert sig.breakout_state == "BROKEN_UP" and sig.retest_state == "HELD"
    assert sig.entry and sig.stop and sig.target
    assert sig.stop < sig.entry < sig.target, "long: stop below entry below target"
    assert sig.risk_reward and sig.risk_reward >= B8.MIN_RR


def test_breakdown_then_retest_produces_a_short_entry():
    sig = B8.evaluate(falling_then_pullback(), atr=200.0, vix=12.0,
                      now=dtime(11, 0), daily_bias="DOWNTREND", k=3)
    assert sig.state == "SHORT_ENTRY"
    assert sig.direction == -1
    assert sig.target < sig.entry < sig.stop, "short: target below entry below stop"


def test_counter_structure_breaks_are_refused():
    """Trading a break against the higher-timeframe structure is the thing to avoid."""
    sig = B8.evaluate(rising_then_pullback(), atr=200.0, vix=12.0,
                      now=dtime(11, 0), daily_bias="DOWNTREND", k=3)
    assert sig.state == "WAIT" and "COUNTER_STRUCTURE" in sig.reason
    sig = B8.evaluate(falling_then_pullback(), atr=200.0, vix=12.0,
                      now=dtime(11, 0), daily_bias="UPTREND", k=3)
    assert sig.state == "WAIT" and "COUNTER_STRUCTURE" in sig.reason


def test_an_extended_break_is_armed_not_entered():
    """Chasing the impulse is exactly what the retest rule exists to prevent."""
    p = rising_then_pullback()[:11] + [23360.0]      # still extended, no pullback
    sig = B8.evaluate(p, atr=200.0, vix=12.0, now=dtime(11, 0), daily_bias="UPTREND", k=3)
    assert sig.state == "ARMED"
    assert sig.retest_state == "NONE" and sig.entry is None


def test_a_failed_break_is_called_failed():
    p = rising_then_pullback()[:11] + [23090.0]             # gave the level back
    sig = B8.evaluate(p, atr=200.0, vix=12.0, now=dtime(11, 0), daily_bias="UPTREND", k=3)
    assert sig.state == "REJECTED"
    assert sig.breakout_state == "FAILED" and sig.direction == 0
    assert sig.entry is None, "a failed break must not carry an entry"


def test_gates_refuse_before_any_structure_is_read():
    p = rising_then_pullback()
    for kwargs, expect in (
        (dict(vix=None), "NO_VIX"),
        (dict(vix=40.0), "VIX_TOO_HIGH"),
        (dict(atr=0.0), "NO_ATR"),
        (dict(now=dtime(9, 20)), "AWAITING_STRUCTURE"),
        (dict(now=dtime(15, 30)), "TOO_LATE_TO_OPEN"),
    ):
        base = dict(prices=p, atr=200.0, vix=12.0, now=dtime(11, 0), daily_bias="UPTREND")
        base.update(kwargs)
        sig = B8.evaluate(**base)
        assert sig.state == "WAIT" and expect in sig.reason


def test_insufficient_bars_waits():
    sig = B8.evaluate([100.0, 101.0, 102.0], atr=200.0, vix=12.0,
                      now=dtime(11, 0), daily_bias="UPTREND")
    assert sig.state == "WAIT" and "INSUFFICIENT_BARS" in sig.reason


def test_every_signal_carries_its_structure_and_reason():
    for p, bias in ((rising_then_pullback(), "UPTREND"),
                    (falling_then_pullback(), "DOWNTREND"),
                    ([23300.0] * 20, "RANGE")):
        sig = B8.evaluate(p, atr=200.0, vix=12.0, now=dtime(11, 0), daily_bias=bias, k=3)
        assert sig.reason and len(sig.reason) > 5, "a state must always explain itself"
        assert sig.structure is not None
        assert sig.state in ("WAIT", "ARMED", "LONG_SETUP", "SHORT_SETUP",
                             "LONG_ENTRY", "SHORT_ENTRY", "REJECTED")


def test_risk_reward_floor_is_enforced_and_is_not_circular():
    """
    A setup that does not pay for its own spread is not taken.

    This also pins a fix: the target used to be derived from min_rr, which made the
    check circular — raising the floor raised the target with it and the test could
    never bind. The target is now a structural measured move, so the floor filters.
    """
    ok = B8.evaluate(rising_then_pullback(), atr=200.0, vix=12.0, now=dtime(11, 0),
                     daily_bias="UPTREND", k=3)
    assert ok.state == "LONG_ENTRY"
    blocked = B8.evaluate(rising_then_pullback(), atr=200.0, vix=12.0, now=dtime(11, 0),
                          daily_bias="UPTREND", k=3, min_rr=99.0)
    assert blocked.state == "WAIT" and "RR_BELOW_THRESHOLD" in blocked.reason
    assert ok.risk_reward == blocked.risk_reward,         "the measured-move target must not move with the floor"


# ════════════════════ WRAPPER INTO THE EXECUTION LAYER ════════════════════

@pytest.fixture(scope="module")
def hist():
    raw = pd.read_parquet("data/raw/nse/index_history/nse_index_daily.parquet")
    n = raw[raw["symbol"] == "NIFTY50"][["datetime", "open", "high", "low", "close"]]
    v = raw[raw["symbol"] == "INDIAVIX"][["datetime", "close"]].rename(columns={"close": "vix"})
    d = n.merge(v, on="datetime", how="inner").sort_values("datetime").reset_index(drop=True)
    d["volume"] = 0.0
    return d


def test_wrapper_emits_a_tradable_decision_with_protective_levels(hist):
    today = pd.to_datetime(hist["datetime"]).dt.date.max()
    dec = BS.bot8_price_action(23330.0, 12.0, hist, today, dtime(11, 0),
                               rising_then_pullback(), 23400.0, 23100.0)
    if dec.action == "ENTER":
        assert dec.legs and dec.legs[0].side == "BUY"
        assert dec.target_pnl > 0 and dec.stop_pnl < 0
        assert dec.trail_trigger and dec.trail_giveback and dec.flat_by == "15:10"
        for f in ("state", "setup_type", "breakout_state", "retest_state",
                  "swing_high", "swing_low", "risk_reward", "daily_bias"):
            assert f in dec.meta, f"meta missing {f}"
    else:
        assert dec.reason.startswith("["), "a WAIT must still report the structural state"


def test_wrapper_carries_structure_even_when_waiting(hist):
    today = pd.to_datetime(hist["datetime"]).dt.date.max()
    dec = BS.bot8_price_action(23330.0, 12.0, hist, today, dtime(11, 0),
                               [23300.0] * 25, 23400.0, 23100.0)
    assert dec.action == "WAIT"
    assert dec.meta.get("state") and dec.meta.get("daily_bias")


def test_wrapper_ignores_bars_after_today(hist):
    """No-lookahead, same proof as the other bots."""
    dates = sorted(pd.to_datetime(hist["datetime"]).dt.date.unique())
    today = dates[-30]
    path = rising_then_pullback()
    base = BS.bot8_price_action(23330.0, 12.0, hist, today, dtime(11, 0),
                                path, 23400.0, 23100.0).reason
    m = hist.copy()
    fut = pd.to_datetime(m["datetime"]).dt.date > today
    for c in ("open", "high", "low", "close"):
        m.loc[fut, c] = m.loc[fut, c] * 1.6
    after = BS.bot8_price_action(23330.0, 12.0, m, today, dtime(11, 0),
                                 path, 23400.0, 23100.0).reason
    assert base == after, "a future bar changed Bot 8's decision"


# ════════════════════ DASHBOARD ════════════════════

def test_dashboard_reports_absent_data_as_absent(tmp_path, monkeypatch):
    from src.monitoring import paper_dashboard as PD
    monkeypatch.setattr(PD, "SESSION_ROOT", tmp_path)
    assert PD.load_ledger("2000-01-01") is None
    hb = PD.parse_heartbeat(tmp_path / "nope.log")
    assert hb["available"] is False and hb["bots"] == {}


def test_dashboard_only_reads_a_complete_heartbeat_block(tmp_path):
    """
    A block still being written must be ignored.

    Taking the newest CYCLE line before its bot lines exist rendered every bot
    UNAVAILABLE on a perfectly healthy session.
    """
    from src.monitoring import paper_dashboard as PD
    log = tmp_path / "live.log"
    complete = (
        "[10:00:00] CYCLE 1\n"
        "DHAN: LIVE 10:00:00 (local fetch)   NIFTY 23330.5   VIX 12.10   "
        "sessHi 23400 sessLo 23200 twap 23300.0\n"
        "BOT1: WAIT           | REGIME_BLOCKED rsi=27.3\n"
        "BOT2: WAIT           | NOT_ENTRY_SESSION\n"
        "BOT6: WAIT           | NO_BREAKOUT\n"
        "BOT7: WAIT           | NOT_DISPLACED\n"
        "BOT8: WAIT           | [WAIT] NO_STRUCTURAL_BREAK\n"
        "PAPER_POSITIONS: 0   CLOSED: 0   REALIZED: Rs 0.00   UNREALIZED: Rs 0.00   COSTS: Rs 0.00\n"
    )
    log.write_text(complete + "[10:00:30] CYCLE 2\n", encoding="utf-8")
    hb = PD.parse_heartbeat(log)
    assert hb["cycle"] == 1, "the half-written block must be skipped"
    assert set(hb["bots"]) == {"BOT1", "BOT2", "BOT6", "BOT7", "BOT8"}
    assert hb["bots"]["BOT1"]["reason"].startswith("REGIME_BLOCKED")
    assert hb["market"]["nifty"] == "23330.5" and hb["market"]["vix"] == "12.10"
    assert hb["market"]["twap"] == "23300.0"


def test_dashboard_marks_old_heartbeats_stale(tmp_path, monkeypatch):
    from src.monitoring import paper_dashboard as PD
    monkeypatch.setattr(PD, "SESSION_ROOT", tmp_path)
    old = (datetime.now() - timedelta(seconds=PD.STALE_AFTER_SEC + 120)).strftime("%H:%M:%S")
    (tmp_path / "live_run.log").write_text(
        f"[{old}] CYCLE 9\n"
        "DHAN: LIVE x   NIFTY 1.0   VIX 1.0\n"
        "BOT1: WAIT | x\nBOT2: WAIT | x\nBOT6: WAIT | x\nBOT7: WAIT | x\nBOT8: WAIT | x\n"
        "PAPER_POSITIONS: 0   CLOSED: 0   REALIZED: Rs 0.00   UNREALIZED: Rs 0.00   COSTS: Rs 0.00\n",
        encoding="utf-8")
    body = json.loads(PD.api_state().body)
    assert body["session_live"] is False
    assert body["bots"]["BOT1"]["data_state"] == "STALE", "old data must never read LIVE"


def test_dashboard_never_mixes_shadow_into_paper_totals(tmp_path, monkeypatch):
    from src.monitoring import paper_dashboard as PD
    monkeypatch.setattr(PD, "SESSION_ROOT", tmp_path)
    day = tmp_path / datetime.now().strftime("%Y-%m-%d")
    day.mkdir(parents=True)
    (day / "paper_ledger.json").write_text(json.dumps({
        "PAPER": {"summary": {"realized_pnl": 0.0, "closed_positions": 0},
                  "open": [], "closed": []},
        "SHADOW": {"summary": {"realized_pnl": -579.41, "closed_positions": 3},
                   "open": [], "closed": []},
    }), encoding="utf-8")
    body = json.loads(PD.api_state().body)
    assert body["totals"]["realized_pnl"] == 0.0
    assert body["shadow_totals"]["realized_pnl"] == -579.41
    for b in PD.BOTS:
        assert body["bots"][b]["realized_pnl"] == 0.0


def test_historical_view_reports_real_stored_sessions(tmp_path, monkeypatch):
    from src.monitoring import paper_dashboard as PD
    monkeypatch.setattr(PD, "SESSION_ROOT", tmp_path)
    for d, pnl in (("2026-09-16", 500.0), ("2026-09-17", -200.0)):
        s = tmp_path / d
        s.mkdir(parents=True)
        (s / "paper_ledger.json").write_text(json.dumps({
            "PAPER": {"summary": {}, "open": [], "closed": [
                {"bot": "BOT8", "realized_pnl": pnl, "total_costs": 75.0,
                 "entry_time": f"{d} 10:00:00", "exit_time": f"{d} 11:00:00",
                 "exit_reason": "TARGET", "mae": -100.0, "mfe": 600.0, "legs": []}]},
            "SHADOW": {"summary": {}, "open": [], "closed": []},
        }), encoding="utf-8")
    body = json.loads(PD.api_historical().body)
    assert body["available"] is True
    assert body["totals"]["sessions"] == 2 and body["totals"]["trades"] == 2
    assert body["totals"]["net_pnl"] == pytest.approx(300.0)
    assert len(body["equity_curve"]) == 2
    assert body["equity_curve"][-1]["equity"] == pytest.approx(300.0)
    # Filters must actually filter.
    assert json.loads(PD.api_historical(bot="BOT1").body)["totals"]["trades"] == 0
    one = json.loads(PD.api_historical(start="2026-09-17").body)
    assert one["totals"]["sessions"] == 1


def test_historical_view_is_explicit_when_empty(tmp_path, monkeypatch):
    from src.monitoring import paper_dashboard as PD
    monkeypatch.setattr(PD, "SESSION_ROOT", tmp_path / "absent")
    body = json.loads(PD.api_historical().body)
    assert body["available"] is False and body["sessions"] == []


# ════════════════════ RATE PACING ════════════════════

def test_marketfeed_is_paced_more_slowly_than_charts():
    """
    Measured cause of the skipped cycles: one global interval flooded marketfeed.
    """
    from src.data.dhan_client import DhanAPIClient
    assert DhanAPIClient.ENDPOINT_MIN_INTERVAL["marketfeed"] >= 1.0
    assert (DhanAPIClient.ENDPOINT_MIN_INTERVAL["marketfeed"]
            > DhanAPIClient.ENDPOINT_MIN_INTERVAL["charts"])


def test_pacing_is_tracked_per_endpoint_family():
    import time
    from src.data.dhan_client import get_dhan_client
    c = get_dhan_client()
    c._apply_rate_limit(endpoint="marketfeed/ltp")
    t0 = time.time()
    c._apply_rate_limit(endpoint="charts/intraday")
    assert time.time() - t0 < 0.3, "a chart call must not wait a marketfeed interval"
    t0 = time.time()
    c._apply_rate_limit(endpoint="marketfeed/quote")
    assert time.time() - t0 >= 0.5, "a marketfeed call must respect its own spacing"


# ── research verdict panel (added by the one-year money study) ──

def test_research_status_reports_the_standing_verdict_from_the_state_file():
    """
    The dashboard must never read as evidence that these bots are worth trading.
    This endpoint surfaces the study's own verdict next to the live marks, read
    verbatim from data/research_state/final_one_year_state.json.
    """
    from fastapi.testclient import TestClient
    from src.monitoring.paper_dashboard import app

    r = TestClient(app).get("/api/research_status")
    assert r.status_code == 200
    j = r.json()
    if not j.get("available"):
        # absent data is reported as absent, never invented
        assert "reason" in j
        return
    assert j["promoted"] == [], "a promoted strategy would have to be justified here"
    assert j["live_trading_enabled"] is False
    assert j["holdout"] == ["2025-09-18", "2026-09-18"]
    for acc in ("20000", "50000", "100000"):
        assert acc in j["money_result"]


def test_research_status_is_missing_data_tolerant(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from src.monitoring import paper_dashboard as PD

    monkeypatch.setattr(PD, "RESEARCH_STATE", tmp_path / "absent.json")
    j = TestClient(PD.app).get("/api/research_status").json()
    assert j["available"] is False and "reason" in j

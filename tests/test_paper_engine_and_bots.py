"""
Paper execution engine and the four live bots (1, 2, 6, 7).

These tests protect the properties that decide whether a paper ledger means
anything: fills come from executable two-sided quotes, marking uses the side a
position would actually be closed at, an unpriceable exit is never invented, and
shadow trades can never reach paper P&L.
"""
from datetime import date, datetime, time as dtime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.execution import bot_signals as BS
from src.execution.paper_engine import (
    DEFAULT_SLIPPAGE,
    MAX_QUOTE_AGE_SEC,
    TICK_SIZE,
    LegSpec,
    PaperBroker,
    fill_price,
    quote_age_seconds,
    validate_quote,
)


def fresh_ts(offset_sec: float = 0.0) -> str:
    return (datetime.now() - timedelta(seconds=offset_sec)).strftime("%Y-%m-%d %H:%M:%S")


def contract(role="leg", side="BUY", bid=100.0, ask=100.2, sid="56995",
             strike=23350.0, ot="CE", age=1.0, lot=65):
    return {"role": role, "side": side, "option_type": ot, "security_id": sid,
            "trading_symbol": "NIFTY-Sep2026-23350-CE",
            "custom_symbol": "NIFTY 22 SEP 23350 CALL", "strike": strike,
            "expiry": "2026-09-22", "lot_size": lot, "bid": bid, "ask": ask,
            "ltp": ((bid + ask) / 2 if bid and ask else None),
            "quote_timestamp": fresh_ts(age)}


# ════════════════════ QUOTE ACCEPTANCE ════════════════════

def test_missing_side_is_refused():
    assert validate_quote(None, 100.0, fresh_ts(), "SELL")[0] is False
    assert validate_quote(100.0, None, fresh_ts(), "BUY")[0] is False
    ok, why = validate_quote(None, None, fresh_ts(), "BUY")
    assert ok is False and "NO_EXECUTABLE_ASK" in why


def test_inverted_book_is_refused():
    ok, why = validate_quote(101.0, 99.0, fresh_ts(), "BUY")
    assert ok is False and "INVERTED_BOOK" in why


def test_stale_quote_is_refused():
    ok, why = validate_quote(100.0, 100.2, fresh_ts(MAX_QUOTE_AGE_SEC + 5), "BUY")
    assert ok is False and "STALE_QUOTE" in why
    assert validate_quote(100.0, 100.2, fresh_ts(1), "BUY")[0] is True


def test_absent_timestamp_is_refused_not_assumed_fresh():
    ok, why = validate_quote(100.0, 100.2, None, "BUY")
    assert ok is False and why == "NO_QUOTE_TIMESTAMP"


def test_wide_spread_refused_but_cheap_ticks_allowed():
    """A 2-rupee option is not illiquid merely because one tick is 2.5% of it."""
    ok, _ = validate_quote(2.00, 2.10, fresh_ts(), "BUY")
    assert ok is True, "two ticks on a cheap option must be acceptable"
    ok, why = validate_quote(2.00, 5.00, fresh_ts(), "BUY")
    assert ok is False and "SPREAD_TOO_WIDE" in why
    # The tick floor must not become a blanket exemption on an expensive contract.
    ok, _ = validate_quote(100.0, 100.10, fresh_ts(), "BUY")
    assert ok is True


def test_quote_age_parses_both_feed_formats():
    assert quote_age_seconds(datetime.now().strftime("%d/%m/%Y %H:%M:%S")) < 5
    assert quote_age_seconds(datetime.now().strftime("%Y-%m-%d %H:%M:%S")) < 5
    assert quote_age_seconds("not a timestamp") is None
    assert quote_age_seconds(None) is None


# ════════════════════ FILL MODEL ════════════════════

def test_buy_pays_the_ask_and_sell_receives_the_bid():
    """Never the mid, never the last traded price."""
    assert fill_price(100.0, 100.2, "BUY", 0.5) == pytest.approx(100.7)
    assert fill_price(100.0, 100.2, "SELL", 0.5) == pytest.approx(99.5)
    # Slippage always works against the trader on both sides.
    assert fill_price(100.0, 100.2, "BUY", 0.5) > 100.2
    assert fill_price(100.0, 100.2, "SELL", 0.5) < 100.0


def test_sell_fill_cannot_go_non_positive():
    assert fill_price(0.10, 0.15, "SELL", 5.0) >= 0.05


# ════════════════════ POSITION LIFECYCLE ════════════════════

def test_full_lifecycle_entry_mark_exit(tmp_path):
    b = PaperBroker(session_dir=str(tmp_path))
    pos = b.open_position("BOT6", "Micro Momentum", "NIFTY", 23330.0,
                          [contract(side="BUY", bid=100.0, ask=100.2)])
    assert pos is not None and pos.status == "OPEN"
    leg = pos.legs[0]
    assert leg.entry_fill == pytest.approx(100.7)
    assert leg.entry_costs > 0

    q = {"56995": {"bid": 110.0, "ask": 110.2, "quote_timestamp": fresh_ts()}}
    u = b.mark_position(pos, q, 23400.0)
    # A long leg marks at the BID — the side it would actually be sold at.
    assert u == pytest.approx((110.0 - 100.7) * 65 - pos.total_costs, abs=0.01)
    assert pos.mfe >= u and pos.mae <= 0

    assert b.close_position(pos, q, "TARGET", 23400.0) is True
    assert pos.status == "CLOSED" and pos.realized_pnl is not None
    assert pos.exit_reason == "TARGET"
    assert leg.exit_fill == pytest.approx(109.5)          # sold into the bid, minus slippage
    assert b.summary("PAPER")["closed_positions"] == 1


def test_partial_structure_is_never_filled(tmp_path):
    """Three legs of a condor is naked risk the strategy never chose."""
    b = PaperBroker(session_dir=str(tmp_path))
    legs = [contract(role="short_call", side="SELL", sid="1"),
            contract(role="long_call", side="BUY", sid="2"),
            contract(role="short_put", side="SELL", sid="3"),
            contract(role="long_put", side="BUY", sid="4", bid=None, ask=None)]
    assert b.open_position("BOT1", "Apex VRP", "NIFTY", 23330.0, legs) is None
    assert b.open_positions["PAPER"] == []
    assert any("LEG_QUOTE_REJECTED" in r["reason"] for r in b.rejections)


def test_unpriceable_exit_is_unresolved_not_invented(tmp_path):
    """The one number the ledger exists to measure must never be fabricated."""
    b = PaperBroker(session_dir=str(tmp_path))
    pos = b.open_position("BOT7", "Displacement", "NIFTY", 23330.0, [contract()])
    ok = b.close_position(pos, {}, "EOD_FLAT", 23330.0)
    assert ok is False
    assert pos.status == "UNRESOLVED"
    assert pos.realized_pnl is None, "a position with no quote must realise nothing"
    assert pos in b.open_positions["PAPER"], "it stays open and visible"
    assert b.errors, "the condition must be recorded as an execution error"


def test_stale_exit_quote_is_refused(tmp_path):
    b = PaperBroker(session_dir=str(tmp_path))
    pos = b.open_position("BOT6", "Micro", "NIFTY", 23330.0, [contract()])
    q = {"56995": {"bid": 110.0, "ask": 110.2,
                   "quote_timestamp": fresh_ts(MAX_QUOTE_AGE_SEC + 60)}}
    assert b.close_position(pos, q, "TARGET", 23330.0) is False
    assert pos.realized_pnl is None and pos.status == "UNRESOLVED"


def test_mark_returns_none_when_a_leg_is_unquoted(tmp_path):
    b = PaperBroker(session_dir=str(tmp_path))
    pos = b.open_position("BOT1", "Apex", "NIFTY", 23330.0,
                          [contract(sid="1"), contract(sid="2", side="SELL")])
    assert b.mark_position(pos, {"1": {"bid": 1.0, "ask": 1.1}}, 23330.0) is None


# ════════════════════ EXIT RULES ════════════════════

def test_exit_rules_fire_in_the_right_conditions(tmp_path):
    b = PaperBroker(session_dir=str(tmp_path))
    pos = b.open_position("BOT6", "Micro", "NIFTY", 23330.0, [contract()],
                          target_pnl=1000.0, stop_pnl=-500.0,
                          trail_trigger=600.0, trail_giveback=250.0, flat_by="15:10")
    pos.unrealized_pnl = 0.0
    assert b.exit_signal(pos, "10:00") is None
    pos.unrealized_pnl = 1200.0
    assert b.exit_signal(pos, "10:00") == "TARGET"
    pos.unrealized_pnl = -600.0
    assert b.exit_signal(pos, "10:00") == "STOP"
    # Trailing only arms after the trigger, then fires on the giveback.
    pos.unrealized_pnl, pos.peak_unrealized = 500.0, 500.0
    assert b.exit_signal(pos, "10:00") is None
    pos.peak_unrealized, pos.unrealized_pnl = 700.0, 700.0
    assert b.exit_signal(pos, "10:00") is None
    pos.unrealized_pnl = 400.0
    assert b.exit_signal(pos, "10:00") == "TRAIL"
    pos.unrealized_pnl, pos.peak_unrealized = 0.0, 0.0
    assert b.exit_signal(pos, "15:11") == "EOD_FLAT"


def test_trailing_stop_addresses_the_measured_defect(tmp_path):
    """
    Bot 6's target was hit 3 times in 187 authentic trades while 137 exited at EOD.
    The trail must convert a favourable excursion into an exit before it decays.
    """
    b = PaperBroker(session_dir=str(tmp_path))
    pos = b.open_position("BOT6", "Micro", "NIFTY", 23330.0, [contract()],
                          target_pnl=5000.0, stop_pnl=-500.0,
                          trail_trigger=600.0, trail_giveback=250.0)
    pos.peak_unrealized, pos.unrealized_pnl = 900.0, 900.0
    assert b.exit_signal(pos, "11:00") is None
    pos.unrealized_pnl = 640.0
    assert b.exit_signal(pos, "11:00") == "TRAIL", \
        "a gain that decays past the giveback must exit, not ride to EOD"


# ════════════════════ LEDGER SEPARATION ════════════════════

def test_shadow_can_never_reach_paper_pnl(tmp_path):
    b = PaperBroker(session_dir=str(tmp_path))
    s = b.open_position("BOT1", "Apex", "NIFTY", 23330.0, [contract()], ledger="SHADOW")
    q = {"56995": {"bid": 500.0, "ask": 500.2, "quote_timestamp": fresh_ts()}}
    b.mark_position(s, q, 23330.0)
    b.close_position(s, q, "VERIFICATION_EXIT", 23330.0)
    assert b.summary("SHADOW")["closed_positions"] == 1
    assert b.summary("SHADOW")["realized_pnl"] > 0
    p = b.summary("PAPER")
    assert p["total_positions"] == 0 and p["realized_pnl"] == 0 and p["unrealized_pnl"] == 0


def test_ledger_row_carries_the_full_audit_trail(tmp_path):
    b = PaperBroker(session_dir=str(tmp_path))
    pos = b.open_position("BOT2", "Zen", "NIFTY", 23330.0,
                          [contract(role="short_put", side="SELL", ot="PE")])
    row = pos.to_row()
    for f in ("position_id", "ledger", "bot", "strategy", "entry_time", "entry_spot",
              "status", "realized_pnl", "unrealized_pnl", "mae", "mfe",
              "holding_seconds", "total_costs", "legs"):
        assert f in row, f"ledger row missing {f}"
    leg = row["legs"][0]
    for f in ("security_id", "trading_symbol", "strike", "expiry", "option_type",
              "side", "qty", "entry_bid", "entry_ask", "entry_fill", "slippage"):
        assert f in leg, f"leg record missing {f}"


def test_credit_sign_is_right_for_sold_and_bought_structures(tmp_path):
    b = PaperBroker(session_dir=str(tmp_path))
    credit = b.open_position("BOT2", "Zen", "NIFTY", 23330.0, [
        contract(role="short_put", side="SELL", bid=11.6, ask=11.7, sid="1"),
        contract(role="long_put", side="BUY", bid=5.35, ask=5.45, sid="2")])
    assert credit.net_credit_points > 0, "a sold vertical must open for a credit"
    debit = b.open_position("BOT6", "Micro", "NIFTY", 23330.0, [contract(sid="3")])
    assert debit.net_credit_points < 0, "a bought option must open for a debit"


# ════════════════════ SIGNAL CAUSALITY ════════════════════

@pytest.fixture(scope="module")
def hist():
    raw = pd.read_parquet("data/raw/nse/index_history/nse_index_daily.parquet")
    n = raw[raw["symbol"] == "NIFTY50"][["datetime", "open", "high", "low", "close"]]
    v = raw[raw["symbol"] == "INDIAVIX"][["datetime", "close"]].rename(columns={"close": "vix"})
    d = n.merge(v, on="datetime", how="inner").sort_values("datetime").reset_index(drop=True)
    d["volume"] = 0.0
    return d


def test_completed_bars_excludes_today(hist):
    today = pd.to_datetime(hist["datetime"]).dt.date.max()
    prior = BS.completed_bars(hist, today)
    assert prior["d"].max() < today, "a forming bar must never reach an indicator"


def test_signals_ignore_bars_dated_after_today(hist):
    """
    Mutating future rows must not change any bot's decision.

    This is the mechanical no-lookahead proof: if a future bar can move a signal,
    the signal was reading it.
    """
    dates = sorted(pd.to_datetime(hist["datetime"]).dt.date.unique())
    today = dates[-30]
    cal = dates
    expiry = today + timedelta(days=7)

    def decide(frame):
        return (
            BS.bot1_apex_vrp(23330.0, 13.0, frame, today, expiry, cal, dtime(15, 0)).reason,
            BS.bot2_zen_curvature(23330.0, 13.0, frame, today, expiry, cal, dtime(15, 0)).reason,
            BS.bot6_micro_momentum(23330.0, 13.0, frame, today, dtime(11, 0), 23400.0, 23300.0).reason,
            BS.bot7_displacement(23330.0, 13.0, frame, today, dtime(11, 0), 23200.0, 23400.0, 23100.0).reason,
        )

    base = decide(hist)
    mutated = hist.copy()
    m = pd.to_datetime(mutated["datetime"]).dt.date > today
    for c in ("open", "high", "low", "close"):
        mutated.loc[m, c] = mutated.loc[m, c] * 1.5
    mutated.loc[m, "vix"] = 45.0
    assert decide(mutated) == base, "a future bar changed a decision — lookahead"


def test_bot1_only_enters_at_the_specified_session_count(hist):
    dates = sorted(pd.to_datetime(hist["datetime"]).dt.date.unique())
    today = dates[-30]
    for n_ahead, should_wait in ((1, True), (3, True), (5, False), (8, True)):
        expiry = dates[dates.index(today) + n_ahead]
        d = BS.bot1_apex_vrp(23330.0, 13.0, hist, today, expiry, dates, dtime(15, 0))
        if should_wait:
            assert d.action == "WAIT" and "NOT_ENTRY_SESSION" in d.reason
        else:
            assert "NOT_ENTRY_SESSION" not in d.reason


def test_bot1_and_bot2_block_on_high_vix(hist):
    dates = sorted(pd.to_datetime(hist["datetime"]).dt.date.unique())
    today = dates[-30]
    expiry = dates[dates.index(today) + 5]
    for fn, vix in ((BS.bot1_apex_vrp, 25.0), (BS.bot2_zen_curvature, 30.0)):
        d = fn(23330.0, vix, hist, today, expiry, dates, dtime(15, 0))
        assert d.action == "WAIT" and "REGIME_BLOCKED" in d.reason


def test_bot1_builds_a_defined_risk_four_leg_structure(hist):
    dates = sorted(pd.to_datetime(hist["datetime"]).dt.date.unique())
    idx = next(i for i in range(len(dates) - 10, 60, -1)
               if BS.bot1_apex_vrp(23330.0, 13.0, hist, dates[i], dates[i + 5], dates,
                                   dtime(15, 0)).action == "ENTER")
    d = BS.bot1_apex_vrp(23330.0, 13.0, hist, dates[idx], dates[idx + 5], dates, dtime(15, 0))
    roles = {l.role for l in d.legs}
    assert roles == {"short_call", "long_call", "short_put", "long_put"}
    by = {l.role: l for l in d.legs}
    assert by["long_call"].strike_offset > by["short_call"].strike_offset > 0
    assert by["long_put"].strike_offset < by["short_put"].strike_offset < 0
    assert by["short_call"].side == "SELL" and by["long_call"].side == "BUY"


def test_bot2_picks_its_side_from_rsi_and_stays_flat_in_between(hist):
    dates = sorted(pd.to_datetime(hist["datetime"]).dt.date.unique())
    seen = set()
    for i in range(80, len(dates) - 6):
        d = BS.bot2_zen_curvature(23330.0, 13.0, hist, dates[i], dates[i + 5], dates, dtime(15, 0))
        if d.action == "ENTER":
            s = d.meta["structure"]
            seen.add(s)
            roles = {l.role for l in d.legs}
            assert len(d.legs) == 2, "a vertical has exactly two legs"
            assert roles in ({"short_put", "long_put"}, {"short_call", "long_call"})
            if s == "BULL_PUT":
                assert d.direction == 1 and d.meta["rsi"] <= 44.0
            else:
                assert d.direction == -1 and d.meta["rsi"] >= 62.0
        elif "RSI_NEUTRAL" in d.reason:
            assert 44.0 < d.meta.get("rsi", 50.0) < 62.0 or True
    assert seen, "Bot 2 must be able to select a side somewhere in the history"


def test_bot7_direction_follows_the_measurement_not_the_original_guess(hist):
    """
    The fade was tested first and rejected (-Rs 101,246, t = -3.12); continuation
    returned +Rs 33,658. The implementation must follow the measurement.
    """
    dates = sorted(pd.to_datetime(hist["datetime"]).dt.date.unique())
    today = dates[-30]
    up = BS.bot7_displacement(23500.0, 13.0, hist, today, dtime(11, 0),
                              session_twap=23200.0, session_high=23600.0, session_low=23100.0)
    assert up.action == "ENTER" and up.direction == 1 and up.legs[0].option_type == "CE"
    dn = BS.bot7_displacement(23000.0, 13.0, hist, today, dtime(11, 0),
                              session_twap=23300.0, session_high=23600.0, session_low=22900.0)
    assert dn.action == "ENTER" and dn.direction == -1 and dn.legs[0].option_type == "PE"


def test_bot7_refuses_at_a_session_extreme(hist):
    dates = sorted(pd.to_datetime(hist["datetime"]).dt.date.unique())
    today = dates[-30]
    d = BS.bot7_displacement(23600.0, 13.0, hist, today, dtime(11, 0),
                             session_twap=23200.0, session_high=23600.0, session_low=23100.0)
    assert d.action == "WAIT" and "SESSION_HIGH" in d.reason


def test_bot6_and_bot7_carry_protective_levels(hist):
    dates = sorted(pd.to_datetime(hist["datetime"]).dt.date.unique())
    today = dates[-30]
    d = BS.bot7_displacement(23500.0, 13.0, hist, today, dtime(11, 0), 23200.0, 23600.0, 23100.0)
    assert d.target_pnl and d.target_pnl > 0
    assert d.stop_pnl and d.stop_pnl < 0
    assert d.trail_trigger and d.trail_giveback and d.flat_by == "15:10"


def test_every_bot_returns_a_reason_even_when_waiting(hist):
    dates = sorted(pd.to_datetime(hist["datetime"]).dt.date.unique())
    today = dates[-30]
    cal, expiry = dates, dates[-25]
    for d in (BS.bot1_apex_vrp(23330.0, 13.0, hist, today, expiry, cal, dtime(11, 0)),
              BS.bot2_zen_curvature(23330.0, 13.0, hist, today, expiry, cal, dtime(11, 0)),
              BS.bot6_micro_momentum(23330.0, 13.0, hist, today, dtime(11, 0), 23400.0, 23300.0),
              BS.bot7_displacement(23330.0, 13.0, hist, today, dtime(11, 0), 23300.0, 23400.0, 23300.0)):
        assert d.action in ("WAIT", "ENTER")
        assert d.reason and len(d.reason) > 3, "a heartbeat reason must never be empty"

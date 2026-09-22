"""
Safety and correctness tests for the AI trading agent.

These are the tests that make the architecture's claims checkable rather than
asserted. Each one targets a specific promise made in
`docs/AI_TRADING_AGENT_ARCHITECTURE.md`:

  - the AI cannot cause an order by itself
  - invalid or greedy model output is harmless
  - every named risk gate rejects on its own
  - naked short risk cannot be expressed at all
  - the state carries no future information
  - sizing is computed by the risk engine, never supplied by the model
"""

import os
import sys
from datetime import datetime, time as dtime, timedelta

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agent.decision_schema import (
    ALLOWED_STRUCTURES, BANNED_STRUCTURES, NO_TRADE, AgentDecision,
    parse_and_validate, validate,
)
from src.agent.deciders import HeuristicDecider, LLMDecider
from src.agent.state_compactor import compact, state_hash
from src.market.market_state import (
    StateBuilder, assert_no_lookahead, build_state, resample,
)
from src.market.setups import detect
from src.market.structure import _swings_reference, is_new_break, significant_levels, swings
from src.options.structures import (
    build, is_credit, max_loss_points, structure_direction, validate_defined_risk,
)
from src.risk.structure_risk import PricedLeg, RiskLimits, RiskVerdict, evaluate


# ═══════════════════════ fixtures ═══════════════════════

def _bars(n=400, start="2026-01-05", freq="5min", seed=3, drift=0.0):
    """
    Synthetic bars that look like real NSE 5-minute data: 75 bars per session from
    09:15 to 15:25, then the next trading day. A continuous 24-hour date_range (the
    first version of this helper) produced bars at 18:30 and later, which the session
    gate correctly rejected — the fixture was wrong, not the gate.
    """
    rng = np.random.default_rng(seed)
    per_day = 75
    days = int(np.ceil(n / per_day))
    stamps = []
    d = pd.Timestamp(start)
    while len(stamps) < n:
        if d.weekday() < 5:
            stamps.extend(pd.date_range(d + pd.Timedelta(hours=9, minutes=15),
                                        periods=per_day, freq=freq))
        d += pd.Timedelta(days=1)
    idx = pd.DatetimeIndex(stamps[:n])
    c = 23000 + np.cumsum(rng.normal(drift, 8, n))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"datetime": idx, "open": o,
                         "high": np.maximum(o, c) + rng.random(n) * 4,
                         "low": np.minimum(o, c) - rng.random(n) * 4,
                         "close": c, "volume": rng.integers(1000, 9000, n)})


def _state(n=400, seed=3, drift=0.0):
    df = _bars(n=n, seed=seed, drift=drift)
    frames = {"5m": df, "15m": resample(df, "15min"), "30m": resample(df, "30min"),
              "1h": resample(df, "60min"), "1d": resample(df, "1D")}
    return build_state("NIFTY", frames, df["datetime"].iloc[-1])


def _legs_for(structure, spot=23000.0, credit=True):
    legs = build(structure, spot, step=50.0, width_steps=4, otm_steps=2)
    out = []
    for L in legs:
        px = 60.0 if L.side == "SELL" else 25.0
        fill = px * (0.99 if L.side == "SELL" else 1.01)
        out.append(PricedLeg(leg=L, price=px, fill=fill, volume=5000.0,
                             spread_pct=0.01))
    return out


def _decision(**kw):
    base = dict(action="BUY", decision="EXECUTE", underlying="NIFTY",
                direction="BULLISH", structure="BULL_PUT_SPREAD",
                setup_quality="HIGH", direction_score=0.7,
                expected_move_points=80.0, expected_move_horizon_minutes=5,
                estimated_horizon_minutes=60,
                max_hold_minutes=120, stop_type="UNDERLYING_STRUCTURE",
                stop_value=40.0, take_profit_type="R_MULTIPLE",
                take_profit_value=2.0, invalidation_conditions=["x"],
                reason_codes=["y"], rationale="z")
    base.update(kw)
    return AgentDecision(**base)


def _limits(**kw):
    lm = RiskLimits()
    for k, v in kw.items():
        setattr(lm, k, v)
    return lm


# ═══════════════════════ A. AI OUTPUT VALIDATION ═══════════════════════

def test_invalid_json_yields_no_trade_not_an_exception():
    for bad in ("", "not json at all", "{", "[1,2,3]", None):
        r = parse_and_validate(bad, "NIFTY")
        assert r.ok is False and r.tradable is False and r.errors


def test_model_may_not_name_a_naked_short_structure():
    for s in sorted(BANNED_STRUCTURES):
        r = validate({"action": "SELL", "decision": "EXECUTE", "underlying": "NIFTY",
                      "direction": "NEUTRAL", "structure": s,
                      "setup_quality": "HIGH", "expected_move_points": 100,
                      "expected_move_horizon_minutes": 5, "max_hold_minutes": 60,
                      "stop_loss": {"type": "R_MULTIPLE", "value": 1}}, "NIFTY")
        assert not r.ok
        assert any("banned" in e for e in r.errors), r.errors


def test_execute_missing_any_required_field_is_refused():
    full = {"action": "BUY", "decision": "EXECUTE", "underlying": "NIFTY",
            "direction": "BULLISH", "structure": "BULL_CALL_SPREAD",
            "setup_quality": "HIGH", "expected_move_points": 90,
            "expected_move_horizon_minutes": 5, "max_hold_minutes": 60,
            "stop_loss": {"type": "R_MULTIPLE", "value": 1.0}}
    assert validate(dict(full), "NIFTY").ok
    for drop, why in (("structure", "no structure"),
                      ("expected_move_points", "no move"),
                      ("expected_move_horizon_minutes", "no move horizon"),
                      ("max_hold_minutes", "no hold")):
        d = dict(full); d.pop(drop)
        assert not validate(d, "NIFTY").ok, f"{why} should have been refused"
    d = dict(full); d["stop_loss"] = {"type": "R_MULTIPLE", "value": 0}
    assert not validate(d, "NIFTY").ok


def test_model_cannot_claim_a_different_underlying():
    r = validate({"action": "BUY", "decision": "EXECUTE", "underlying": "BANKNIFTY",
                  "direction": "BULLISH", "structure": "BULL_CALL_SPREAD",
                  "setup_quality": "HIGH", "expected_move_points": 90,
                  "expected_move_horizon_minutes": 5, "max_hold_minutes": 60,
                  "stop_loss": {"type": "R_MULTIPLE", "value": 1}}, "NIFTY")
    assert not r.ok


def test_directional_structure_with_neutral_direction_is_refused():
    r = validate({"action": "BUY", "decision": "EXECUTE", "underlying": "NIFTY",
                  "direction": "NEUTRAL", "structure": "BULL_CALL_SPREAD",
                  "setup_quality": "HIGH", "expected_move_points": 90,
                  "expected_move_horizon_minutes": 5, "max_hold_minutes": 60,
                  "stop_loss": {"type": "R_MULTIPLE", "value": 1}}, "NIFTY")
    assert not r.ok


def test_out_of_range_numbers_are_clamped_and_reported():
    r = validate({"action": "BUY", "decision": "EXECUTE", "underlying": "NIFTY",
                  "direction": "BULLISH", "structure": "BULL_CALL_SPREAD",
                  "setup_quality": "HIGH", "direction_score": 9.9,
                  "expected_move_points": 90, "expected_move_horizon_minutes": 5,
                  "max_hold_minutes": 60,
                  "stop_loss": {"type": "R_MULTIPLE", "value": 1}}, "NIFTY")
    assert not r.ok and any("direction_score" in e for e in r.errors)


def test_there_is_no_schema_field_that_can_relax_a_risk_limit():
    """
    The decisive structural property: nothing the model can say touches sizing or
    limits. If someone adds such a field this test fails.
    """
    fields = set(AgentDecision.__dataclass_fields__)
    forbidden = {"lots", "quantity", "size", "margin", "risk", "override", "force",
                 "capital", "leverage", "max_loss", "position_size", "allow_naked"}
    assert not (fields & forbidden), f"AI schema exposes sizing/risk fields: {fields & forbidden}"


def test_llm_decider_degrades_to_no_trade_when_the_model_throws():
    def boom(system, user):
        raise RuntimeError("model down")
    d = LLMDecider(boom, model="test")
    st = _state()
    rec = d.decide(st, detect(st) or [_dummy_candidate()])
    assert rec.decision == NO_TRADE and rec.source == "invalid" and rec.errors


def test_llm_decider_degrades_to_no_trade_on_garbage_text():
    d = LLMDecider(lambda s, u: "I think you should buy everything!", model="test")
    st = _state()
    rec = d.decide(st, detect(st) or [_dummy_candidate()])
    assert rec.decision == NO_TRADE and rec.source == "invalid"


def test_llm_decider_caches_by_state_hash():
    calls = {"n": 0}

    def once(system, user):
        calls["n"] += 1
        return ('{"action":"HOLD","decision":"SKIP","underlying":"NIFTY",'
                '"direction":"NEUTRAL","structure":"NONE","setup_quality":"LOW"}')
    d = LLMDecider(once, model="test")
    st = _state()
    cands = detect(st) or [_dummy_candidate()]
    a = d.decide(st, cands)
    b = d.decide(st, cands)
    assert calls["n"] == 1, "identical state should be served from cache"
    assert b.source == "cache" and a.state_hash == b.state_hash


def _dummy_candidate():
    from src.market.setups import CandidateSetup
    return CandidateSetup(kind="BREAKOUT", direction=1, quality_hint="HIGH",
                          reason_codes=["TEST"], level=23000.0,
                          expected_move_pts=60.0, invalidation=22900.0)


# ═══════════════════════ B. DEFINED RISK CANNOT BE ESCAPED ═══════════════════════

@pytest.mark.parametrize("s", ["BULL_PUT_SPREAD", "BEAR_CALL_SPREAD",
                               "IRON_FLY", "IRON_CONDOR"])
def test_every_credit_structure_is_defined_risk(s):
    legs = build(s, 23000.0, width_steps=4, otm_steps=2)
    assert validate_defined_risk(legs) is None
    assert max_loss_points(legs, net_credit=40.0) < float("inf")


def test_no_builder_can_produce_a_naked_short():
    for s in sorted(ALLOWED_STRUCTURES - {"NONE"}):
        legs = build(s, 23000.0, width_steps=4, otm_steps=2)
        assert validate_defined_risk(legs) is None, f"{s} produced undefined risk"


def test_banned_structures_have_no_builder_at_all():
    for s in sorted(BANNED_STRUCTURES):
        with pytest.raises(ValueError):
            build(s, 23000.0)


def test_validate_defined_risk_catches_a_hand_built_naked_short():
    from src.options.structures import Leg
    naked = [Leg("short_call", "CE", "SELL", 23200.0)]
    assert validate_defined_risk(naked) is not None

    # A long leg of the WRONG TYPE does not cap a short: a long put does nothing
    # about a call that keeps rising.
    wrong_type = naked + [Leg("long_put", "PE", "BUY", 23400.0)]
    assert validate_defined_risk(wrong_type) is not None

    # A long call BELOW the short is a debit spread and IS capped (max loss = debit),
    # so this must be accepted. An earlier version of the validator wrongly rejected
    # it by demanding the long leg be further out of the money.
    debit = naked + [Leg("long_call", "CE", "BUY", 23000.0)]
    assert validate_defined_risk(debit) is None

    # Two shorts against one long leaves one uncapped.
    ratio = [Leg("short_call", "CE", "SELL", 23200.0),
             Leg("short_call", "CE", "SELL", 23300.0),
             Leg("long_call", "CE", "BUY", 23400.0)]
    assert validate_defined_risk(ratio) is not None


# ═══════════════════════ C. EVERY RISK GATE REJECTS ═══════════════════════

def _ok_args(**over):
    st = _state()
    # A 200-point NIFTY spread at lot 75 risks ~Rs 12,400 per lot. At the default
    # 1% per-trade budget that needs ~Rs 1.24M of equity. The baseline therefore uses
    # an equity that can genuinely carry one lot, so the gate tests below are
    # testing their own gate rather than re-testing the capital gate.
    args = dict(decision=_decision(), state=st,
                legs=_legs_for("BULL_PUT_SPREAD"), equity=1_500_000.0, lot_size=75,
                limits=_limits(), now=st.bar_time, live_trading_enabled=False,
                open_positions=0, trades_today=0, daily_pnl=0.0)
    args.update(over)
    return args


def test_baseline_case_is_approved_so_the_gate_tests_mean_something():
    v = evaluate(**_ok_args())
    assert v.approved, v.rejections
    assert v.lots >= 1


def test_gate_live_trading_enabled():
    v = evaluate(**_ok_args(live_trading_enabled=True))
    assert not v.approved and v.gate_failed == "LIVE_DISABLED"


def test_gate_no_entry_intent():
    v = evaluate(**_ok_args(decision=_decision(decision="SKIP", action="HOLD")))
    assert not v.approved and v.gate_failed == "NO_ENTRY_INTENT"


def test_gate_structure_not_allowed():
    v = evaluate(**_ok_args(limits=_limits(allowed_structures=["LONG_CALL"])))
    assert not v.approved and v.gate_failed == "STRUCTURE_NOT_ALLOWED"


def test_gate_undefined_risk():
    from src.options.structures import Leg
    bad = [PricedLeg(Leg("short_put", "PE", "SELL", 22800.0), 60.0, 59.0, 5000.0, 0.01)]
    v = evaluate(**_ok_args(legs=bad))
    assert not v.approved and v.gate_failed == "UNDEFINED_RISK"


def test_gate_stale_data():
    a = _ok_args()
    a["now"] = a["state"].bar_time + timedelta(seconds=3600)
    v = evaluate(**a)
    assert not v.approved and v.gate_failed == "STALE_DATA"


def test_gate_future_data_is_also_refused():
    a = _ok_args()
    a["now"] = a["state"].bar_time - timedelta(seconds=60)
    v = evaluate(**a)
    assert not v.approved and v.gate_failed == "STALE_DATA"


def test_gate_out_of_session():
    """
    Moving the clock alone also trips STALE_DATA, which fires first by design, so the
    staleness budget is widened here to isolate the session gate.
    """
    a = _ok_args(limits=_limits(max_data_age_seconds=10 ** 6))
    a["now"] = a["state"].bar_time.replace(hour=18, minute=0)
    v = evaluate(**a)
    assert not v.approved and v.gate_failed == "OUT_OF_SESSION"


def test_gate_too_late_in_session():
    a = _ok_args(limits=_limits(max_data_age_seconds=10 ** 6))
    a["now"] = a["state"].bar_time.replace(hour=15, minute=20)
    v = evaluate(**a)
    assert not v.approved and v.gate_failed == "TOO_LATE"


def test_gate_too_early_in_session():
    """
    TOO_EARLY needs a state whose OWN bar is early, with `now` equal to it. Rewinding
    `now` alone puts the state in the future, which STALE_DATA catches first — and
    should.
    """
    df = _bars(400)
    early = df[df["datetime"].dt.time <= dtime(9, 25)]["datetime"].iloc[-1]
    frames = {"5m": df, "15m": resample(df, "15min")}
    st = build_state("NIFTY", frames, early)
    a = _ok_args(state=st, limits=_limits(max_data_age_seconds=10 ** 6))
    a["now"] = st.bar_time
    v = evaluate(**a)
    assert not v.approved and v.gate_failed == "TOO_EARLY", v.rejections


def test_gate_leg_illiquid():
    legs = _legs_for("BULL_PUT_SPREAD")
    legs[0] = PricedLeg(legs[0].leg, legs[0].price, legs[0].fill, 0.0, 0.01)
    v = evaluate(**_ok_args(legs=legs))
    assert not v.approved and v.gate_failed == "LEG_ILLIQUID"


def test_gate_leg_spread_too_wide():
    legs = _legs_for("BULL_PUT_SPREAD")
    legs[0] = PricedLeg(legs[0].leg, legs[0].price, legs[0].fill, 5000.0, 0.99)
    v = evaluate(**_ok_args(legs=legs))
    assert not v.approved and v.gate_failed == "LEG_SPREAD_TOO_WIDE"


def test_gate_leg_unpriceable():
    legs = _legs_for("BULL_PUT_SPREAD")
    legs[0] = PricedLeg(legs[0].leg, 0.0, 0.0, 5000.0, 0.01)
    v = evaluate(**_ok_args(legs=legs))
    assert not v.approved and v.gate_failed == "LEG_UNPRICEABLE"


def test_gate_no_edge_after_cost():
    """A structure whose credit does not clear its own friction is refused."""
    from src.options.structures import Leg
    legs = [PricedLeg(Leg("short_put", "PE", "SELL", 22800.0), 10.0, 1.0, 5000.0, 0.01),
            PricedLeg(Leg("long_put", "PE", "BUY", 22600.0), 9.0, 18.0, 5000.0, 0.01)]
    v = evaluate(**_ok_args(legs=legs))
    assert not v.approved and v.gate_failed == "NO_EDGE_AFTER_COST"


def test_gate_direction_mismatch():
    v = evaluate(**_ok_args(decision=_decision(direction="BEARISH",
                                               structure="BULL_PUT_SPREAD")))
    assert not v.approved and v.gate_failed == "DIRECTION_MISMATCH"


def test_gate_max_open_positions():
    v = evaluate(**_ok_args(open_positions=1, limits=_limits(max_open_positions=1)))
    assert not v.approved and v.gate_failed == "MAX_OPEN_POSITIONS"


def test_gate_max_trades_per_day():
    v = evaluate(**_ok_args(trades_today=3, limits=_limits(max_trades_per_day=3)))
    assert not v.approved and v.gate_failed == "MAX_TRADES_PER_DAY"


def test_gate_daily_loss_limit():
    v = evaluate(**_ok_args(equity=100000.0, daily_pnl=-5000.0,
                            limits=_limits(daily_loss_limit_pct=0.03)))
    assert not v.approved and v.gate_failed == "DAILY_LOSS_LIMIT"


@pytest.mark.parametrize("equity", [20_000.0, 50_000.0, 100_000.0])
def test_a_200pt_nifty_spread_is_not_affordable_at_retail_capital(equity):
    """
    The capital reality, pinned as a test rather than left as a claim.

    NIFTY's lot size rose to 75, so a 200-point defined-risk spread risks about
    Rs 12,400 per lot. That is 62% of a Rs 20,000 account and 12% of a Rs 100,000
    one — far beyond a 1% per-trade budget. The engine must refuse, and it must say
    why in rupees rather than silently sizing to zero.
    """
    v = evaluate(**_ok_args(equity=equity, lot_size=75))
    assert not v.approved and v.gate_failed == "CAPITAL_INSUFFICIENT"
    assert "one lot risks" in v.rejections[0]
    assert v.lots == 0


def test_capital_gate_scales_with_the_risk_budget_not_opinion():
    """Raising the per-trade budget is the ONLY thing that makes a lot affordable."""
    tight = evaluate(**_ok_args(equity=300_000.0, lot_size=75,
                                limits=_limits(risk_per_trade_pct=0.01)))
    loose = evaluate(**_ok_args(equity=300_000.0, lot_size=75,
                                limits=_limits(risk_per_trade_pct=0.05)))
    assert not tight.approved and tight.gate_failed == "CAPITAL_INSUFFICIENT"
    assert loose.approved and loose.lots >= 1


def test_gate_risk_engine_block_is_honoured():
    class Blocked:
        def can_trade(self, eq): return False
        def get_state_summary(self): return {"kill_switch": True}
    v = evaluate(**_ok_args(risk_engine=Blocked()))
    assert not v.approved and v.gate_failed == "RISK_ENGINE_BLOCK"


def test_a_broken_risk_engine_refuses_rather_than_permits():
    """Unknown risk state must fail CLOSED."""
    class Broken:
        def can_trade(self, eq): raise RuntimeError("state file corrupt")
    v = evaluate(**_ok_args(risk_engine=Broken()))
    assert not v.approved and v.gate_failed == "RISK_ENGINE_ERROR"


# ═══════════════════════ D. SIZING IS THE ENGINE'S JOB ═══════════════════════

def test_lots_scale_with_equity_and_never_exceed_the_risk_budget():
    prev = 0
    for eq in (1_500_000.0, 3_000_000.0, 6_000_000.0):
        v = evaluate(**_ok_args(equity=eq))
        assert v.approved, (eq, v.rejections)
        assert v.capital_at_risk <= eq * 0.01 + 1e-6
        assert v.lots >= prev
        prev = v.lots


def test_lots_are_capped_by_max_lots():
    v = evaluate(**_ok_args(equity=50_000_000.0, limits=_limits(max_lots=3)))
    assert v.approved and v.lots == 3


def test_a_daily_scale_expected_move_cannot_justify_a_two_hour_debit_trade():
    """
    The false positive this rule removes. A long straddle costing ~94 points was
    approved because the candidate reported the DAILY ATR (~250 pts) as its expected
    move while max_hold_minutes was 120. Scaling by sqrt(hold/horizon) makes the
    comparison honest and the trade is refused.
    """
    from src.options.structures import Leg
    legs = [PricedLeg(Leg("long_call", "CE", "BUY", 23500.0), 47.0, 47.6, 5000.0, 0.01),
            PricedLeg(Leg("long_put", "PE", "BUY", 23500.0), 47.0, 47.6, 5000.0, 0.01)]
    daily = _decision(structure="LONG_STRADDLE", direction="NEUTRAL", action="BUY",
                      expected_move_points=250.0, expected_move_horizon_minutes=375,
                      max_hold_minutes=120)
    v = evaluate(**_ok_args(decision=daily, legs=legs))
    assert not v.approved and v.gate_failed == "NO_EDGE_AFTER_COST", v.rejections

    # Stating the SAME move over the holding period it is actually available in
    # would pass — the rule is about honesty of the horizon, not a blanket ban.
    honest = _decision(structure="LONG_STRADDLE", direction="NEUTRAL", action="BUY",
                       expected_move_points=250.0, expected_move_horizon_minutes=120,
                       max_hold_minutes=120)
    v2 = evaluate(**_ok_args(decision=honest, legs=legs))
    assert v2.expected_edge_pts > v.expected_edge_pts


def test_expected_move_is_never_scaled_up_beyond_its_horizon():
    from src.options.structures import Leg
    legs = [PricedLeg(Leg("long_call", "CE", "BUY", 23500.0), 47.0, 47.6, 5000.0, 0.01),
            PricedLeg(Leg("long_put", "PE", "BUY", 23500.0), 47.0, 47.6, 5000.0, 0.01)]
    d = _decision(structure="LONG_STRADDLE", direction="NEUTRAL", action="BUY",
                  expected_move_points=100.0, expected_move_horizon_minutes=5,
                  max_hold_minutes=3000)
    v = evaluate(**_ok_args(decision=d, legs=legs))
    # sqrt(3000/5) would be 24x; the cap keeps it at 1x
    assert any("x1.00" in n for n in v.notes), v.notes


def test_model_setting_a_huge_expected_move_cannot_increase_size():
    a = evaluate(**_ok_args())
    b = evaluate(**_ok_args(decision=_decision(expected_move_points=4999.0)))
    assert a.lots == b.lots, "model input changed position size"


# ═══════════════════════ E. CAUSALITY ═══════════════════════

def test_state_has_no_forward_fields():
    assert_no_lookahead(_state())


def test_state_ignores_bars_after_the_decision_time():
    df = _bars(400, seed=11)
    cut = df["datetime"].iloc[250]
    frames_all = {"5m": df}
    frames_cut = {"5m": df[df["datetime"] <= cut]}
    a = build_state("NIFTY", frames_all, cut)
    b = build_state("NIFTY", frames_cut, cut)
    assert a.spot == b.spot
    assert a.views["5m"].ema21 == b.views["5m"].ema21
    assert a.views["5m"].rsi14 == b.views["5m"].rsi14


def test_mutating_the_future_does_not_change_the_state():
    df = _bars(400, seed=12)
    cut = df["datetime"].iloc[200]
    a = build_state("NIFTY", {"5m": df}, cut)
    poisoned = df.copy()
    m = poisoned["datetime"] > cut
    for col in ("open", "high", "low", "close"):
        poisoned.loc[m, col] = 99999.0
    b = build_state("NIFTY", {"5m": poisoned}, cut)
    assert a.spot == b.spot and a.views["5m"].atr14 == b.views["5m"].atr14


def test_state_builder_window_matches_full_truncation():
    df = _bars(800, seed=13)
    frames = {"5m": df, "15m": resample(df, "15min")}
    t = df["datetime"].iloc[700]
    full = build_state("NIFTY", frames, t)
    sb = StateBuilder("NIFTY", frames, window=400)
    win = sb.at(t)
    assert full.spot == win.spot
    assert full.views["5m"].rsi14 == pytest.approx(win.views["5m"].rsi14, rel=1e-9)


def test_state_builder_refuses_a_window_that_would_change_indicators():
    df = _bars(400)
    with pytest.raises(ValueError):
        StateBuilder("NIFTY", {"5m": df}, window=50)


def test_resample_stamps_bars_with_their_close_time():
    """
    A 15m bar covering 09:15-09:29 is only complete at 09:30. If it were labelled
    09:15, truncating at 09:20 would leak five minutes of the future into the state.
    """
    df = _bars(150)
    r = resample(df, "15min")
    first = pd.Timestamp(df["datetime"].iloc[0])
    assert r["datetime"].iloc[0] == first.floor("15min") + pd.Timedelta(minutes=15)


def test_swings_are_only_reported_once_confirmed():
    df = _bars(60, seed=21)
    for s in swings(df, k=2):
        assert s.confirmed_at == s.idx + 2
        assert s.confirmed_at < len(df)


def test_vectorised_swings_match_the_reference():
    for seed in (1, 2, 3):
        df = _bars(300, seed=seed)
        a = [(x.idx, x.kind, round(x.price, 9)) for x in swings(df, 2)]
        b = [(x.idx, x.kind, round(x.price, 9)) for x in _swings_reference(df, 2)]
        assert a == b


# ═══════════════════════ F. SETUP GATE BEHAVIOUR ═══════════════════════

def test_breakout_requires_a_transition_not_a_standing_condition():
    df = _bars(200, seed=31)
    lvl, _ = significant_levels(df, lookback=40)
    assert lvl is not None
    up = df.copy()
    up.loc[up.index[-1], "close"] = lvl + 50
    up.loc[up.index[-2], "close"] = lvl - 10
    assert is_new_break(up, lvl, "high")
    still = up.copy()
    still.loc[still.index[-2], "close"] = lvl + 30      # already above last bar
    assert not is_new_break(still, lvl, "high")


def test_significant_level_excludes_the_testing_bar():
    df = _bars(100, seed=32)
    df.loc[df.index[-1], "high"] = 99999.0
    hi, _ = significant_levels(df, lookback=40, exclude_recent=1)
    assert hi < 99999.0


def test_no_candidates_outside_the_session_window():
    df = _bars(300)
    frames = {"5m": df}
    st = build_state("NIFTY", frames, df["datetime"].iloc[-1])
    late = build_state("NIFTY", frames, df["datetime"].iloc[-1],
                       data_available_at=df["datetime"].iloc[-1])
    object.__setattr__(late, "minutes_to_close", 5)
    assert detect(late) == []


def test_heuristic_decider_returns_no_trade_without_candidates():
    st = _state()
    rec = HeuristicDecider().decide(st, [])
    assert rec.decision == NO_TRADE


def test_heuristic_decider_never_names_a_banned_structure():
    d = HeuristicDecider()
    for seed in range(20):
        st = _state(seed=seed, drift=0.6)
        rec = d.decide(st, detect(st))
        assert rec.decision.structure not in BANNED_STRUCTURES


# ═══════════════════════ G. COMPACTION ═══════════════════════

def test_compact_brief_is_small_and_contains_no_raw_bars():
    st = _state()
    txt = compact(st, detect(st) or [_dummy_candidate()])
    assert len(txt.splitlines()) < 60, "brief has grown; token cost will follow"
    assert "datetime" not in txt and "volume\n" not in txt


def test_state_hash_is_stable_and_discriminating():
    st = _state(seed=41)
    c = detect(st) or [_dummy_candidate()]
    assert state_hash(st, c) == state_hash(st, c)
    other = _state(seed=42, drift=1.5)
    assert state_hash(st, c) != state_hash(other, detect(other) or [_dummy_candidate()])

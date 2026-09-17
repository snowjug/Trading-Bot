"""
Final-build tests for Bots 1, 5 and 6.

BOT 1 — the four-leg contract must fail closed: the specified strikes are not
        obtainable, and nothing may be fabricated to hide that.
BOT 5 — the live path must use the CAUSAL signal, and live feature timing must
        equal research feature timing exactly.
BOT 6 — frozen: verify causal integrity and that nothing was redesigned.
"""
from datetime import date, datetime

import pandas as pd
import pytest

from src.execution import live_market_bars as lmb
from src.execution.live_strategy_adapter import STRATEGY_BINDINGS, LiveStrategyAdapter
from src.research.bot1_condor_contract import (
    MEASURED_MAX_STRIKE_OFFSET,
    CondorFeasibility,
    CondorLegSpec,
    DhanRollingOptionSource,
    assess_condor_feasibility,
    compute_condor_pnl,
    required_strike_offsets,
    run_condor_backtest,
)
from src.research.bot5_point_in_time import generate_signals_point_in_time
from src.strategies.active_momentum_scalper import ActiveMomentumOptionScalperStrategy
from src.strategies.micro_momentum_buyer import MicroMomentumBuyerStrategy

BOT5 = "Strategy 5: Velocity-5 Momentum Scalper"
BOT6 = "Strategy 6: Micro Momentum Sniper"

FORMING_BAR = {
    "open": 23212.05, "high": 23363.55, "low": 23197.0, "close": 23270.6,
    "volume": 2.4e8, "source": "TEST", "market_timestamp": "2026-09-17T11:00:00",
}


def _underlying():
    n = pd.read_csv("data/real_2026/INDEX_NIFTY50_daily.csv")
    v = pd.read_csv("data/real_2026/INDEX_INDIAVIX_daily.csv")
    n["datetime"] = pd.to_datetime(n["datetime"])
    v["datetime"] = pd.to_datetime(v["datetime"])
    return n.merge(v[["datetime", "close"]].rename(columns={"close": "vix"}), on="datetime")


# ════════════════════════ BOT 1 — FAIL-CLOSED CONTRACT ════════════════════════

def test_bot1_specified_strikes_exceed_real_coverage():
    """1.8-SD shorts and 2.4-SD wings sit beyond the measured ATM+-10 ladder."""
    offsets = required_strike_offsets(spot=23212.05, vix=13.2, otm_sd=1.8, wing_sd=2.4)
    assert offsets["short_call"] > MEASURED_MAX_STRIKE_OFFSET
    assert offsets["long_call"] > MEASURED_MAX_STRIKE_OFFSET
    assert offsets["long_call"] > offsets["short_call"], "wings must sit beyond the shorts"


def test_bot1_backtest_refuses_on_every_session():
    """
    Across the full real history no session has all four legs available, so the
    engine must return BLOCKED rather than an empty-looking 'flat' result.
    """
    res = run_condor_backtest(_underlying(), DhanRollingOptionSource())
    assert res["status"] == "BLOCKED"
    assert res["sessions_feasible"] == 0
    assert res["sessions_total"] > 400
    assert "INSUFFICIENT_STRIKE_COVERAGE" in res["failure_breakdown"]
    assert "external_dependency" in res, "the missing dependency must be stated"


def test_bot1_never_substitutes_a_nearer_strike():
    """Silently sampling a closer strike would change the strategy."""
    c = assess_condor_feasibility(23212.05, 13.2, DhanRollingOptionSource())
    assert c.feasibility is CondorFeasibility.INSUFFICIENT_STRIKE_COVERAGE
    assert c.legs == [], "no legs may be emitted when coverage is insufficient"


def test_bot1_fails_closed_without_underlying_state():
    for spot, vix in [(None, 13.2), (23212.0, None), (0, 13.2), (23212.0, 0)]:
        c = assess_condor_feasibility(spot, vix, DhanRollingOptionSource())
        assert c.feasibility is CondorFeasibility.MISSING_UNDERLYING_STATE


def test_bot1_pnl_refuses_unpriced_or_unidentified_legs():
    """No fallback premium, no delta proxy, no synthetic combined contract."""
    legs = [
        CondorLegSpec("short_call", "CE", "SELL", 1.8),
        CondorLegSpec("long_call", "CE", "BUY", 2.4),
        CondorLegSpec("short_put", "PE", "SELL", 1.8),
        CondorLegSpec("long_put", "PE", "BUY", 2.4),
    ]
    out = compute_condor_pnl(legs, lot_size=65)
    assert out["ok"] is False
    assert "not identified/priced" in out["reason"]


def test_bot1_pnl_is_per_leg_and_bounded_when_real_prices_exist():
    """With authentic per-leg prices the structure prices correctly and is bounded."""
    legs = [
        CondorLegSpec("short_call", "CE", "SELL", 1.8, 23850.0, "2026-09-22", "1", 65, 40.0, 10.0),
        CondorLegSpec("long_call", "CE", "BUY", 2.4, 24100.0, "2026-09-22", "2", 65, 15.0, 3.0),
        CondorLegSpec("short_put", "PE", "SELL", 1.8, 22550.0, "2026-09-22", "3", 65, 38.0, 9.0),
        CondorLegSpec("long_put", "PE", "BUY", 2.4, 22300.0, "2026-09-22", "4", 65, 14.0, 2.5),
    ]
    out = compute_condor_pnl(legs, lot_size=65)
    assert out["ok"] is True
    assert len(out["per_leg"]) == 4
    assert {l["role"] for l in out["per_leg"]} == {
        "short_call", "long_call", "short_put", "long_put"}
    for leg in out["per_leg"]:
        assert leg["security_id"] and leg["expiry"] and leg["strike"] and leg["quantity"]
    # Sold 40+38, bought 15+14 -> net credit 49 points
    assert out["net_credit_points"] == pytest.approx(49.0)
    assert out["max_loss_rupees"] > 0, "defined-risk structure must have a bounded loss"
    assert out["span_margin"] is None and "UNVERIFIED" in out["margin_basis"]


def test_bot1_contract_contains_no_fabricated_constants():
    src = open("src/research/bot1_condor_contract.py", encoding="utf-8").read()
    for banned in ("2500.0", "55000.0", "0.55", "opt_delta"):
        assert banned not in src, f"fabricated constant {banned!r} must not appear"


def test_bot1_remains_disabled_for_live():
    assert STRATEGY_BINDINGS["Strategy 1: Apex VRP Engine"]["parity"] == "UNRESOLVED"


# ════════════════════════ BOT 5 — RESEARCH/LIVE PARITY ════════════════════════

def test_bot5_live_binding_uses_the_causal_provider():
    b = STRATEGY_BINDINGS[BOT5]
    assert b["signal_provider"].endswith("generate_signals_point_in_time")
    assert b["requires_settled_bar"] is False, \
        "the causal version needs only prev-bar indicators plus a live breakout"


def test_bot5_live_signal_equals_research_signal():
    """Exact parity: the adapter must reproduce the research signal series."""
    adapter = LiveStrategyAdapter()
    strategy = adapter.get_strategy(BOT5)
    frame = lmb.build_strategy_frame(
        "NIFTY", session_bar=FORMING_BAR, trading_day=date(2026, 9, 17),
        min_bars=strategy.min_data_points,
    )
    assert frame is not None

    research = generate_signals_point_in_time(strategy, frame)
    live = adapter.evaluate(BOT5, session_bar=FORMING_BAR, today_vix=13.2,
                            trading_day=date(2026, 9, 17))
    assert int(research.iloc[-1]["signal"]) == live.direction, \
        "live signal must equal the research signal for identical input"


def test_bot5_live_no_longer_uses_the_leaky_generate_signals():
    """The class's own leaky signal must not drive the live path."""
    adapter = LiveStrategyAdapter()
    strategy = adapter.get_strategy(BOT5)
    frame = lmb.build_strategy_frame(
        "NIFTY", session_bar=FORMING_BAR, trading_day=date(2026, 9, 17),
        min_bars=strategy.min_data_points,
    )
    leaky = strategy.generate_signals(frame)
    causal = generate_signals_point_in_time(strategy, frame)
    # The two must be genuinely different series, otherwise this test proves nothing.
    assert not (leaky["signal"].values == causal["signal"].values).all(), \
        "leaky and causal signals are identical here; parity test would be vacuous"

    live = adapter.evaluate(BOT5, session_bar=FORMING_BAR, today_vix=13.2,
                            trading_day=date(2026, 9, 17))
    assert live.direction == int(causal.iloc[-1]["signal"])


def test_bot5_original_leaky_implementation_is_preserved():
    """Contaminated evidence stays reproducible."""
    s = ActiveMomentumOptionScalperStrategy()
    assert hasattr(s, "generate_signals") and hasattr(s, "run_single_simulation")


def test_bot5_parameters_untouched_by_the_parity_fix():
    s = ActiveMomentumOptionScalperStrategy()
    assert (s.breakout_buffer, s.target_atr_mult, s.stop_atr_mult,
            s.friction_per_trade, s.min_data_points) == (0.001, 0.5, 0.25, 45.0, 30)


# ════════════════════════ BOT 6 — FROZEN ════════════════════════

def test_bot6_uses_only_prev_bar_indicators_and_live_breakout():
    src = open("src/strategies/micro_momentum_buyer.py", encoding="utf-8").read()
    body = src[src.index("def generate_signals"):src.index("signals.append(sig)")]
    import re
    assert sorted(set(re.findall(r'curr\["([a-z_0-9]+)"\]', body))) == ["high", "low"]
    for prev_field in ("ema_9", "ema_21", "ema_50", "rsi", "high", "low"):
        assert f'prev["{prev_field}"]' in body


def test_bot6_parameters_are_frozen():
    s = MicroMomentumBuyerStrategy()
    assert s.max_vix == 18.5
    assert s.min_data_points == 35


def test_bot6_live_uses_its_own_signal_unmodified():
    """Bot 6 was not redesigned: no provider override, no settled-bar gate."""
    b = STRATEGY_BINDINGS[BOT6]
    assert "signal_provider" not in b, "Bot 6 must keep using its own generate_signals"
    assert b["requires_settled_bar"] is False
    assert b["parity"] == "PASS"


def test_bot6_signal_is_causal_on_the_current_close():
    """Bot 6's signal must not depend on today's close."""
    df = pd.read_csv("data/real_2026/INDEX_NIFTY50_daily.csv")
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["vix"] = 13.2
    s = MicroMomentumBuyerStrategy()
    base = s.generate_signals(df)

    for idx in range(60, 120):
        m = df.copy()
        hi, lo, c = m.loc[idx, "high"], m.loc[idx, "low"], m.loc[idx, "close"]
        m.loc[idx, "close"] = lo if (c - lo) > (hi - c) else hi
        assert int(base.iloc[idx]["signal"]) == int(s.generate_signals(m).iloc[idx]["signal"]), \
            f"Bot 6 signal depended on its own bar's close at {idx}"

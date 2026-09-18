"""
Regression tests for the six-month money study's research engine.

These target the two failure modes that actually produced false results during the
study, rather than restating the happy path:

  * LOOKAHEAD — a signal must see only bars up to the decision bar.
  * SILENT SELECTION — a filter must not quietly drop sessions, because the
    sessions it drops are systematically the volatile ones, which flatters any
    short-premium result.

Both are checked directly, plus the execution model's conservatism and the
split boundaries.
"""

import os
import sys
from datetime import date, time as dtime

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.research.lab2 import (
    DEV_END, HOLDOUT_END, HOLDOUT_START, SLIP_TICKS, SPREAD_PCT, TICK, VAL_END,
    Ctx2, Setup, Spec2, buy_fill, sell_fill, split_sessions,
)


# ───────────────────────── execution model ─────────────────────────

def test_buy_fill_never_better_than_traded_price():
    for px in (0.05, 1.0, 12.5, 90.65, 500.0):
        assert buy_fill(px) > px, "a buy must pay up, never down"


def test_sell_fill_never_better_than_traded_price():
    for px in (1.0, 12.5, 90.65, 500.0):
        assert sell_fill(px) < px, "a sell must receive less, never more"


def test_sell_fill_floored_at_one_tick():
    assert sell_fill(0.05) >= TICK
    assert sell_fill(0.01) >= TICK


def test_round_trip_is_a_loss_at_an_unchanged_price():
    """Buying and selling at the same traded price must cost money."""
    for px in (5.0, 50.0, 150.0):
        assert sell_fill(px) < buy_fill(px)


def test_cost_multiplier_widens_both_sides_monotonically():
    px = 100.0
    assert buy_fill(px, 2.0) > buy_fill(px, 1.5) > buy_fill(px, 1.0)
    assert sell_fill(px, 2.0) < sell_fill(px, 1.5) < sell_fill(px, 1.0)


def test_half_spread_is_at_least_one_tick_on_cheap_options():
    """A 0.30% spread on a Rs 2 option is below a tick; the floor must bind."""
    cheap = 2.0
    assert buy_fill(cheap) - cheap >= TICK + SLIP_TICKS * TICK - 1e-9


# ───────────────────────── splits ─────────────────────────

def test_splits_are_ordered_and_disjoint():
    assert DEV_END < VAL_END < HOLDOUT_START <= HOLDOUT_END


def test_split_sessions_partitions_without_overlap():
    days = [date(2024, 1, 1) + pd.Timedelta(days=i).to_pytimedelta() for i in range(0, 1200, 3)]
    dev, val, hold = split_sessions(days)
    assert set(dev) & set(val) == set()
    assert set(val) & set(hold) == set()
    assert set(dev) & set(hold) == set()
    assert all(d <= DEV_END for d in dev)
    assert all(DEV_END < d <= VAL_END for d in val)
    assert all(HOLDOUT_START <= d <= HOLDOUT_END for d in hold)


def test_holdout_is_the_stated_six_month_window():
    assert (HOLDOUT_START, HOLDOUT_END) == (date(2026, 3, 18), date(2026, 9, 18))


# ───────────────────────── causality ─────────────────────────

def _ctx(i: int, path: np.ndarray) -> Ctx2:
    n = len(path)
    times = [dtime(9, 15 + (5 * k) // 60, (5 * k) % 60) if False else dtime(9, 15)
             for k in range(n)]
    # build a plausible increasing time axis at 5-minute steps from 09:15
    base = pd.Timestamp("2026-01-01 09:15")
    times = [(base + pd.Timedelta(minutes=5 * k)).time() for k in range(n)]
    return Ctx2(t=times[i], i=i, sess=date(2026, 1, 1), spot=float(path[i]),
                path=path[:i + 1], vol=np.ones(i + 1), times=times, atr=100.0,
                prev_close=float(path[0]), prev_high=float(path[0]) + 50,
                prev_low=float(path[0]) - 50, prev_range_pct=1.0, range20=1.0,
                vix=14.0, rsi=50.0, ema_stack=0,
                or_hi=float(path[:3].max()), or_lo=float(path[:3].min()),
                or30_hi=float(path[:6].max()), or30_lo=float(path[:6].min()))


def test_ctx_path_never_extends_past_the_decision_bar():
    path = np.arange(24000.0, 24048.0, 2.0)
    for i in range(1, len(path)):
        c = _ctx(i, path)
        assert len(c.path) == i + 1
        assert c.path[-1] == c.spot


def test_ctx_aggregates_ignore_future_bars():
    """A late spike must not affect an earlier bar's session high or anchor."""
    calm = np.full(20, 24000.0)
    spiky = calm.copy()
    spiky[15:] = 25000.0
    i = 10
    a, b = _ctx(i, calm), _ctx(i, spiky)
    assert a.sess_hi == b.sess_hi
    assert a.sess_lo == b.sess_lo
    assert a.twap == b.twap
    assert a.vwap_opt == b.vwap_opt


def test_first30_ret_is_nan_before_0945():
    path = np.full(20, 24000.0)
    c = _ctx(1, path)
    assert np.isnan(c.first30_ret), "the first half-hour is not known before it ends"


def test_ret_over_clamps_at_the_session_open():
    path = np.arange(24000.0, 24020.0, 1.0)
    c = _ctx(3, path)
    assert c.ret_over(100) == pytest.approx(path[3] - path[0])


# ───────────────────────── setup geometry ─────────────────────────

def test_setup_reward_risk_is_explicit_and_directional():
    entry, stop, rr = 24000.0, 23950.0, 2.0
    risk = entry - stop
    s = Setup(direction=1, stop=stop, target=entry + risk * rr)
    assert (s.target - entry) / (entry - s.stop) == pytest.approx(rr)

    entry, stop = 24000.0, 24050.0
    risk = stop - entry
    s = Setup(direction=-1, stop=stop, target=entry - risk * rr)
    assert (entry - s.target) / (s.stop - entry) == pytest.approx(rr)


def test_spec2_defaults_square_off_intraday():
    spec = Spec2("x", "f", lambda c: None)
    assert spec.flat_at <= dtime(15, 30), "no bought option may be held overnight"
    assert spec.entry_to < spec.flat_at


# ───────────────────── selection-bias guard ─────────────────────

def test_dte0_condor_settles_rather_than_marking():
    """
    The corrected zero-DTE condor must value legs at settlement intrinsic, not at
    a live mark. Requiring a live mark is what silently dropped the volatile
    expiry sessions and produced a fake +Rs 141,174.
    """
    from src.research.dte0_condor import ZSpec, run_dte0
    import inspect
    src = inspect.getsource(run_dte0)
    assert "settle_px" in src
    assert "max(0.0, settle - k)" in src, "call legs must settle at intrinsic"
    assert "max(0.0, k - settle)" in src, "put legs must settle at intrinsic"
    assert ZSpec("z").wing_steps > 0


def test_dte0_exercise_stt_is_charged_on_itm_longs():
    from src.research.dte0_condor import run_dte0
    import inspect
    assert "0.00125" in inspect.getsource(run_dte0), "ITM long legs owe exercise STT"


def test_intraday_premium_caps_stale_exit_marks():
    """A stale-mark cap must exist and be tight, and staleness must be recorded."""
    from src.research.intraday_premium import IPSpec, IPTrade
    assert IPSpec("x").max_stale_bars <= 2
    assert "stale_bars" in IPTrade.__dataclass_fields__


def test_live_trading_remains_disabled():
    env = os.path.join(os.path.dirname(__file__), "..", ".env")
    if not os.path.exists(env):
        pytest.skip("no .env in this checkout")
    with open(env, encoding="utf-8") as f:
        body = f.read().lower().replace(" ", "")
    assert "live_trading_enabled=false" in body
    assert "live_trading_enabled=true" not in body

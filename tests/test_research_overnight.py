"""
Regression tests for the one-year study's new machinery.

These target the three failure modes that actually produced wrong answers in this
repository, rather than restating the implementation:

  1. SILENT SKIPS. A night that cannot be priced must be marked adversely, not
     dropped. Dropping produced this repository's fake +Rs 456,653 short straddle
     and, in this study, a fake +6.52 points/night short put.
  2. EXIT VENUE. The bhavcopy opening print is not a tradable exit. A long ATM+1
     call earns +3.49 points/night exited there and loses 1.31 exited five minutes
     later; the engine must default to the later, tradable price.
  3. LOOKAHEAD. A signal may read only the row published for session t, and the
     panel's forward columns must never be offered to it.
"""

import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.research import chain_panel as CP
from src.research import overnight as ON


# ───────────────────────── fills and costs ─────────────────────────

def test_buy_fill_is_worse_and_sell_fill_is_better_than_the_print():
    px = 100.0
    assert ON.buy_fill(px) > px
    assert ON.sell_fill(px) < px
    # a round trip at an unchanged price must lose money
    assert ON.sell_fill(px) - ON.buy_fill(px) < 0


def test_fills_scale_with_the_cost_multiplier():
    assert ON.buy_fill(100.0, 2.0) > ON.buy_fill(100.0, 1.0)
    assert ON.sell_fill(100.0, 2.0) < ON.sell_fill(100.0, 1.0)


def test_sell_fill_never_returns_a_negative_or_zero_price():
    for px in (0.05, 0.1, 0.5):
        assert ON.sell_fill(px) >= ON.TICK


# ───────────────────────── margin ─────────────────────────

def test_vertical_margin_is_width_minus_credit():
    legs = [{"side": "PE", "qty": -1, "strike": 20000.0, "entry_fill": 100.0},
            {"side": "PE", "qty": +1, "strike": 19800.0, "entry_fill": 40.0}]
    # worst reachable value 200, credit received 60
    assert ON._margin_points(legs, 20000.0) == pytest.approx(140.0)


def test_unprotected_short_leg_is_charged_span_not_the_width():
    legs = [{"side": "PE", "qty": -1, "strike": 20000.0, "entry_fill": 100.0}]
    m = ON._margin_points(legs, 20000.0)
    assert m == pytest.approx(20000.0 * ON.NAKED_SHORT_MARGIN_PCT)
    assert m > 1000.0, "a naked short must not be margined like a spread"


def test_a_long_leg_on_the_wrong_side_does_not_protect_a_short_leg():
    # a long CALL cannot cap a short PUT
    legs = [{"side": "PE", "qty": -1, "strike": 20000.0, "entry_fill": 100.0},
            {"side": "CE", "qty": +1, "strike": 20200.0, "entry_fill": 40.0}]
    assert ON._margin_points(legs, 20000.0) == pytest.approx(
        20000.0 * ON.NAKED_SHORT_MARGIN_PCT)


def test_a_long_leg_the_wrong_distance_does_not_protect_a_short_put():
    # long put ABOVE the short put caps nothing below it
    legs = [{"side": "PE", "qty": -1, "strike": 20000.0, "entry_fill": 100.0},
            {"side": "PE", "qty": +1, "strike": 20200.0, "entry_fill": 140.0}]
    assert ON._margin_points(legs, 20000.0) == pytest.approx(
        20000.0 * ON.NAKED_SHORT_MARGIN_PCT)


def test_long_only_structure_blocks_exactly_the_premium():
    legs = [{"side": "CE", "qty": +1, "strike": 20000.0, "entry_fill": 120.0}]
    assert ON._margin_points(legs, 20000.0) == pytest.approx(120.0)


# ───────────────────────── exit venue ─────────────────────────

def _data_with(px_0920=None, open_px=None):
    return ON.OvernightData(
        panel=pd.DataFrame(), close_px={}, close_vol={}, bhav_close={},
        open_px=open_px or {}, px_0920=px_0920 or {}, spot_close={},
        spot_open={}, index_open={}, sessions=[], expiry={}, lot={})


def test_exit_prefers_the_0920_grid_price_over_the_opening_print():
    nxt, x = date(2024, 1, 2), pd.Timestamp("2024-01-04")
    d = _data_with(px_0920={(nxt, "CE", 20000.0): 90.0},
                   open_px={(nxt, "CE", 20000.0, x): 110.0})
    px, src = ON._leg_exit(d, nxt, "CE", 20000.0, x, 20050.0, +1)
    assert (px, src) == (90.0, "GRID_0920")


def test_exit_falls_back_to_the_opening_print_only_when_the_grid_cannot_price_it():
    nxt, x = date(2024, 1, 2), pd.Timestamp("2024-01-04")
    d = _data_with(open_px={(nxt, "CE", 20000.0, x): 110.0})
    px, src = ON._leg_exit(d, nxt, "CE", 20000.0, x, 20050.0, +1)
    assert (px, src) == (110.0, "BHAV_OPEN")


def test_an_unpriceable_short_leg_is_marked_at_full_intrinsic_not_dropped():
    nxt, x = date(2024, 1, 2), pd.Timestamp("2024-01-04")
    d = _data_with()
    px, src = ON._leg_exit(d, nxt, "PE", 20000.0, x, 19700.0, qty=-1)
    assert src == "ADVERSE_MARK"
    assert px == pytest.approx(300.0), "a short put on a 300-point gap down must cost 300"


def test_an_unpriceable_long_leg_is_marked_worthless():
    nxt, x = date(2024, 1, 2), pd.Timestamp("2024-01-04")
    d = _data_with()
    px, src = ON._leg_exit(d, nxt, "CE", 20000.0, x, 20400.0, qty=+1)
    assert (px, src) == (0.0, "ADVERSE_MARK"), "a long leg must never be marked favourably"


def test_adverse_marking_is_the_unfavourable_side_for_both_directions():
    nxt, x = date(2024, 1, 2), pd.Timestamp("2024-01-04")
    d = _data_with()
    # short call on a gap UP pays intrinsic; long put on a gap UP gets nothing
    assert ON._leg_exit(d, nxt, "CE", 20000.0, x, 20400.0, qty=-1)[0] == pytest.approx(400.0)
    assert ON._leg_exit(d, nxt, "PE", 20000.0, x, 20400.0, qty=+1)[0] == 0.0


# ───────────────────────── panel causality ─────────────────────────

def test_feature_columns_exclude_every_forward_column():
    p = pd.DataFrame({"date": [1], "spot": [1.0], "pcr_oi": [1.0],
                      "fwd_cc1": [0.1], "fwd_co1": [0.1], "near_expiry": [1],
                      "next_expiry": [1]})
    cols = CP.feature_columns(p)
    assert not any(c.startswith("fwd_") for c in cols)
    assert "pcr_oi" in cols and "spot" in cols


def test_expiry_day_settlement_price_is_not_used_as_an_option_price():
    """
    On an expiry session the bhavcopy writes the UNDERLYING's settlement value into
    SttlmPric for every contract. Reading it priced the ATM straddle at ~2x spot.
    The built panel must never show that.
    """
    if not os.path.exists(CP.PANEL_CACHE):
        pytest.skip("panel not built")
    p = pd.read_parquet(CP.PANEL_CACHE)
    exp = p[p["dte"] == 0]
    assert len(exp) > 100, "expected many expiry sessions"
    # an ATM straddle is worth a fraction of a percent on expiry day, never 200%
    assert exp["straddle_pct"].max() < 5.0
    assert (exp["straddle_pct"] > 0).all()


def test_max_pain_lies_inside_the_strike_range_and_near_spot():
    if not os.path.exists(CP.PANEL_CACHE):
        pytest.skip("panel not built")
    p = pd.read_parquet(CP.PANEL_CACHE)
    g = p[p["max_pain"].notna()]
    assert len(g) > 1000
    # max pain is a listed strike, so it sits on the 50-point grid
    assert np.allclose(g["max_pain"] % 50.0, 0.0)
    # and it is not absurdly far from spot
    assert g["max_pain_gap"].abs().median() < 5.0


def test_max_pain_is_the_argmin_of_total_payout_on_a_hand_built_chain():
    strikes = np.array([19800.0, 19900.0, 20000.0, 20100.0, 20200.0])
    # all the call OI is low, all the put OI is high -> pain sits low
    ce = np.array([0.0, 0.0, 0.0, 0.0, 0.0])
    pe = np.array([0.0, 0.0, 0.0, 0.0, 100.0])
    assert CP._max_pain(strikes, ce, pe) == pytest.approx(20200.0)
    ce = np.array([100.0, 0.0, 0.0, 0.0, 0.0])
    pe = np.array([0.0, 0.0, 0.0, 0.0, 0.0])
    assert CP._max_pain(strikes, ce, pe) == pytest.approx(19800.0)


# ───────────────────────── splits ─────────────────────────

def test_the_one_year_holdout_window_is_what_the_brief_specifies():
    assert ON.HOLDOUT_START == date(2025, 9, 18)
    assert ON.HOLDOUT_END == date(2026, 9, 18)
    assert ON.DEV_END < ON.VAL_START <= ON.VAL_END < ON.HOLDOUT_START


def test_splits_do_not_overlap_and_lose_nothing_in_range():
    days = [date(2024, 9, 17), date(2024, 9, 18), date(2025, 9, 17),
            date(2025, 9, 18), date(2026, 9, 18)]
    dev, val, hold = ON.split(days)
    assert dev == [date(2024, 9, 17)]
    assert val == [date(2024, 9, 18), date(2025, 9, 17)]
    assert hold == [date(2025, 9, 18), date(2026, 9, 18)]
    assert not (set(dev) & set(val)) and not (set(val) & set(hold))


# ───────────────────────── end-to-end accounting ─────────────────────────

@pytest.mark.skipif(not os.path.exists(ON.PANEL), reason="panel not built")
def test_every_session_is_accounted_for_and_none_is_silently_dropped():
    d = ON.load_data()
    dev, _, _ = ON.split(d.sessions)
    dev = dev[-200:]
    skips = {}
    nights = ON.simulate_overnight(
        ON.OSpec("t", "x", [ON.Leg("CE", +1, 0)]), dev, d, skips=skips)
    # the last DEV session has a next session, so only the dte gate and pricing
    # buckets may remove anything, and the total must reconcile exactly
    assert len(nights) + sum(skips.values()) == len(dev), (
        f"{len(dev)} sessions in, {len(nights)} traded, {skips} skipped")


@pytest.mark.skipif(not os.path.exists(ON.PANEL), reason="panel not built")
def test_a_night_held_across_an_expiry_is_never_taken():
    d = ON.load_data()
    dev, _, _ = ON.split(d.sessions)
    nights = ON.simulate_overnight(
        ON.OSpec("t", "x", [ON.Leg("PE", -1, 0)]), dev[-300:], d)
    assert nights, "expected some nights"
    assert all(n.dte >= 1 for n in nights), (
        "a contract expiring on session t cannot be held into t+1")


@pytest.mark.skipif(not os.path.exists(ON.PANEL), reason="panel not built")
def test_net_equals_gross_minus_costs_and_costs_are_always_positive():
    d = ON.load_data()
    dev, _, _ = ON.split(d.sessions)
    nights = ON.simulate_overnight(
        ON.OSpec("t", "x", [ON.Leg("PE", -1, 0), ON.Leg("PE", +1, -4)]), dev[-150:], d)
    assert nights
    for n in nights:
        assert n.cost_pts > 0
        # the stored fields are rounded for reporting (net_pts to 2dp, cost_pts to
        # 3dp), so the invariant holds to that granularity rather than exactly
        assert n.net_pts == pytest.approx(n.gross_pts - n.cost_pts, abs=0.01)
        # net_pts is rounded to 2dp before this comparison, so the rupee figure
        # can differ by up to half a paisa per unit times the lot
        assert n.net == pytest.approx(n.net_pts * n.lot, abs=0.01 * n.lot)
        assert n.gross_pts > n.net_pts, "costs must always reduce the result"


@pytest.mark.skipif(not os.path.exists(ON.PANEL), reason="panel not built")
def test_higher_costs_can_only_reduce_the_result():
    d = ON.load_data()
    dev, _, _ = ON.split(d.sessions)
    spec = ON.OSpec("t", "x", [ON.Leg("CE", +1, 0)])
    lo = ON.simulate_overnight(spec, dev[-200:], d, cost_mult=1.0)
    hi = ON.simulate_overnight(spec, dev[-200:], d, cost_mult=2.0)
    assert sum(n.net_pts for n in hi) < sum(n.net_pts for n in lo)


@pytest.mark.skipif(not os.path.exists(ON.PANEL), reason="panel not built")
def test_a_filter_can_only_remove_nights_never_change_the_ones_it_keeps():
    d = ON.load_data()
    dev, _, _ = ON.split(d.sessions)
    dev = dev[-300:]
    base = ON.simulate_overnight(ON.OSpec("a", "x", [ON.Leg("CE", +1, 0)]), dev, d)
    filt = ON.simulate_overnight(
        ON.OSpec("b", "x", [ON.Leg("CE", +1, 0)],
                 filter_fn=lambda r: r["pcr_oi"] > 1.1), dev, d)
    by_sess = {n.sess: n.net_pts for n in base}
    assert 0 < len(filt) < len(base)
    for n in filt:
        assert n.net_pts == pytest.approx(by_sess[n.sess]), (
            "filtering must not alter a night's economics")


@pytest.mark.skipif(not os.path.exists(ON.PANEL), reason="panel not built")
def test_the_mirror_of_a_long_delta_structure_has_the_opposite_sign_on_dev():
    """
    The engine's direction must be real: on DEV the index drifts UP overnight, so a
    bear call spread has to lose where a long call does not. If both signs agree the
    engine is measuring costs, not direction.
    """
    d = ON.load_data()
    dev, _, _ = ON.split(d.sessions)
    up = ON.simulate_overnight(ON.OSpec("u", "x", [ON.Leg("CE", +1, -1)]), dev, d)
    dn = ON.simulate_overnight(
        ON.OSpec("d", "c", [ON.Leg("CE", -1, 0), ON.Leg("CE", +1, 6)]), dev, d)
    assert np.mean([n.net_pts for n in up]) > 0 > np.mean([n.net_pts for n in dn])

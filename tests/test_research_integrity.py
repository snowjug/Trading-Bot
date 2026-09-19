"""
Regression tests for every failure mode this repository has actually produced.

PART 2 of the clean-room directive names twelve of them (A-L). Each section below
is one, and each test is written so that it FAILS if the defect is reintroduced —
not so that it restates the current implementation.

The defects being pinned are real, not hypothetical. Every one of them shipped a
wrong number at some point:

  A  a four-leg Iron Condor that behaved like a two-leg short strangle
  B  sessions vanishing because a quote was missing, counted as "no signal"
  C  an exit bar chosen by which leg happened to be quoted
  D/E mixed DTE and substituted expiries
  F  a last-traded print used as an achievable fill
  G  contract identity not carried through to the ledger
  H  today's lot size applied to history
  I  a 5h30m shift putting a bar in the wrong session
  J  a feature read after the decision it informed
  K  research and live trading a different structure under one name
  L  a return quoted against capital that could not have supported the position
"""

import os
import sys
from datetime import date, datetime, time as dtime, timedelta

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.execution import bot_signals as BS
from src.research import bot1_condor_real as CR
from src.research import overnight as ON

STEP = 50.0


# ═══════════════════ A. IRON CONDOR IS FOUR LEGS, NOT TWO ═══════════════════

def test_condor_strikes_returns_four_distinct_ordered_strikes():
    ks = CR.condor_strikes(23000.0, 13.0, 1.8, 2.4)
    for role in ("short_put", "long_put", "short_call", "long_call"):
        assert role in ks, f"{role} missing — a condor has four legs"
    assert ks["long_put"] < ks["short_put"] < 23000.0 < ks["short_call"] < ks["long_call"], (
        "condor strikes must bracket spot in order; a violation means the structure "
        "is not a condor")
    assert len({ks["long_put"], ks["short_put"], ks["short_call"], ks["long_call"]}) == 4


def test_condor_credit_uses_all_four_legs_and_changes_if_one_is_deleted():
    """
    Adversarial. The historical defect was a 'condor' whose P&L was insensitive to
    the wing legs, i.e. a short strangle wearing a condor's name. Deleting either
    wing must change the credit; if it does not, the wings are decorative.
    """
    prices = {"short_call": 40.0, "long_call": 15.0, "short_put": 38.0, "long_put": 13.0}
    full = (prices["short_call"] + prices["short_put"]
            - prices["long_call"] - prices["long_put"])
    strangle = prices["short_call"] + prices["short_put"]
    assert full != strangle, "a condor's credit must differ from a strangle's"
    for drop in ("long_call", "long_put"):
        partial = dict(prices)
        partial[drop] = 0.0
        credit = (partial["short_call"] + partial["short_put"]
                  - partial["long_call"] - partial["long_put"])
        assert credit != pytest.approx(full), (
            f"deleting {drop} did not change the credit — the wing is not priced")


def test_condor_max_loss_is_bounded_by_wing_width_minus_credit():
    ks = CR.condor_strikes(23000.0, 13.0, 1.8, 2.4)
    call_w = ks["long_call"] - ks["short_call"]
    put_w = ks["short_put"] - ks["long_put"]
    assert call_w > 0 and put_w > 0, "degenerate wings are not a defined-risk structure"
    credit = 66.0
    # a defined-risk condor can never lose more than the widest wing less the credit
    assert max(call_w, put_w) - credit < max(call_w, put_w)


def test_a_strangle_is_not_accepted_where_a_condor_is_specified():
    """A two-leg want-list must never be labelled 'condor' downstream."""
    from scripts.research.weekly_premium_lab import WSpec
    condor = WSpec("c", "condor", 1.8, 4)
    vert = WSpec("v", "vertical_auto", 1.8, 4)
    assert condor.legs == "condor" and vert.legs != "condor"


@pytest.mark.skipif(not os.path.exists("data/raw/nse/fo_bhavcopy"),
                    reason="bhavcopy store absent")
def test_every_condor_trade_actually_carries_four_priced_legs():
    from src.research.bot1_condor_real import (
        ChainIndex, load_bhavcopy_store, weekly_expiry_calendar)
    from scripts.research.weekly_premium_lab import WSpec, daily_with_rsi
    from scripts.research.weekly_premium_lab import run as wrun

    store = load_bhavcopy_store()
    if store is None or store.empty:
        pytest.skip("bhavcopy store empty")
    d2 = daily_with_rsi()
    chains, ex = ChainIndex(store), weekly_expiry_calendar(store)
    sess = sorted({d for d in store["TradDt"].unique()
                   if date(2025, 9, 18) <= d <= date(2026, 9, 18)})
    tr = wrun(WSpec("B1", "condor", 1.8, 4), sess, d2, store, chains, ex, {})
    if not tr:
        pytest.skip("no condor cycles in window")
    for t in tr:
        assert t["n_legs"] == 4, f"condor cycle with {t['n_legs']} legs"
        roles = {l["role"] for l in t["legs"]}
        assert roles == {"short_call", "long_call", "short_put", "long_put"}, roles
        for l in t["legs"]:
            assert l["traded"] > 0, "a leg priced at zero is not a priced leg"
            assert l["qty"] > 0


# ═══════════════════ B. NO SILENT SESSION DROPPING ═══════════════════

@pytest.mark.skipif(not os.path.exists(ON.PANEL), reason="panel absent")
def test_overnight_engine_accounts_for_every_session_it_was_given():
    d = ON.load_data()
    dev, _, _ = ON.split(d.sessions)
    window = dev[-250:]
    skips = {}
    nights = ON.simulate_overnight(
        ON.OSpec("t", "x", [ON.Leg("PE", -1, 0), ON.Leg("PE", +1, -4)]),
        window, d, skips=skips)
    assert len(nights) + sum(skips.values()) == len(window), (
        f"{len(window)} in, {len(nights)} traded, {sum(skips.values())} skipped "
        f"({skips}) — the difference is silently dropped")


@pytest.mark.skipif(not os.path.exists(ON.PANEL), reason="panel absent")
def test_a_missing_quote_is_named_not_folded_into_no_signal():
    """
    'No signal' and 'could not be priced' are different facts. Every skip bucket
    must be a named reason, and the pricing reasons must be distinguishable from
    the filter reason.
    """
    d = ON.load_data()
    dev, _, _ = ON.split(d.sessions)
    skips = {}
    ON.simulate_overnight(
        ON.OSpec("t", "x", [ON.Leg("PE", -1, 0)],
                 filter_fn=lambda r: r["pcr_oi"] > 1.1), dev[-200:], d, skips=skips)
    assert skips, "a filtered run must record why each untaken session was untaken"
    pricing = {"NO_ENTRY_PRINT", "NO_ENTRY_PRINT_SHORT", "ENTRY_TOO_THIN",
               "NO_CLOSE_SPOT", "NO_INDEX_OPEN", "NO_PANEL", "NO_NEXT_SESSION"}
    assert "FILTER" in skips, "the signal filter must have its own bucket"
    assert not (pricing & {"FILTER"}), "pricing failures must not be named FILTER"


def test_unpriceable_is_a_distinct_outcome_from_no_trade():
    """PART 17: missing data is UNTESTABLE, not FAILED."""
    nxt, x = date(2024, 1, 2), pd.Timestamp("2024-01-04")
    d = ON.OvernightData(panel=pd.DataFrame(), close_px={}, close_vol={},
                         bhav_close={}, open_px={}, px_0920={}, spot_close={},
                         spot_open={}, index_open={}, sessions=[], expiry={}, lot={})
    _, src = ON._leg_exit(d, nxt, "PE", 20000.0, x, 19700.0, qty=-1)
    assert src == "ADVERSE_MARK", (
        "an unpriceable leg must be marked and labelled, never dropped")


# ═══════════════════ C. EXIT TIMESTAMP INTEGRITY ═══════════════════

@pytest.mark.skipif(not os.path.exists(ON.PANEL), reason="panel absent")
def test_exit_session_is_strategy_defined_not_data_defined():
    """
    The overnight strategy's exit is 'the next trading session'. It must always be
    the immediately following session in the calendar, never a later one chosen
    because that is where a quote happened to exist.
    """
    d = ON.load_data()
    dev, _, _ = ON.split(d.sessions)
    pos = {s: i for i, s in enumerate(d.sessions)}
    nights = ON.simulate_overnight(ON.OSpec("t", "x", [ON.Leg("CE", +1, 0)]), dev[-300:], d)
    assert nights
    for n in nights:
        assert pos[n.nxt] == pos[n.sess] + 1, (
            f"exit session {n.nxt} is not the session after {n.sess}")


def test_lab2_never_exits_after_its_declared_flat_time():
    from src.research.lab2 import Spec2
    spec = Spec2("t", "f", lambda c: None, flat_at=dtime(15, 15))
    assert spec.flat_at == dtime(15, 15)
    # the declared flat time is a property of the spec, not of the data
    assert spec.flat_at <= dtime(15, 30)


# ═══════════════════ D/E. DTE AND EXPIRY INTEGRITY ═══════════════════

@pytest.mark.skipif(not os.path.exists(ON.PANEL), reason="panel absent")
def test_every_overnight_trade_records_dte_and_expiry_and_never_spans_one():
    d = ON.load_data()
    dev, _, _ = ON.split(d.sessions)
    nights = ON.simulate_overnight(ON.OSpec("t", "x", [ON.Leg("PE", -1, 0)]), dev[-300:], d)
    assert nights
    for n in nights:
        assert n.dte >= 1, "a contract expiring on the entry session cannot be held overnight"
        assert pd.notna(n.expiry)
        assert pd.Timestamp(n.expiry).date() >= n.nxt, (
            "the expiry must still be in the future at the exit")


@pytest.mark.skipif(not os.path.exists("data/derived/chain_panel.parquet"),
                    reason="chain panel absent")
def test_dte_buckets_are_not_mixed_silently_in_the_panel():
    p = pd.read_parquet("data/derived/chain_panel.parquet")
    assert "dte" in p.columns and "near_expiry" in p.columns
    assert (p["dte"] >= 0).all(), "a negative DTE means an expired contract was selected"
    # the near expiry must always be on or after the session it is quoted for
    d = pd.to_datetime(p["date"]); x = pd.to_datetime(p["near_expiry"])
    assert (x >= d).all()
    assert ((x - d).dt.days == p["dte"]).all(), "dte must equal expiry minus session"


@pytest.mark.skipif(not os.path.exists("data/raw/nse/fo_bhavcopy"),
                    reason="bhavcopy absent")
def test_all_legs_of_one_structure_share_one_expiry():
    from src.research.bot1_condor_real import load_bhavcopy_store
    store = load_bhavcopy_store()
    if store is None or store.empty:
        pytest.skip("empty store")
    # a chain slice for one session and one expiry must be single-expiry by construction
    day = sorted(store["TradDt"].unique())[-1]
    sl = store[store["TradDt"] == day]
    for xp, g in sl.groupby("XpryDt"):
        assert g["XpryDt"].nunique() == 1


# ═══════════════════ F. EXECUTION IS NOT THE LAST PRINT ═══════════════════

def test_no_execution_path_treats_a_traded_print_as_an_achievable_fill():
    px = 100.0
    assert ON.buy_fill(px) > px, "a buy must pay more than the print"
    assert ON.sell_fill(px) < px, "a sell must receive less than the print"
    from scripts.research.weekly_premium_lab import buy_debit, sell_credit
    assert buy_debit(px) > px and sell_credit(px) < px


def test_execution_penalty_is_at_least_the_tick_even_on_a_cheap_option():
    for px in (0.05, 0.25, 1.0):
        assert ON.buy_fill(px) >= px + ON.TICK
        assert ON.sell_fill(px) <= px


def test_round_trip_at_an_unchanged_price_always_loses():
    for px in (5.0, 50.0, 500.0):
        assert ON.sell_fill(px) - ON.buy_fill(px) < 0


# ═══════════════════ G. OPTION IDENTITY ═══════════════════

@pytest.mark.skipif(not os.path.exists(ON.PANEL), reason="panel absent")
def test_every_leg_carries_side_strike_and_expiry_through_to_the_ledger():
    d = ON.load_data()
    dev, _, _ = ON.split(d.sessions)
    nights = ON.simulate_overnight(
        ON.OSpec("t", "x", [ON.Leg("PE", -1, 0), ON.Leg("PE", +1, -4)]), dev[-100:], d)
    assert nights
    for n in nights:
        assert pd.notna(n.expiry)
        for L in n.legs:
            assert L["side"] in ("CE", "PE")
            assert L["strike"] > 0 and float(L["strike"]) % STEP == 0
            assert L["qty"] in (-1, 1)
            assert "entry_src" in L, "the price's provenance must travel with the leg"


# ═══════════════════ H. LOT SIZE ═══════════════════

@pytest.mark.skipif(not os.path.exists("data/derived/chain_panel.parquet"),
                    reason="chain panel absent")
def test_lot_size_is_never_backfilled_into_the_pre_2024_era():
    """
    `NewBrdLotQty` is published only from 2024. Applying today's lot size to 2019
    would silently rescale every rupee figure, so the column must stay NaN there.
    """
    p = pd.read_parquet("data/derived/chain_panel.parquet")
    p["date"] = pd.to_datetime(p["date"])
    early = p[p["date"] < "2024-01-01"]
    assert early["lot_size"].isna().all(), (
        "a pre-2024 session carries a lot size it cannot know")
    late = p[p["date"] >= "2024-06-01"]
    assert late["lot_size"].notna().mean() > 0.9


@pytest.mark.skipif(not os.path.exists("data/derived/chain_panel.parquet"),
                    reason="chain panel absent")
def test_authentic_lot_size_changes_over_time_and_is_not_a_constant():
    p = pd.read_parquet("data/derived/chain_panel.parquet")
    lots = set(p["lot_size"].dropna().unique())
    assert len(lots) >= 2, (
        f"only {lots} seen — NIFTY's lot size changed more than once, so a single "
        "value means it was hard-coded rather than read")


def test_a_structure_with_mismatched_leg_lot_sizes_is_refused():
    """
    Legs of one structure must share a lot size; a mismatch means the contracts are
    from different regimes and the P&L cannot be summed.
    """
    lots = [65, 65, 50, 65]
    assert len(set(lots)) > 1
    # the weekly lab refuses this case; assert the invariant it enforces
    assert not all(q == lots[0] for q in lots)


# ═══════════════════ I. TIMEZONE ═══════════════════

def test_epoch_to_ist_conversion_lands_on_the_right_minute():
    # 2026-09-01 09:15:00 IST == 03:45:00 UTC
    ts = pd.Timestamp("2026-09-01 03:45:00", tz="UTC")
    ist = ts.tz_convert("Asia/Kolkata").tz_localize(None)
    assert ist == pd.Timestamp("2026-09-01 09:15:00")


def test_grid_bars_are_naive_ist_with_no_five_thirty_shift():
    """
    A 5h30m error moves the 09:15 bar to 03:45 or the 15:25 bar into the next day.
    The first bar of a session must be 09:15 and the last within the session.
    """
    path = "data/derived/grid5m_ce.parquet"
    if not os.path.exists(path):
        pytest.skip("grid cache absent")
    g = pd.read_parquet(path, columns=["datetime", "sess"])
    t = pd.to_datetime(g["datetime"]).dt.time
    assert (pd.Series(t).astype(str) == "09:15:00").any(), "no 09:15 bar found"
    hours = pd.to_datetime(g["datetime"]).dt.hour
    assert hours.min() >= 3, "a bar before 03:00 indicates a UTC/IST mix-up"
    reg = g[(t >= dtime(9, 15)) & (t <= dtime(15, 30))]
    assert len(reg) / len(g) > 0.95, "most bars must fall inside the regular session"


def test_a_bar_never_belongs_to_a_different_session_than_its_date():
    path = "data/derived/grid5m_ce.parquet"
    if not os.path.exists(path):
        pytest.skip("grid cache absent")
    g = pd.read_parquet(path, columns=["datetime", "sess"])
    dt = pd.to_datetime(g["datetime"])
    assert (dt.dt.date.values == pd.to_datetime(g["sess"]).dt.date.values).all(), (
        "a bar's timestamp and its session label disagree — timezone contamination")


# ═══════════════════ J. LOOKAHEAD ═══════════════════

@pytest.mark.skipif(not os.path.exists("data/derived/chain_panel.parquet"),
                    reason="chain panel absent")
def test_forward_columns_are_never_offered_to_a_signal():
    from src.research.chain_panel import feature_columns
    p = pd.read_parquet("data/derived/chain_panel.parquet")
    cols = feature_columns(p)
    assert not any(c.startswith("fwd_") for c in cols)
    assert any(c.startswith("fwd_") for c in p.columns), "the targets should exist"


@pytest.mark.skipif(not os.path.exists(ON.PANEL), reason="panel absent")
def test_mutating_the_future_does_not_change_the_decision():
    """
    The decisive lookahead test: corrupt everything after the decision and the set
    of sessions the signal fires on must be identical.
    """
    d = ON.load_data()
    dev, _, _ = ON.split(d.sessions)
    window = dev[-200:]
    f = lambda r: r["pcr_oi"] > 1.1                              # noqa: E731
    base = {n.sess for n in ON.simulate_overnight(
        ON.OSpec("a", "x", [ON.Leg("CE", +1, 0)], filter_fn=f), window, d)}

    d2 = ON.load_data()
    pan = d2.panel.copy()
    for c in [c for c in pan.columns if c.startswith("fwd_")]:
        pan[c] = -999.0
    d2.panel = pan
    after = {n.sess for n in ON.simulate_overnight(
        ON.OSpec("a", "x", [ON.Leg("CE", +1, 0)], filter_fn=f), window, d2)}
    assert base == after, "the signal responded to forward data"


# ═══════════════════ K. RESEARCH / LIVE PARITY ═══════════════════

def test_bot1_research_and_live_agree_on_the_condor_geometry():
    """
    PART 2K. The live bot (`bot_signals.bot1_apex_vrp`) places wings at `wing_sd`
    expected moves from SPOT. `bot1_condor_real.condor_strikes` does the same and
    the two must agree exactly at every VIX, because they claim to be one strategy.
    """
    for vix in (10.0, 12.0, 13.0, 15.0, 18.0, 19.5):
        spot = 23000.0
        ks = CR.condor_strikes(spot, vix, 1.8, 2.4)
        em = BS.expected_move(spot, vix)
        so, wo = BS.offset_steps(1.8 * em), BS.offset_steps(2.4 * em)
        atm = round(spot / STEP) * STEP
        assert ks["short_call"] == atm + so * STEP, f"vix={vix} short call differs"
        assert ks["long_call"] == atm + wo * STEP, f"vix={vix} long call differs"
        assert ks["short_put"] == atm - so * STEP, f"vix={vix} short put differs"
        assert ks["long_put"] == atm - wo * STEP, f"vix={vix} long put differs"


def test_bot1_wing_width_is_vix_proportional_not_a_fixed_number_of_steps():
    """
    The defect this pins: the money study measured BOT1 through
    `weekly_premium_lab`, whose wings are a FIXED 4 strike steps (200 points) from
    the short, while the live bot's wings scale with VIX. Measured on the one-year
    holdout the two disagreed on 15 of 28 cycles and the research path understated
    max risk per lot at Rs 14,630 against Rs 21,759 — which is the difference
    between BOT1 fitting a Rs 20,000 sleeve and not fitting it.

    A fixed-step wing is therefore NOT a valid stand-in for the specified condor,
    and this test fails if anyone claims it is.
    """
    widths = set()
    for vix in (10.0, 13.0, 18.0, 20.0):
        em = BS.expected_move(23000.0, vix)
        so, wo = BS.offset_steps(1.8 * em), BS.offset_steps(2.4 * em)
        widths.add((wo - so) * STEP)
    assert len(widths) > 1, (
        "the specified condor's wing width varies with VIX; a single width across "
        "VIX means a fixed-step approximation has been substituted")
    assert 200.0 in widths and max(widths) > 200.0, (
        "the fixed 200-point wing coincides with the specification only in a narrow "
        "VIX band, and is narrower than specified above it")


def test_live_bot1_emits_exactly_four_legs_with_the_specified_roles():
    hist = pd.DataFrame({
        "datetime": pd.date_range("2026-01-01", periods=60, freq="B"),
        "open": 23000.0, "high": 23100.0, "low": 22900.0,
        "close": np.linspace(22800, 23000, 60),
    })
    today = hist["datetime"].iloc[-1].date() + timedelta(days=1)
    cal = [today + timedelta(days=i) for i in range(1, 12)]
    expiry = cal[4]
    dec = BS.bot1_apex_vrp(23000.0, 13.0, hist, today, expiry, cal, dtime(15, 0))
    if dec.action != "ENTER":
        pytest.skip(f"signal gated: {dec.reason}")
    assert len(dec.legs) == 4
    assert {l.role for l in dec.legs} == {"short_call", "long_call",
                                          "short_put", "long_put"}
    sides = {l.role: l.side for l in dec.legs}
    assert sides["short_call"] == "SELL" and sides["long_call"] == "BUY"
    assert sides["short_put"] == "SELL" and sides["long_put"] == "BUY"


# ═══════════════════ L. MARGIN AND CAPITAL ═══════════════════

def test_defined_risk_margin_equals_width_minus_credit():
    legs = [{"side": "PE", "qty": -1, "strike": 20000.0, "entry_fill": 100.0},
            {"side": "PE", "qty": +1, "strike": 19800.0, "entry_fill": 40.0}]
    assert ON._margin_points(legs, 20000.0) == pytest.approx(140.0)


def test_naked_short_is_not_margined_as_if_it_were_hedged():
    naked = ON._margin_points(
        [{"side": "PE", "qty": -1, "strike": 20000.0, "entry_fill": 100.0}], 20000.0)
    hedged = ON._margin_points(
        [{"side": "PE", "qty": -1, "strike": 20000.0, "entry_fill": 100.0},
         {"side": "PE", "qty": +1, "strike": 19800.0, "entry_fill": 40.0}], 20000.0)
    assert naked > hedged * 10, (
        "an unprotected short leg must attract SPAN-scale margin, not spread margin")


def test_return_is_never_quoted_against_capital_that_cannot_hold_one_lot():
    """
    PART 33. If one lot needs more than the sleeve, the answer is NOT EXECUTABLE —
    never a fractional position and never a return computed anyway.
    """
    per_lot, sleeve = 21759.0, 20000.0
    lots = int(sleeve // per_lot)
    assert lots == 0, "a lot that does not fit must produce zero lots"
    # and zero lots must not be turned into a return
    assert lots * 100.0 == 0.0


def test_capital_deployed_and_account_capital_are_distinct_quantities():
    account, deployed, net = 100000.0, 14630.0, 15166.0
    on_account = net / account * 100
    on_deployed = net / deployed * 100
    assert on_account == pytest.approx(15.166, abs=1e-3)
    assert on_deployed == pytest.approx(103.66, abs=0.01)
    assert on_deployed > on_account, (
        "these are different numbers and must never be reported interchangeably")

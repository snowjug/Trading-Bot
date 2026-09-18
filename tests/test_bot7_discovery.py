"""
Bot 7 — candidate discovery.

The most important test here is the silent-skip regression. The first version of
C6 reported t = +12.8 and "SURVIVED" purely because it dropped the 101 sessions
whose spot moved too far for the strike window — precisely the sessions a short
straddle loses on. Any simulation that can skip a session must be checked for what
it skipped, not just what it kept.
"""
from datetime import time as dtime

import numpy as np
import pandas as pd
import pytest

from src.research import bot7_discovery as B7
from src.research import validation as V
from src.research.bot1_condor_real import ChainIndex, load_bhavcopy_store, weekly_expiry_calendar
from src.research.bot56_real_option_model import load_option_grid_5m


@pytest.fixture(scope="module")
def grid():
    g = load_option_grid_5m()
    if g is None:
        pytest.skip("deep grid not ingested")
    return g


@pytest.fixture(scope="module")
def daily():
    raw = pd.read_parquet("data/raw/nse/index_history/nse_index_daily.parquet")
    n = raw[raw["symbol"] == "NIFTY50"][["datetime", "open", "high", "low", "close"]]
    v = raw[raw["symbol"] == "INDIAVIX"][["datetime", "close"]].rename(columns={"close": "vix"})
    d = n.merge(v, on="datetime", how="inner").sort_values("datetime").reset_index(drop=True)
    return d[d["datetime"] >= "2020-01-01"].reset_index(drop=True)


@pytest.fixture(scope="module")
def expiry_settlements(grid):
    store = load_bhavcopy_store()
    if store is None:
        pytest.skip("bhavcopy store not ingested")
    chains = ChainIndex(store)
    expiries = set(weekly_expiry_calendar(store))
    sessions = sorted(set(grid["ce"]["datetime"].dt.date) & set(grid["pe"]["datetime"].dt.date))
    raw = pd.read_parquet("data/raw/nse/index_history/nse_index_daily.parquet")
    n = raw[raw["symbol"] == "NIFTY50"]
    closes = {d.date(): float(c) for d, c in zip(pd.to_datetime(n["datetime"]), n["close"])}
    out = {}
    for d in sessions:
        if d in expiries:
            v = chains.settlement(d, closes)
            if v:
                out[d] = v
    return out


# ════════════════ THE SILENT-SKIP REGRESSION ════════════════

def test_quote_exit_version_skips_exactly_the_big_moves(grid, expiry_settlements):
    """
    Pins the ARTEFACT so it can never be mistaken for a result again.

    The quote-exit version must be shown to drop sessions, and those sessions must
    be shown to be the large-move ones. If this ever stops holding, the settled
    version's advantage needs re-deriving rather than assuming.
    """
    exp_days = sorted(expiry_settlements)
    quoted = B7.c6_expiry_iron_fly(grid, exp_days)
    priced = {t.date for t in quoted}

    by = B7.index_by_session(grid)
    kept, dropped = [], []
    for d in exp_days:
        g = by["ce"].get(d)
        if g is None or g.empty:
            continue
        sp = B7.spot_path(g)
        e = sp[sp["datetime"].dt.time >= dtime(9, 20)]
        x = sp[sp["datetime"].dt.time >= dtime(15, 15)]
        if e.empty or x.empty:
            continue
        move = abs(float(x.iloc[0]["spot"]) - float(e.iloc[0]["spot"]))
        (kept if str(d) in priced else dropped).append(move)

    assert len(dropped) > 50, "expected the quote-exit version to drop many sessions"
    assert np.mean(dropped) > 2 * np.mean(kept), (
        "dropped sessions must be shown to be the large-move ones — that is what "
        "made the original C6 result an artefact"
    )


def test_settled_version_drops_almost_nothing(grid, expiry_settlements):
    """Cash settlement needs no exit quote, so no session can be dropped for moving."""
    settled = B7.c6_expiry_iron_fly_settled(grid, expiry_settlements)
    assert len(settled) > 300
    assert len(settled) >= len(expiry_settlements) - 5, \
        "settlement-based exit must price essentially every expiry session"

    quoted = B7.c6_expiry_iron_fly(grid, sorted(expiry_settlements))
    assert len(settled) > len(quoted) * 1.3, "the correction must recover the dropped sessions"


def test_settled_version_reaches_realistic_losses(grid, expiry_settlements):
    """
    A short straddle must sometimes lose big.

    The artefact's worst trade was 30% of the structural max loss over 218 expiry
    days, which is not plausible. The corrected version must show real tail losses.
    """
    settled = B7.c6_expiry_iron_fly_settled(grid, expiry_settlements)
    worst = min(t.net_pnl for t in settled)
    max_loss_rupees = 4 * 50.0 * B7.LOT          # wing width x lot
    assert worst < -0.5 * max_loss_rupees, (
        f"worst loss {worst:.0f} is implausibly small against a structural maximum "
        f"of {max_loss_rupees:.0f}"
    )
    for t in settled:
        assert t.net_pnl >= -(max_loss_rupees + t.costs) - 0.01, \
            "a defined-risk structure cannot lose more than its width"


# ════════════════ CANDIDATE MECHANICS ════════════════

def test_candidates_hold_one_fixed_contract(grid, daily):
    """No candidate may let the rolling-ATM label swap its contract mid-trade."""
    for trades in (B7.c1_overnight_gap(daily, grid),
                   B7.c2_nr_breakout(daily, grid, n=7)):
        assert trades
        for t in trades[:40]:
            side = "ce" if t.option_type == "CE" else "pe"
            g = grid[side]
            leg = g[(g["strike"] == t.strike)
                    & (g["datetime"].dt.date == pd.Timestamp(t.date).date())]
            prices = set(leg["close"].round(4))
            assert round(t.entry_price, 4) in prices
            assert round(t.exit_price, 4) in prices


def test_c1_threshold_uses_only_prior_sessions(daily, grid):
    """
    The gap threshold is a TRAILING percentile.

    Mutating sessions after a trade must not change whether that trade was taken.
    """
    base = B7.c1_overnight_gap(daily, grid)
    assert len(base) > 50
    cut = pd.Timestamp(base[20].date)
    m = daily.copy()
    mask = m["datetime"] > cut
    for c in ("open", "high", "low", "close"):
        m.loc[mask, c] = m.loc[mask, c] * 1.4
    after = B7.c1_overnight_gap(m, grid)
    assert [t.date for t in base[:20]] == [t.date for t in after[:20]], \
        "a later session changed an earlier entry decision — lookahead"


def test_c2_takes_only_the_first_break_of_a_session(daily, grid):
    trades = B7.c2_nr_breakout(daily, grid, n=7)
    per_day = pd.Series([t.date for t in trades]).value_counts()
    assert per_day.max() == 1, "only the first break of a session may be traded"


def test_c4_entry_is_after_the_opening_range_closes(daily, grid):
    trades = B7.c4_opening_range(daily, grid, minutes=30)
    assert trades
    for t in trades:
        assert t.entry_time >= "09:45:00", "entry must follow the observation window"


def test_every_trade_declares_its_execution_basis(daily, grid):
    for t in B7.c1_overnight_gap(daily, grid)[:30]:
        assert "NO_BIDASK" in t.execution_basis


def test_costs_are_charged_on_every_trade(daily, grid):
    for t in B7.c1_overnight_gap(daily, grid)[:50]:
        assert t.costs > 0
        assert t.net_pnl == pytest.approx(t.gross_pnl - t.costs, abs=0.02)


# ════════════════ LEDGER DISCIPLINE ════════════════

def test_no_candidate_was_recorded_as_surviving():
    """
    The ledger's conclusion must match the code's verdicts.

    If a future change makes a candidate survive, this test should fail and force
    the ledger to be updated deliberately rather than silently.
    """
    led = open("reports/BOT7_RESEARCH_LEDGER.md", encoding="utf-8").read()
    assert "NO VALIDATED EDGE" in led
    assert "SURVIVED" not in led.split("## Results")[1].split("### What each result")[0], \
        "the results table claims a survivor; the ledger conclusion must be revisited"


def test_failed_candidates_are_retained_in_the_ledger():
    led = open("reports/BOT7_RESEARCH_LEDGER.md", encoding="utf-8").read()
    for c in ("C1", "C2", "C3", "C4", "C5", "C6"):
        assert c in led, f"{c} must remain on the record"
    assert "ARTEFACT" in led, "the C6 artefact must stay documented"


def test_multiple_testing_denominator_counts_perturbations():
    """Perturbations are tests too and must not be excluded from the haircut."""
    few = V.deflated_expectation(1, 2.5, 200)
    many = V.deflated_expectation(8, 2.5, 200)
    assert many["p_bonferroni"] > few["p_bonferroni"]
    assert many["variants_examined"] == 8


# ════════════════ LIVE-PATH CRASH REGRESSION (found by the suite) ════════════════

def test_missing_protective_level_fails_closed_instead_of_crashing():
    """
    A position without target_premium must NOT raise inside the monitoring loop.

    The bug: `t5["target_premium"]` was read directly, so a position restored from
    an older state file raised KeyError — which aborts evaluation for EVERY bot in
    that cycle, not just the one holding it. Failing closed leaves the position
    open, visible and still subject to EOD square-off.
    """
    from src.execution.live_paper_session import protective_level

    logged = []
    trade = {"contract": "NIFTY 23250 CE", "entry_premium": 136.5}
    assert protective_level(trade, "target_premium", "BOT 5", logged.append) is None
    assert protective_level(trade, "stop_premium", "BOT 5", logged.append) is None
    assert len(logged) == 2 and all("UNAVAILABLE" in m for m in logged), \
        "a missing level must be recorded, not silently swallowed"

    # A present level is returned unchanged, so behaviour is identical when set.
    assert protective_level({"target_premium": 177.45}, "target_premium", "BOT 5") == 177.45
    # Non-numeric and non-positive values are refused rather than coerced.
    assert protective_level({"target_premium": "abc"}, "target_premium", "B") is None
    assert protective_level({"target_premium": 0.0}, "target_premium", "B") is None
    assert protective_level({"target_premium": -5.0}, "target_premium", "B") is None


def test_no_bot_reads_a_protective_level_unguarded():
    """Structural proof that the direct-subscript pattern is gone from all four bots."""
    src = open("src/execution/live_paper_session.py", encoding="utf-8").read()
    for var in ("t3", "t4", "t5", "t6"):
        for key in ("target_premium", "stop_premium"):
            assert f'{var}["{key}"]' not in src, \
                f'{var}["{key}"] is read unguarded; it must go through protective_level()'

"""
Tests for the authentic index-option lot size.

Every rupee figure in this repository is proportional to this number, so these tests pin the
specific mistakes actually made while getting it right — five of them — rather than merely
exercising the happy path.
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.research.futures_panel import derived_lot
from src.research.option_lots import (
    MIN_LIQUID_ROWS, implied_option_lot, lot_map, pair_lot_table, session_lot_table,
    validate_against_chain_panel, validate_estimator,
)

PAIRS = "data/derived/option_lot_pairs.parquet"
needs_store = pytest.mark.skipif(not os.path.exists(PAIRS),
                                 reason="needs the built lot tables")


def _rows(lot=50, strike=20000.0, premium=105.0, contracts=5000, n=30,
          vary_strike=True, sess="2023-06-15", xp="2023-06-22", official=None,
          bias=1.0):
    """
    Option rows whose value column is the NOTIONAL, as the exchange publishes it.

    `bias` multiplies the value to imitate the real upward bias: the notional accrues against
    the traded underlying, not the strike, so a row implies lot x (underlying/strike) and is
    never below the true lot.
    """
    ks = [strike + (50 * i if vary_strike else 0) for i in range(n)]
    d = pd.DataFrame({
        "TradDt": pd.to_datetime([sess] * n),
        "XpryDt": pd.to_datetime([xp] * n),
        "TckrSymb": ["NIFTY"] * n,
        "StrkPric": ks,
        "OptnTp": ["CE" if i % 2 else "PE" for i in range(n)],
        "ClsPric": [premium] * n,
        "LegacyContracts": [contracts] * n,
        "LegacyValInLakh": [k * contracts * lot * bias / 1e5 for k in ks],
    })
    if official is not None:
        d["NewBrdLotQty"] = official
    return d


def _write(tmp_path, d, stamp="20230615"):
    f = tmp_path / f"idxopt_{stamp}.parquet"
    d.to_parquet(f, index=False)
    return str(f)


# ═══════════════ the identity: strike, never premium ═══════════════

@pytest.mark.parametrize("lot", [25, 50, 65, 75])
def test_the_strike_identity_recovers_each_real_lot(lot):
    d = _rows(lot=lot)
    imp = implied_option_lot(d["LegacyValInLakh"] * 1e5, d["LegacyContracts"],
                             d["StrkPric"])
    assert np.allclose(imp.to_numpy(), float(lot))


def test_dividing_by_the_premium_is_wrong_by_strike_over_premium():
    """
    Measured on the real store, the premium divisor misses the published lot by a median
    factor of 236. Pinned so the strike is never "simplified" back to the close price.
    """
    strike, premium, lot = 20000.0, 105.0, 50
    d = _rows(lot=lot, strike=strike, premium=premium, vary_strike=False)
    right = float(implied_option_lot(d["LegacyValInLakh"] * 1e5,
                                     d["LegacyContracts"], d["StrkPric"]).median())
    wrong = float((d["LegacyValInLakh"] * 1e5
                   / (d["ClsPric"] * d["LegacyContracts"])).median())
    assert round(right) == lot
    assert wrong / right == pytest.approx(strike / premium, rel=1e-6)
    assert wrong > 150 * right, "the error must be enormous, not subtle"


def test_unusable_inputs_give_nan_not_a_fallback():
    imp = implied_option_lot(pd.Series([1e9, 1e9, 1e9, np.nan]),
                             pd.Series([0, 5000, 5000, 5000]),
                             pd.Series([20000.0, 0.0, np.nan, 20000.0]))
    assert imp.isna().all(), "zero contracts, zero strike, NaN strike, NaN value"


# ═══════════════ derived_lot is for futures and must refuse options ═══════════════

def test_derived_lot_refuses_an_option_row():
    assert np.isnan(derived_lot(_rows().iloc[0]))


def test_derived_lot_still_answers_for_a_futures_row():
    fut = pd.Series({"TradDt": pd.Timestamp("2023-06-15"), "TckrSymb": "NIFTY",
                     "StrkPric": 0.0, "OptnTp": None, "ClsPric": 19500.0,
                     "LegacyContracts": 4000, "NewBrdLotQty": np.nan,
                     "LegacyValInLakh": 19500.0 * 4000 * 50 / 1e5,
                     "TtlTrfVal": np.nan, "TtlTradgVol": np.nan})
    assert round(derived_lot(fut)) == 50


# ═══════════════ the published column wins over any estimate ═══════════════

def test_the_published_lot_is_used_verbatim_even_when_the_estimate_differs(tmp_path):
    """
    `NewBrdLotQty` is the exchange's own figure. Where it exists nothing is estimated —
    including when a biased turnover would have implied something else.
    """
    d = _rows(lot=50, official=50, bias=1.02)      # turnover implies ~51
    p = pair_lot_table("NIFTY", files=[_write(tmp_path, d)], use_cache=False)
    assert len(p) == 1
    assert int(p["lot"].iloc[0]) == 50
    assert p["source"].iloc[0] == "NewBrdLotQty"
    assert p["implied_min"].iloc[0] > 50.5, "the biased estimate existed and was ignored"


# ═══════════════ the minimum, because the bias is one-sided ═══════════════

def test_the_minimum_is_taken_because_the_bias_is_strictly_positive(tmp_path):
    """
    Measured on 5,918 liquid rows, implied/published lies in [1.0004, 1.0210] and is never
    below 1. So the minimum is the least-biased row; a median sits inside the bias
    distribution. Validated at 100.00% vs 91.63% on the same 2,998 pairs.
    """
    d = _rows(lot=50, n=30)
    d.loc[1:, "LegacyValInLakh"] = d.loc[1:, "LegacyValInLakh"] * 1.018
    p = pair_lot_table("NIFTY", files=[_write(tmp_path, d)], use_cache=False)
    assert int(p["lot"].iloc[0]) == 50
    assert p["source"].iloc[0] == "derived-min"
    med = float((d["LegacyValInLakh"] * 1e5
                 / (d["StrkPric"] * d["LegacyContracts"])).median())
    assert round(med) == 51, "a median would have produced 51 — the failure being avoided"


def test_too_few_liquid_rows_is_unpriceable_not_estimated(tmp_path):
    """The minimum only approaches the floor with enough samples, so refuse below it."""
    d = _rows(lot=50, n=MIN_LIQUID_ROWS - 1)
    assert pair_lot_table("NIFTY", files=[_write(tmp_path, d)], use_cache=False).empty


def test_illiquid_rows_are_excluded_before_the_minimum_is_taken(tmp_path):
    d = _rows(lot=50, n=30, contracts=10)
    assert pair_lot_table("NIFTY", files=[_write(tmp_path, d)], use_cache=False).empty


def test_an_unrelated_symbol_does_not_leak_in(tmp_path):
    d = _rows(lot=50)
    d["TckrSymb"] = "BANKNIFTY"
    assert pair_lot_table("NIFTY", files=[_write(tmp_path, d)], use_cache=False).empty


# ═══════════════ two lots trade on the same day during a transition ═══════════════

def test_a_transition_session_takes_the_near_expiry_not_a_blend(tmp_path):
    """
    On 2025-12-24 the contracts expiring 2025-12-30 implied 75.01 and those expiring
    2026-01-06 implied 65.05. A session-wide median blends them into 66.6, which is not a lot
    size at all. The near expiry is the contract an intraday trade touches.
    """
    near = _rows(lot=75, strike=26000.0, sess="2025-12-24", xp="2025-12-30")
    far = _rows(lot=65, strike=26000.0, sess="2025-12-24", xp="2026-01-06")
    f = _write(tmp_path, pd.concat([near, far], ignore_index=True), "20251224")
    s = session_lot_table("NIFTY", files=[f], use_cache=False)
    assert len(s) == 1
    assert int(s["lot"].iloc[0]) == 75, "near expiry wins"
    assert int(s["n_expiries"].iloc[0]) == 2, "both expiries were seen"
    assert int(s["lot"].iloc[0]) != 70, "and it is not the midpoint of the two"


def test_both_expiries_keep_their_own_lot_in_the_pair_table(tmp_path):
    near = _rows(lot=75, strike=26000.0, sess="2025-12-24", xp="2025-12-30")
    far = _rows(lot=65, strike=26000.0, sess="2025-12-24", xp="2026-01-06")
    f = _write(tmp_path, pd.concat([near, far], ignore_index=True), "20251224")
    p = pair_lot_table("NIFTY", files=[f], use_cache=False).sort_values("expiry")
    assert list(p["lot"]) == [75, 65], "the lot is per (session, expiry), not per session"


def test_a_missing_session_is_absent_rather_than_carried_forward(tmp_path):
    files = [_write(tmp_path, _rows(lot=50, sess=d, xp="2023-06-29"), s)
             for d, s in (("2023-06-12", "20230612"), ("2023-06-19", "20230619"))]
    m = lot_map("NIFTY", files=files, use_cache=False)
    assert set(m) == {pd.Timestamp("2023-06-12").date(),
                      pd.Timestamp("2023-06-19").date()}
    assert pd.Timestamp("2023-06-15").date() not in m, "the gap must not be filled"


# ═══════════════ against the real store ═══════════════

@needs_store
def test_the_estimator_is_exact_against_the_published_lot_where_it_has_enough_rows():
    """
    The whole basis for trusting the 2019-2023 figures, where no published lot exists. If
    this ever drops below 100% the legacy numbers must not be used.
    """
    v = validate_estimator("NIFTY")
    e = v[v["enough_rows"]]
    assert len(e) >= 2000, f"expected a large validation set, got {len(e)}"
    assert e["agrees"].all(), (
        f"{(~e['agrees']).sum()} of {len(e)} pairs disagree:\n"
        f"{e[~e['agrees']].head(10).to_string()}")


@needs_store
def test_the_estimator_beats_ninety_percent_even_unrestricted():
    v = validate_estimator("NIFTY")
    assert 100 * v["agrees"].mean() > 90


@needs_store
def test_every_session_agrees_with_chain_panel():
    c = validate_against_chain_panel("NIFTY")
    assert len(c) >= 600, f"expected a broad overlap, got {len(c)}"
    bad = c[~c["agrees"]]
    assert bad.empty, f"disagreement on {len(bad)} sessions:\n{bad.head(10).to_string()}"


@needs_store
def test_the_legacy_era_produces_only_lot_sizes_that_actually_existed():
    """
    Earlier estimators emitted 26, 51, 52, 54, 66, 67, 76, 77, 81, 93, 104 and 107 — all bias
    artefacts. The legacy era had exactly two NIFTY lots.
    """
    p = pair_lot_table("NIFTY")
    legacy = p[p["source"] == "derived-min"]
    assert len(legacy) > 3000, f"expected broad legacy coverage, got {len(legacy)}"
    assert set(legacy["lot"].unique()) == {50, 75}, \
        f"unexpected derived lots: {sorted(set(legacy['lot'].unique()))}"


@needs_store
def test_the_derived_values_sit_essentially_on_the_integer():
    p = pair_lot_table("NIFTY")
    legacy = p[p["source"] == "derived-min"].copy()
    legacy["frac"] = (legacy["implied_min"] - legacy["lot"]).abs()
    assert legacy["frac"].max() < 0.5, f"worst {legacy['frac'].max():.4f}"
    assert legacy["frac"].median() < 0.02, f"median {legacy['frac'].median():.4f}"


@needs_store
def test_the_real_lot_changes_land_on_the_right_sessions():
    m = lot_map("NIFTY")

    def lot(d):
        return m.get(pd.Timestamp(d).date())

    assert lot("2021-07-22") == 75 and lot("2021-07-23") == 50
    assert lot("2024-04-25") == 50 and lot("2024-04-26") == 25, "mid-April, not 1 May"
    assert lot("2024-12-26") == 25 and lot("2024-12-27") == 75, "mid-December"
    assert lot("2025-01-24") == 25, "the near contract kept the old lot for a week"
    assert lot("2025-01-31") == 75
    assert lot("2025-12-30") == 75 and lot("2025-12-31") == 65


@needs_store
def test_the_dev_window_has_an_authentic_lot_for_every_session():
    """2022-2023 is the DEV window; chain_panel has nothing there, so this is the cover."""
    m = lot_map("NIFTY")
    days = [d for d in m if pd.Timestamp("2022-01-01").date() <= d
            <= pd.Timestamp("2023-12-31").date()]
    assert len(days) > 450, f"expected ~490 sessions, got {len(days)}"
    assert {m[d] for d in days} == {50}, "the NIFTY lot was 50 throughout 2022-2023"

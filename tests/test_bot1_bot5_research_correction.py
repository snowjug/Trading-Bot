"""
Research-correction tests for Bot 1 and Bot 5.

BOT 1 — proves the strategy is NOT a four-leg Iron Condor in its active research
path, and that the historical option data required to build one does not exist.
These tests document the STOP; they do not implement a condor.

BOT 5 — proves the original signal has same-bar leakage and that the corrected
point-in-time signal does not, while remaining free of future-bar leakage.
"""
import glob
from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.research.bot5_point_in_time import (
    LEAKED_FIELDS,
    generate_signals_point_in_time,
    run_point_in_time_simulation,
    summarise,
)
from src.strategies.active_momentum_scalper import ActiveMomentumOptionScalperStrategy
from src.strategies.options_theta import NiftyWeeklyIronCondorStrategy


def _nifty():
    df = pd.read_csv("data/real_2026/INDEX_NIFTY50_daily.csv")
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df


# ════════════════════════ BOT 1 — STRUCTURE & DATA ════════════════════════

def test_bot1_active_research_path_has_no_long_wings():
    """
    The strategy's own simulator builds TWO strikes, not four.

    Research is a short strangle, not an Iron Condor.
    """
    src = open("src/strategies/options_theta.py", encoding="utf-8").read()
    sim = src[src.index("def simulate_weekly_condors"):]

    assert "call_k" in sim and "put_k" in sim, "short strikes must exist"
    for wing in ("long_call", "long_put", "wing_sd"):
        assert wing not in sim, f"unexpected wing reference {wing!r} in the active path"


def test_bot1_wing_sd_is_declared_but_unused_by_the_strategy():
    """wing_sd is a constructor parameter that the strategy never consumes."""
    strategy = NiftyWeeklyIronCondorStrategy()
    assert strategy.wing_sd == 2.4                      # declared
    src = open("src/strategies/options_theta.py", encoding="utf-8").read()
    # get_parameters() legitimately REPORTS wing_sd; the point is that no
    # signal-generation or simulation code ever CONSUMES it.
    signal_body = src[src.index("def generate_signals"):src.index("def get_parameters")]
    sim_body = src[src.index("def simulate_weekly_condors"):]
    assert "wing_sd" not in signal_body, "wing_sd must not be used in signal generation"
    assert "wing_sd" not in sim_body, "wing_sd must not be used in the simulator"


def test_bot1_four_leg_engine_exists_but_is_orphaned():
    """
    A genuine four-leg Black-Scholes condor exists in OptionsStructure, but the
    strategy never calls it. Recording this prevents the earlier mistaken claim
    that the wings were never implemented at all.
    """
    from src.deriv.options_engine import OptionsStructure

    assert hasattr(OptionsStructure, "simulate_iron_condor")
    theta_src = open("src/strategies/options_theta.py", encoding="utf-8").read()
    assert theta_src.count("OptionsStructure") == 1, "should appear only as an unused import"
    assert "OptionsStructure.simulate_iron_condor" not in theta_src


def test_bot1_pnl_is_a_fixed_credit_not_option_pricing():
    """P&L is independent of any option price."""
    src = open("src/strategies/options_theta.py", encoding="utf-8").read()
    sim = src[src.index("def simulate_weekly_condors"):]
    assert "credit_per_lot = 2500.0" in sim, "fixed credit constant expected"
    assert "margin_per_lot = 55000.0" in sim, "fabricated margin constant expected"
    for real_pricing in ("price_call", "price_put", "bid", "ask"):
        assert real_pricing not in sim, f"unexpected real pricing {real_pricing!r}"


def test_bot1_has_no_exit_specification():
    """No stop, target, adjustment, roll or EOD rule is specified anywhere."""
    src = open("src/strategies/options_theta.py", encoding="utf-8").read().lower()
    for token in ("stop", "target", "adjust", "roll", "square", "eod"):
        assert token not in src, f"unexpected exit token {token!r}; spec may have changed"


def test_bot1_simulator_is_never_invoked_in_the_repository():
    """The options backtest is dead code — no reported result can come from it."""
    hits = []
    for path in glob.glob("**/*.py", recursive=True):
        if "__pycache__" in path or path.endswith("options_theta.py"):
            continue
        if path.startswith("tests"):
            continue
        if "simulate_weekly_condors" in open(path, encoding="utf-8", errors="ignore").read():
            hits.append(path)
    assert hits == [], f"simulate_weekly_condors unexpectedly called by {hits}"


def test_bot1_historical_option_chain_is_insufficient():
    """
    A weekly condor needs ~40+ cycles x 4 strikes at entry and exit. The repo has
    4 full-chain days and near-ATM intraday only, so the backtest cannot be run.
    """
    bhav = glob.glob("data/real_2026/bhavcopies/NIFTY_options_*.csv")
    chains = glob.glob("data/normalized/options/date=*")
    rolling = glob.glob("data/raw/dhan/rollingoption/**/*.parquet", recursive=True)

    assert len(bhav) < 40, "if this now exceeds 40 days, re-open the Bot 1 assessment"
    assert len(chains) < 40, "chain snapshots still insufficient for a weekly backtest"

    strikes = {p.replace("\\", "/").split("strike=")[1].split("/")[0] for p in rolling}
    assert strikes <= {"ATM", "ATMM1", "ATMM2", "ATMM3", "ATMP1", "ATMP2", "ATMP3"}, \
        "rolling option coverage changed; re-assess whether far-OTM wings are now available"


# ════════════════════════ BOT 5 — CAUSALITY ════════════════════════

def _mutate_close_within_existing_range(df, idx):
    """
    Moves bar `idx`'s CLOSE to the opposite end of its OWN high/low range,
    leaving open, high and low untouched.

    This isolates the close exactly: the bar's observable intraday extremes are
    unchanged, so the breakout trigger cannot move. Any signal change at index
    `idx` therefore proves the bar's CLOSE leaked into a decision that is taken
    while the bar is still forming.
    """
    out = df.copy()
    hi, lo, close = out.loc[idx, "high"], out.loc[idx, "low"], out.loc[idx, "close"]
    # Flip the close to the far end of the same range (no new extremes created).
    out.loc[idx, "close"] = lo if (close - lo) > (hi - close) else hi
    return out


def test_bot5_original_signal_has_same_bar_leakage():
    """
    Documents the defect: changing bar i's CLOSE changes bar i's own signal,
    which is impossible for a decision taken during bar i.
    """
    df = _nifty()
    strategy = ActiveMomentumOptionScalperStrategy()
    base = strategy.generate_signals(df)

    changed = 0
    for idx in range(30, len(df)):
        mutated = strategy.generate_signals(_mutate_close_within_existing_range(df, idx))
        if int(base.iloc[idx]["signal"]) != int(mutated.iloc[idx]["signal"]):
            changed += 1
    # Measured on the real NIFTY series: 17 of 393 bars (4.3%) flip their own
    # signal purely from that bar's close. A one-bar perturbation moves a 20-span
    # EWM and a 14-period RSI only slightly, so the rate is low but non-zero —
    # and non-zero is disqualifying for a decision taken during the bar.
    assert changed > 0, "expected same-bar leakage in the ORIGINAL implementation"


def test_bot5_point_in_time_signal_has_no_same_bar_close_leakage():
    """The corrected signal must be invariant to bar i's close."""
    df = _nifty()
    strategy = ActiveMomentumOptionScalperStrategy()
    base = generate_signals_point_in_time(strategy, df)

    for idx in range(30, len(df)):
        mutated = generate_signals_point_in_time(strategy, _mutate_close_within_existing_range(df, idx))
        assert int(base.iloc[idx]["signal"]) == int(mutated.iloc[idx]["signal"]), \
            f"same-bar close leaked into the point-in-time signal at index {idx}"


def test_bot5_point_in_time_signal_has_no_future_bar_leakage():
    """Mutating every FUTURE bar must not change any past or present signal."""
    df = _nifty()
    strategy = ActiveMomentumOptionScalperStrategy()
    base = generate_signals_point_in_time(strategy, df)

    cutoff = 300
    mutated_df = df.copy()
    rng = np.random.default_rng(7)
    factor = rng.uniform(0.5, 2.5, len(mutated_df) - cutoff - 1)
    for col in ("open", "high", "low", "close"):
        mutated_df.loc[cutoff + 1:, col] = mutated_df.loc[cutoff + 1:, col].values * factor

    mutated = generate_signals_point_in_time(strategy, mutated_df)
    assert (base.iloc[:cutoff + 1]["signal"].values
            == mutated.iloc[:cutoff + 1]["signal"].values).all(), "future-bar leakage detected"


def test_bot5_only_the_three_leaked_fields_moved_to_prev():
    """The correction is scoped: exactly the leaked inputs changed bar."""
    src = open("src/research/bot5_point_in_time.py", encoding="utf-8").read()
    body = src[src.index("def generate_signals_point_in_time"):src.index("def run_point_in_time_simulation")]
    assert 'prev["ema_20"]' in body and 'row["ema_20"]' not in body
    assert 'prev["rsi_14"]' in body and 'row["rsi_14"]' not in body
    # The breakout must remain on the current bar — it is a live crossing event.
    assert 'row["high"] > prev["high"]' in body
    assert 'row["open"]' in body
    assert set(LEAKED_FIELDS) == {"ema_20", "rsi_14", "atr_14"}


def test_bot5_sizing_uses_previous_bar_atr():
    src = open("src/research/bot5_point_in_time.py", encoding="utf-8").read()
    body = src[src.index("def run_point_in_time_simulation"):]
    assert 'atr = prev["atr_14"]' in body, "target/stop must be sized from ATR known at entry"
    assert 'row["atr_14"]' not in body


def test_bot5_parameters_are_untouched():
    """No threshold, buffer, multiple or cost was changed."""
    s = ActiveMomentumOptionScalperStrategy()
    assert s.breakout_buffer == 0.001
    assert s.target_atr_mult == 0.5
    assert s.stop_atr_mult == 0.25
    assert s.friction_per_trade == 45.0
    assert s.min_data_points == 30


def test_bot5_original_implementation_is_preserved():
    """Contaminated evidence must remain reproducible, not overwritten."""
    s = ActiveMomentumOptionScalperStrategy()
    assert hasattr(s, "run_single_simulation") and hasattr(s, "generate_signals")
    trades = s.run_single_simulation(_nifty(), "NIFTY", 50)
    assert len(trades) > 0, "the original (leaky) path must still run for comparison"


def test_bot5_correction_is_deterministic():
    df = _nifty()
    s = ActiveMomentumOptionScalperStrategy()
    a = summarise(run_point_in_time_simulation(s, df, "NIFTY", 50), s.initial_capital)
    b = summarise(run_point_in_time_simulation(s, df, "NIFTY", 50), s.initial_capital)
    assert a == b, "point-in-time simulation must be deterministic"


def test_bot5_pnl_is_labelled_as_a_proxy_not_real_options():
    """The premium/delta proxy is inherited unchanged and must be declared."""
    trades = run_point_in_time_simulation(
        ActiveMomentumOptionScalperStrategy(), _nifty(), "NIFTY", 50)
    assert trades
    assert all(t["pricing_basis"] == "SPOT_DELTA_PROXY_NOT_REAL_OPTION" for t in trades)
    assert all(t["option_entry_prem"] == 100.0 for t in trades), "flat premium proxy unchanged"

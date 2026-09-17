"""
Bots 5 and 6 — real option economics.

Proves the synthetic flat-premium / fixed-delta model has been replaced with
authentic option prices, that the simulation holds ONE tradable contract, and
that the research contract matches what the live path would actually resolve.
"""
import glob
from datetime import date

import pandas as pd
import pytest

from src.research.bot56_real_option_model import (
    EXECUTION_BASIS,
    available_option_days,
    load_option_grid,
    simulate_real_option_trades,
    summarise_real,
)
from src.research.bot5_point_in_time import generate_signals_point_in_time
from src.strategies.active_momentum_scalper import ActiveMomentumOptionScalperStrategy
from src.strategies.micro_momentum_buyer import MicroMomentumBuyerStrategy


def _daily():
    n = pd.read_csv("data/real_2026/INDEX_NIFTY50_daily.csv")
    v = pd.read_csv("data/real_2026/INDEX_INDIAVIX_daily.csv")
    n["datetime"] = pd.to_datetime(n["datetime"])
    v["datetime"] = pd.to_datetime(v["datetime"])
    return n.merge(v[["datetime", "close"]].rename(columns={"close": "vix"}), on="datetime")


@pytest.fixture(scope="module")
def grid():
    g = load_option_grid()
    assert g is not None, "authentic option bars must be present"
    return g


# ─────────────── DATA SEMANTICS: THE ROLLING-ATM TRAP ───────────────

def test_rolling_atm_series_reanchors_intraday():
    """
    The 'ATM' series is NOT one contract: its strike changes during a session.

    This is why the model must not price a held position from it. If this ever
    stops being true, the model's fixed-contract logic can be revisited.
    """
    f = glob.glob("data/raw/dhan/rollingoption/**/NIFTY_ATM_ce_*.parquet", recursive=True)[0]
    df = pd.read_parquet(f)
    df["ist"] = (pd.to_datetime(df["timestamp"], unit="s", utc=True)
                 .dt.tz_convert("Asia/Kolkata").dt.tz_localize(None))
    per_day = df.groupby(df["ist"].dt.date)["strike"].nunique()
    assert per_day.max() > 1, "expected the ATM series to re-anchor within a session"


def test_grid_timestamps_are_ist_session_times():
    """Cached files store a pre-fix UTC-naive datetime; the grid must correct it."""
    g = load_option_grid()
    t = g["ce"]["datetime"]
    assert t.dt.time.min() >= pd.Timestamp("09:15").time(), "bars must start at/after 09:15 IST"
    assert t.dt.time.max() <= pd.Timestamp("15:40").time(), "bars must end within the session"


def test_grid_exposes_authentic_fields(grid):
    for side in ("ce", "pe"):
        for col in ("datetime", "strike", "spot", "close", "iv", "oi"):
            assert col in grid[side].columns
        assert grid[side]["strike"].nunique() > 1, "grid must span multiple strikes"


# ─────────────── FIXED CONTRACT, NOT A SYNTHETIC SERIES ───────────────

def test_trade_holds_a_single_fixed_strike(grid):
    """Every trade must name one strike and hold it from entry to exit."""
    s = ActiveMomentumOptionScalperStrategy()
    d = _daily()
    trades = simulate_real_option_trades(
        d, generate_signals_point_in_time(s, d), grid,
        s.target_atr_mult, s.stop_atr_mult, 65)
    assert trades, "expected trades within the covered window"
    for t in trades:
        assert t.strike > 0 and float(t.strike).is_integer() or t.strike > 0
        # the exit price must come from the SAME strike's series
        side = "ce" if t.option_type == "CE" else "pe"
        leg = grid[side][(grid[side]["strike"] == t.strike)
                         & (grid[side]["datetime"].dt.date == pd.Timestamp(t.date).date())]
        prices = set(leg["close"].round(4))
        assert round(t.entry_option_price, 4) in prices
        assert round(t.exit_option_price, 4) in prices


def test_option_direction_is_coherent(grid):
    """A put must gain when spot falls; a call when spot rises."""
    s = ActiveMomentumOptionScalperStrategy()
    d = _daily()
    trades = simulate_real_option_trades(
        d, generate_signals_point_in_time(s, d), grid,
        s.target_atr_mult, s.stop_atr_mult, 65)
    checked = 0
    for t in trades:
        spot_move = t.exit_spot - t.entry_spot
        opt_move = t.exit_option_price - t.entry_option_price
        if abs(spot_move) < 5:
            continue                                  # too small to be directional
        checked += 1
        if t.option_type == "PE":
            assert not (spot_move < -20 and opt_move < -5), \
                f"PE lost value while spot fell sharply on {t.date}"
        else:
            assert not (spot_move > 20 and opt_move < -5), \
                f"CE lost value while spot rose sharply on {t.date}"
    assert checked > 0, "no directional trades to verify"


# ─────────────── NO FABRICATION ───────────────

def test_model_contains_no_synthetic_premium_or_delta():
    src = open("src/research/bot56_real_option_model.py", encoding="utf-8").read()
    # Scope to the SIMULATION only: summarise_real legitimately uses 100.0 as a
    # percentage multiplier, which is not a pricing artefact.
    body = src[src.index("def simulate_real_option_trades"):src.index("def summarise_real")]
    for banned in ("0.55", "opt_delta", "entry_premium = 100", "* 100.0"):
        assert banned not in body, f"synthetic pricing artefact {banned!r} present"
    # Prices must come from the feed, not a constant.
    assert 'float(chosen["close"])' in body and 'float(exit_row["close"])' in body


def test_every_trade_declares_its_execution_basis(grid):
    s = MicroMomentumBuyerStrategy()
    d = _daily()
    trades = simulate_real_option_trades(
        d, s.generate_signals(d), grid, s.target_atr_mult, s.stop_atr_mult,
        65, s.max_trades_per_day)
    for t in trades:
        assert t.execution_basis == EXECUTION_BASIS
        assert "NO_BIDASK" in t.execution_basis, "the bid/ask gap must be declared"


def test_summary_declares_execution_basis_and_empty_is_explicit():
    empty = summarise_real([])
    assert empty["total_trades"] == 0
    assert "note" in empty, "an empty result must be explicit, not look like a flat strategy"
    assert empty["execution_basis"] == EXECUTION_BASIS


def test_prices_used_are_real_not_constant(grid):
    s = ActiveMomentumOptionScalperStrategy()
    d = _daily()
    trades = simulate_real_option_trades(
        d, generate_signals_point_in_time(s, d), grid,
        s.target_atr_mult, s.stop_atr_mult, 65)
    entries = {round(t.entry_option_price, 2) for t in trades}
    assert len(entries) > 1, "entry premiums must vary; a constant implies the old proxy"
    assert 100.0 not in entries or len(entries) > 2


# ─────────────── SAMPLE-SIZE HONESTY ───────────────

def test_covered_window_is_too_small_for_validation(grid):
    """
    Guard against anyone reading this as a validated result.

    If coverage later grows beyond ~60 sessions this test should be revisited
    together with a real walk-forward.
    """
    days = available_option_days(grid)
    assert len(days) < 60, (
        "option coverage has grown; re-run proper validation instead of relying "
        "on the demonstration window"
    )


# ─────────────── RESEARCH == LIVE CONTRACT PARITY ───────────────

def test_research_contract_matches_live_resolution():
    """ATM NIFTY weekly: the live path must resolve the same contract shape."""
    from src.execution.dhan_scrip_master import DhanScripMaster

    DhanScripMaster.sync_master()
    atm = round(23270.6 / 50.0) * 50.0
    c = DhanScripMaster.resolve_contract(underlying="NIFTY", option_type="CE", target_strike=atm)

    assert c is not None
    assert c["underlying"] == "NIFTY"
    assert c["option_type"] == "CE"
    assert c["strike"] == atm, "live must resolve the same ATM strike the research used"
    assert c["lot_size"] == 65, "lot size must match the research model"
    assert c["security_id"].isdigit(), "security id must be authentic and numeric"
    assert c["exchange_segment"] == "NSE_FNO"


def test_both_bots_trade_atm_in_the_live_path():
    """Research assumes ATM; the live path must not silently use an offset."""
    src = open("src/execution/live_paper_session.py", encoding="utf-8").read()
    bot6 = src[src.index("BOT 6: MICRO MOMENTUM SNIPER"):]
    assert "strike_offset_steps=0" in bot6, "Bot 6 must resolve ATM"
    # Bot 5 relies on the resolver default, which is ATM.
    from src.execution.dhan_contract_resolver import DhanContractResolver
    import inspect
    sig = inspect.signature(DhanContractResolver.resolve_option_contract)
    assert sig.parameters["strike_offset_steps"].default == 0, "resolver default must be ATM"

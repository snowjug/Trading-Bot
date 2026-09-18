"""
Bots 5 and 6 on the DEEP 5-minute option grid.

The earlier "real option economics" rested on a 10-session cache, which was a
caching artefact rather than a data limit: with a valid token the same endpoint
serves ~6 years. These tests pin the properties that make the larger result
trustworthy — authentic per-strike prices, one fixed contract per trade, coherent
option direction — and the properties that stop it being over-read.
"""
import pandas as pd
import pytest

from src.research import validation as V
from src.research.bot5_point_in_time import generate_signals_point_in_time
from src.research.bot56_real_option_model import (
    EXECUTION_BASIS,
    available_option_days,
    load_option_grid_5m,
    simulate_real_option_trades,
)
from src.strategies.active_momentum_scalper import ActiveMomentumOptionScalperStrategy
from src.strategies.micro_momentum_buyer import MicroMomentumBuyerStrategy


@pytest.fixture(scope="module")
def grid():
    g = load_option_grid_5m()
    if g is None:
        pytest.skip("deep grid not ingested; run scripts/ingest_dhan_option_grid.py")
    return g


@pytest.fixture(scope="module")
def daily():
    p = "data/raw/nse/index_history/nse_index_daily.parquet"
    raw = pd.read_parquet(p)
    n = raw[raw["symbol"] == "NIFTY50"][["datetime", "open", "high", "low", "close"]]
    v = raw[raw["symbol"] == "INDIAVIX"][["datetime", "close"]].rename(columns={"close": "vix"})
    d = n.merge(v, on="datetime", how="inner").sort_values("datetime").reset_index(drop=True)
    d["volume"] = 0.0
    return d


@pytest.fixture(scope="module")
def bot5_trades(grid, daily):
    s = ActiveMomentumOptionScalperStrategy()
    return simulate_real_option_trades(
        daily, generate_signals_point_in_time(s, daily), grid,
        s.target_atr_mult, s.stop_atr_mult, 65)


# ════════════════════ COVERAGE ════════════════════

def test_deep_grid_supersedes_the_ten_session_cache(grid):
    """The whole point of the re-probe: coverage is years, not days."""
    days = available_option_days(grid)
    assert len(days) > 1000, f"expected years of sessions, got {len(days)}"
    assert (days[-1] - days[0]).days > 5 * 365, "expected a multi-year span"


def test_grid_spans_a_real_strike_ladder(grid):
    """Stitching the ATM+/-N ladder must yield many REAL strikes, not one label."""
    for side in ("ce", "pe"):
        assert grid[side]["strike"].nunique() > 100
        for col in ("datetime", "strike", "spot", "close", "high", "low", "iv", "oi"):
            assert col in grid[side].columns


def test_grid_timestamps_are_regular_session_times(grid):
    """
    Bars must sit inside the REGULAR session.

    This caught a real defect: the feed also carries Muhurat (Diwali) trading —
    four evening-only sessions running 18:00-19:15 with no regular-session bars.
    Left in, they would be traded as if 18:15 were the open.
    """
    for side in ("ce", "pe"):
        t = grid[side]["datetime"].dt.time
        assert t.min() >= pd.Timestamp("09:15").time()
        assert t.max() <= pd.Timestamp("15:35").time(),             "evening/Muhurat bars must not reach the simulator"


def test_muhurat_sessions_are_excluded(grid):
    """The four known ceremonial sessions must not appear at all."""
    muhurat = {pd.Timestamp(d).date() for d in
               ("2021-11-04", "2022-10-24", "2023-11-12", "2024-11-01")}
    for side in ("ce", "pe"):
        present = set(grid[side]["datetime"].dt.date) & muhurat
        assert not present, f"{side}: Muhurat sessions leaked in: {sorted(present)}"


def test_grid_has_no_duplicate_contract_bars(grid):
    for side in ("ce", "pe"):
        g = grid[side]
        assert not g.duplicated(subset=["datetime", "strike"]).any()


def test_grid_prices_are_positive_and_ordered(grid):
    for side in ("ce", "pe"):
        g = grid[side].sample(min(20000, len(grid[side])), random_state=0)
        assert (g["close"] > 0).all(), "a zero or negative option price is not a price"
        assert (g["high"] >= g["low"]).all()
        assert (g["spot"] > 1000).all(), "spot must be an index level"


# ════════════════════ TRADE MECHANICS ════════════════════

def test_trades_hold_one_fixed_contract(bot5_trades, grid):
    """A held position must not silently swap strike — the rolling-ATM trap."""
    assert len(bot5_trades) > 100, "expected a large trade sample on the deep grid"
    for t in bot5_trades[:60]:
        side = "ce" if t.option_type == "CE" else "pe"
        g = grid[side]
        leg = g[(g["strike"] == t.strike) & (g["datetime"].dt.date == pd.Timestamp(t.date).date())]
        prices = set(leg["close"].round(4))
        assert round(t.entry_option_price, 4) in prices, "entry price is not from this strike"
        assert round(t.exit_option_price, 4) in prices, "exit price is not from this strike"


def test_entry_precedes_exit(bot5_trades):
    for t in bot5_trades:
        assert t.entry_time <= t.exit_time, f"{t.date}: exit precedes entry"


def test_option_direction_is_coherent_at_scale(bot5_trades):
    """
    Calls must rise with spot and puts fall with it, measured across the whole
    sample rather than on a handful of trades.
    """
    df = pd.DataFrame([t.__dict__ for t in bot5_trades])
    df["spot_move"] = df["exit_spot"] - df["entry_spot"]
    df["opt_move"] = df["exit_option_price"] - df["entry_option_price"]
    ce = df[df["option_type"] == "CE"]
    pe = df[df["option_type"] == "PE"]
    assert len(ce) > 30 and len(pe) > 30
    assert ce["spot_move"].corr(ce["opt_move"]) > 0.6, "calls must track spot upward"
    assert pe["spot_move"].corr(pe["opt_move"]) < -0.6, "puts must move against spot"


def test_every_trade_declares_its_execution_basis(bot5_trades):
    for t in bot5_trades:
        assert t.execution_basis == EXECUTION_BASIS
        assert "NO_BIDASK" in t.execution_basis


def test_entry_premium_is_not_the_old_flat_constant(bot5_trades):
    """The synthetic model used a flat 100.0 premium; real prices must vary."""
    prices = [t.entry_option_price for t in bot5_trades]
    assert len(set(round(p, 2) for p in prices)) > 50
    assert pd.Series(prices).std() > 10.0


def test_bot6_remains_frozen_and_capped(grid, daily):
    """Bot 6 is a protected baseline: its own signal, its own per-day cap."""
    s = MicroMomentumBuyerStrategy()
    assert s.max_vix == 18.5 and s.min_data_points == 35
    trades = simulate_real_option_trades(
        daily, s.generate_signals(daily), grid,
        s.target_atr_mult, s.stop_atr_mult, 65, s.max_trades_per_day)
    per_day = pd.Series([t.date for t in trades]).value_counts()
    assert per_day.max() <= s.max_trades_per_day


# ════════════════════ VERDICT SEMANTICS ════════════════════

def test_a_losing_sample_is_called_losing_not_inconclusive():
    """
    A demonstrably negative strategy must not hide behind "not distinguishable".

    This is the Bot 5 case: break-even 0.496 with an observed adverse rate whose
    95% LOWER bound is 0.591.
    """
    v = V.sample_size_verdict(589, 372, 0.4958)
    assert v["verdict"] == "CONCLUSIVELY_ADVERSE"
    assert v["adverse_ci95"][0] > 0.4958

    # An inconclusive sample keeps the inconclusive label.
    assert V.sample_size_verdict(44, 1, 0.0451)["verdict"] == "NOT_DISTINGUISHABLE"
    # And a genuinely favourable one is still recognised.
    assert V.sample_size_verdict(5000, 0, 0.0476)["verdict"] == "EDGE_DISTINGUISHABLE"

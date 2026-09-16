"""Unit tests for Derivatives Engine, Options Pricing, Futures Margin, and F&O Alpha Strategies."""

import pytest
import numpy as np
import pandas as pd

from src.deriv.options_engine import BlackScholesEngine, OptionsStructure, Greeks, IronCondorResult
from src.deriv.futures_engine import FuturesMarginEngine, FuturesTradeResult
from src.strategies.options_theta import NiftyWeeklyIronCondorStrategy
from src.strategies.futures_momentum import BankNiftyTrendFuturesStrategy
from src.strategies.index_reversion import IndexDipSniperStrategy
from src.strategies.master_derivatives_portfolio import MasterDerivativesAlphaPortfolio


def test_black_scholes_call_put_parity():
    """Verify Put-Call Parity: C - P = S - K * exp(-r * T)."""
    spot = 20000.0
    strike = 20000.0
    t_years = 30.0 / 365.0
    vol = 0.15
    r = 0.065

    call_price = BlackScholesEngine.price_call(spot, strike, t_years, vol, r)
    put_price = BlackScholesEngine.price_put(spot, strike, t_years, vol, r)

    synthetic_diff = call_price - put_price
    expected_diff = spot - (strike * np.exp(-r * t_years))

    assert call_price > 0
    assert put_price > 0
    assert abs(synthetic_diff - expected_diff) < 1e-4


def test_black_scholes_greeks():
    """Verify Delta, Gamma, Theta, Vega properties."""
    spot = 22000.0
    strike = 22000.0
    t_years = 14.0 / 365.0
    vol = 0.16
    r = 0.065

    call_greeks = BlackScholesEngine.compute_greeks(spot, strike, t_years, vol, r, is_call=True)
    put_greeks = BlackScholesEngine.compute_greeks(spot, strike, t_years, vol, r, is_call=False)

    # ATM Call delta should be around 0.5 - 0.55
    assert 0.45 < call_greeks.delta < 0.60
    # ATM Put delta should be around -0.45 to -0.55
    assert -0.55 < put_greeks.delta < -0.40
    # Gamma should be positive
    assert call_greeks.gamma > 0
    assert abs(call_greeks.gamma - put_greeks.gamma) < 1e-6
    # Theta should be negative (decay with passing time)
    assert call_greeks.theta < 0
    # Vega should be positive
    assert call_greeks.vega > 0


def test_iron_condor_simulation_unbreached():
    """Test unbreached Iron Condor captures theta decay."""
    res = OptionsStructure.simulate_iron_condor(
        spot_entry=22000.0,
        vix_entry=14.0,
        spot_high=22100.0,
        spot_low=21900.0,
        spot_exit=22050.0,
        otm_sd=1.8,
        wing_sd=2.4,
        days_to_expiry=5,
        lot_size=50,
        lots=2,
    )
    assert isinstance(res, IronCondorResult)
    assert not res.breached
    assert res.win
    assert res.breach_side == "none"
    assert res.pnl > 0


def test_iron_condor_simulation_breached():
    """Test breached Iron Condor caps loss at defined stop/wing."""
    res = OptionsStructure.simulate_iron_condor(
        spot_entry=22000.0,
        vix_entry=15.0,
        spot_high=23500.0,  # Violent spike breaching upper call
        spot_low=21950.0,
        spot_exit=23400.0,
        otm_sd=1.8,
        wing_sd=2.4,
        days_to_expiry=5,
        lot_size=50,
        lots=1,
    )
    assert res.breached
    assert not res.win
    assert res.breach_side == "call"
    assert res.pnl < 0


def test_futures_margin_engine():
    """Verify margin calculations and F&O execution friction."""
    engine = FuturesMarginEngine()

    nifty_margin = engine.get_margin_requirement("INDEX_NIFTY50", 22000.0)
    bn_margin = engine.get_margin_requirement("INDEX_BANKNIFTY", 48000.0)

    # NIFTY 1 lot = 50 * 22000 = 11,00,000 * 0.11 = 1,21,000
    assert 110000 < nifty_margin < 135000
    # BANK NIFTY 1 lot = 15 * 48000 = 7,20,000 * 0.14 = 1,00,800
    assert 90000 < bn_margin < 115000

    # Test trade pnl: 500 pt gain on BANK NIFTY 1 lot (15 qty)
    gross_pnl, costs, net_pnl = engine.compute_trade_pnl(
        symbol="INDEX_BANKNIFTY",
        direction=1,
        entry_price=48000.0,
        exit_price=48500.0,
        quantity=15,
        leverage=3.0,
    )
    assert gross_pnl == 500.0 * 15  # 7500
    assert costs > 0
    assert net_pnl == gross_pnl - costs


def _create_dummy_df(n_bars: int = 250, base_price: float = 20000.0) -> pd.DataFrame:
    """Helper to create dummy OHLCV dataframe with indicators."""
    dates = pd.date_range("2023-01-01", periods=n_bars, freq="B")
    np.random.seed(42)
    drift = np.linspace(0, 0.20, n_bars)
    noise = np.random.normal(0, 0.008, n_bars)
    prices = base_price * (1.0 + drift + np.cumsum(noise))

    highs = prices * (1.0 + np.abs(np.random.normal(0, 0.005, n_bars)))
    lows = prices * (1.0 - np.abs(np.random.normal(0, 0.005, n_bars)))
    closes = prices
    volumes = np.random.randint(100000, 500000, n_bars)

    df = pd.DataFrame({
        "datetime": dates,
        "open": prices * 0.999,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })
    df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["ema_200"] = df["close"].ewm(span=200, adjust=False).mean()
    df["rsi_14"] = 55.0
    df["atr_14"] = (df["high"] - df["low"]).rolling(14).mean().fillna(base_price * 0.01)
    df["vix"] = 15.0
    return df


def test_derivatives_strategy_signals():
    """Verify signals generation across all 4 derivatives strategies."""
    df = _create_dummy_df(250)

    # 1. Options Condor
    condor_strat = NiftyWeeklyIronCondorStrategy()
    condor_sig = condor_strat.generate_signals(df)
    assert not condor_sig.empty
    assert "signal" in condor_sig.columns
    assert set(condor_sig["signal"].unique()).issubset({0, 1})

    # 2. Bank Nifty Trend Futures
    trend_strat = BankNiftyTrendFuturesStrategy()
    trend_sig = trend_strat.generate_signals(df)
    assert not trend_sig.empty
    assert "signal" in trend_sig.columns
    assert set(trend_sig["signal"].unique()).issubset({0, 1})

    # 3. Index Dip Sniper
    dip_strat = IndexDipSniperStrategy()
    dip_sig = dip_strat.generate_signals(df)
    assert not dip_sig.empty
    assert "signal" in dip_sig.columns

    # 4. Master Alpha Portfolio
    master_strat = MasterDerivativesAlphaPortfolio()
    master_sig = master_strat.generate_signals(df)
    assert not master_sig.empty
    assert "signal" in master_sig.columns


def test_master_portfolio_simulation():
    """Verify MasterDerivativesAlphaPortfolio simulation execution and metrics."""
    nifty = _create_dummy_df(260, base_price=20000.0)
    bn = _create_dummy_df(260, base_price=45000.0)
    vix = pd.DataFrame({
        "datetime": nifty["datetime"],
        "close": 15.0,
    })

    res = MasterDerivativesAlphaPortfolio.simulate_full_fund(
        nifty_df=nifty,
        banknifty_df=bn,
        vix_df=vix,
        initial_capital=1000000.0,
    )

    assert "win_rate" in res
    assert "cagr" in res
    assert "sharpe_ratio" in res
    assert "max_drawdown_pct" in res
    assert "trades" in res
    assert res["initial_capital"] == 1000000.0
    assert len(res["equity_curve"]) > 0

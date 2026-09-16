"""
Black-Scholes Options Pricing, Greeks, and Synthetic Multi-Leg Options Simulator.
Calibrated for Indian Index Options (NIFTY 50 & BANK NIFTY) with INDIA VIX.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass
from scipy.stats import norm
from src.backtesting.cost_model import IndianCostModel, OrderType
from src.utils.logging import setup_logging

logger = setup_logging("deriv.options")


@dataclass
class Greeks:
    delta: float
    gamma: float
    theta: float  # daily theta in currency/index points
    vega: float   # per 1% change in IV


@dataclass
class IronCondorResult:
    entry_date: pd.Timestamp
    expiry_date: pd.Timestamp
    spot_entry: float
    spot_exit: float
    vix_entry: float
    short_call: float
    short_put: float
    long_call: float
    long_put: float
    net_credit: float
    max_loss: float
    lots: int
    pnl: float
    win: bool
    breached: bool
    breach_side: str  # 'call', 'put', 'none'


class BlackScholesEngine:
    """
    Analytic Black-Scholes framework for European index options.
    """

    @staticmethod
    def d1_d2(spot: float, strike: float, t_years: float, vol: float, r: float = 0.065) -> tuple[float, float]:
        if spot <= 0 or strike <= 0 or t_years <= 0 or vol <= 0:
            return 0.0, 0.0
        d1 = (np.log(spot / strike) + (r + 0.5 * vol**2) * t_years) / (vol * np.sqrt(t_years))
        d2 = d1 - vol * np.sqrt(t_years)
        return d1, d2

    @staticmethod
    def price_call(spot: float, strike: float, t_years: float, vol: float, r: float = 0.065) -> float:
        if t_years <= 0:
            return max(0.0, spot - strike)
        d1, d2 = BlackScholesEngine.d1_d2(spot, strike, t_years, vol, r)
        return spot * norm.cdf(d1) - strike * np.exp(-r * t_years) * norm.cdf(d2)

    @staticmethod
    def price_put(spot: float, strike: float, t_years: float, vol: float, r: float = 0.065) -> float:
        if t_years <= 0:
            return max(0.0, strike - spot)
        d1, d2 = BlackScholesEngine.d1_d2(spot, strike, t_years, vol, r)
        return strike * np.exp(-r * t_years) * norm.cdf(-d2) - spot * norm.cdf(-d1)

    @staticmethod
    def compute_greeks(
        spot: float, strike: float, t_years: float, vol: float, r: float = 0.065, is_call: bool = True
    ) -> Greeks:
        if t_years <= 0 or vol <= 0:
            return Greeks(delta=1.0 if is_call and spot > strike else 0.0, gamma=0.0, theta=0.0, vega=0.0)
        d1, d2 = BlackScholesEngine.d1_d2(spot, strike, t_years, vol, r)
        pdf_d1 = norm.pdf(d1)
        sqrt_t = np.sqrt(t_years)

        delta = norm.cdf(d1) if is_call else norm.cdf(d1) - 1.0
        gamma = pdf_d1 / (spot * vol * sqrt_t) if (spot * vol * sqrt_t) > 0 else 0.0

        # Annualized theta -> divide by 365 for daily theta
        theta_annual = -(spot * pdf_d1 * vol) / (2 * sqrt_t)
        if is_call:
            theta_annual -= r * strike * np.exp(-r * t_years) * norm.cdf(d2)
        else:
            theta_annual += r * strike * np.exp(-r * t_years) * norm.cdf(-d2)
        theta_daily = theta_annual / 365.0

        vega = spot * sqrt_t * pdf_d1 * 0.01  # Per 1% IV move
        return Greeks(delta=delta, gamma=gamma, theta=theta_daily, vega=vega)


class OptionsStructure:
    """
    Simulates multi-leg synthetic options payoff structures.
    """

    @staticmethod
    def simulate_iron_condor(
        spot_entry: float,
        vix_entry: float,
        spot_high: float,
        spot_low: float,
        spot_exit: float,
        otm_sd: float = 1.8,
        wing_sd: float = 2.4,
        days_to_expiry: int = 5,
        lot_size: int = 50,
        lots: int = 1,
        r: float = 0.065,
    ) -> IronCondorResult:
        """
        Simulate an Iron Condor over a holding period (e.g. weekly).
        - Sells OTM Call & Put at otm_sd standard deviations
        - Buys long protective wings at wing_sd standard deviations
        """
        vol = max(0.08, vix_entry / 100.0)
        t_years = days_to_expiry / 365.0
        exp_move = spot_entry * vol * np.sqrt(t_years)

        short_call = spot_entry + (otm_sd * exp_move)
        short_put = spot_entry - (otm_sd * exp_move)
        long_call = spot_entry + (wing_sd * exp_move)
        long_put = spot_entry - (wing_sd * exp_move)

        # Theoretical premiums
        p_sc = BlackScholesEngine.price_call(spot_entry, short_call, t_years, vol, r)
        p_sp = BlackScholesEngine.price_put(spot_entry, short_put, t_years, vol, r)
        p_lc = BlackScholesEngine.price_call(spot_entry, long_call, t_years, vol, r)
        p_lp = BlackScholesEngine.price_put(spot_entry, long_put, t_years, vol, r)

        net_credit_pts = max(10.0, (p_sc + p_sp) - (p_lc + p_lp))
        wing_width = (long_call - short_call)
        max_loss_pts = max(1.0, wing_width - net_credit_pts)

        # Check breach over the week
        breached_up = spot_high > short_call
        breached_down = spot_low < short_put
        breached = breached_up or breached_down

        cost_model = IndianCostModel()
        costs = lots * 140.0  # STT, exchange charges, turnover GST

        if not breached:
            # 85% of credit retained on unbreached expiry (theta decay)
            trade_pnl_pts = net_credit_pts * 0.85
            net_pnl = (trade_pnl_pts * lot_size * lots) - costs
            win = True
            side = "none"
        else:
            # Stop loss capped at 1.5x credit
            loss_pts = min(max_loss_pts, net_credit_pts * 1.5)
            net_pnl = (-loss_pts * lot_size * lots) - costs
            win = False
            side = "call" if breached_up else "put"

        return IronCondorResult(
            entry_date=pd.Timestamp.now(),
            expiry_date=pd.Timestamp.now(),
            spot_entry=spot_entry,
            spot_exit=spot_exit,
            vix_entry=vix_entry,
            short_call=short_call,
            short_put=short_put,
            long_call=long_call,
            long_put=long_put,
            net_credit=net_credit_pts,
            max_loss=max_loss_pts,
            lots=lots,
            pnl=net_pnl,
            win=win,
            breached=breached,
            breach_side=side,
        )

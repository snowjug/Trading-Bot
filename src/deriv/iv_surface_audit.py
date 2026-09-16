"""
Options Implied Volatility Surface & Pricing Error Audit Engine.
Phase 28G Implementation.

Audits whether assuming India VIX as a flat implied volatility causes systematic
pricing errors across the options surface (strike skew, term structure, moneyness).
Computes implied volatility via Black-Scholes inversion on real NSE UDiFF Bhavcopy prices.
"""
import math
import numpy as np
import pandas as pd
from scipy.stats import norm
from scipy.optimize import brentq
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from src.deriv.contract_reconstruction import HistoricalContractReconstructor
from src.utils.logging import setup_logging

logger = setup_logging("deriv.iv_surface_audit")


def bs_call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Standard Black-Scholes call price."""
    if T <= 1e-5 or sigma <= 1e-5:
        return max(0.0, S - K)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)


def bs_put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Standard Black-Scholes put price."""
    if T <= 1e-5 or sigma <= 1e-5:
        return max(0.0, K - S)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def implied_volatility(
    price: float,
    S: float,
    K: float,
    T: float,
    r: float = 0.065,
    option_type: str = "CE",
) -> Optional[float]:
    """Invert Black-Scholes to extract contract-implied volatility."""
    if price <= 0.05 or T <= 1e-4:
        return None

    intrinsic = max(0.0, S - K) if option_type == "CE" else max(0.0, K - S)
    if price <= intrinsic:
        return None

    def obj(sigma):
        if option_type == "CE":
            return bs_call_price(S, K, T, r, sigma) - price
        else:
            return bs_put_price(S, K, T, r, sigma) - price

    try:
        # Solve for sigma in [0.01, 3.00] (1% to 300% IV)
        iv = brentq(obj, 0.01, 3.0, xtol=1e-4, maxiter=50)
        return float(iv)
    except Exception:
        return None


@dataclass
class IVSurfaceComparisonResult:
    trade_date: str
    underlying_price: float
    india_vix_flat: float
    total_contracts_analyzed: int
    mean_implied_iv: float
    atm_implied_iv: float
    iv_skew_otm_put_minus_atm: float
    iv_skew_otm_call_minus_atm: float
    mean_pricing_error_pts: float
    mean_percentage_pricing_error: float
    is_vix_underpricing: bool


class IVSurfaceAuditor:
    """
    Audits the flat India VIX assumption against real market settlement prices.
    """

    def __init__(self, reconstructor: Optional[HistoricalContractReconstructor] = None):
        self.reconstructor = reconstructor or HistoricalContractReconstructor()

    def audit_bhavcopy_date(
        self,
        date_str: str,
        india_vix_val: float,
        r: float = 0.065,
    ) -> Optional[IVSurfaceComparisonResult]:
        """Audit IV surface for a specific trading date."""
        if date_str not in self.reconstructor.indexed_bhavcopies:
            return None

        df = self.reconstructor.indexed_bhavcopies[date_str]
        nifty_df = df[(df["symbol"] == "NIFTY") & (df["settlement"] > 1.0)].copy()
        if nifty_df.empty:
            return None

        S = float(nifty_df["underlying_price"].iloc[0])
        vix_sigma = india_vix_val / 100.0

        iv_records = []
        pricing_errors = []
        pct_errors = []

        d_obj = pd.to_datetime(date_str)

        for _, row in nifty_df.iterrows():
            K = float(row["strike"])
            opt_type = str(row["option_type"]).upper()
            mkt_price = float(row["settlement"])
            exp_date = pd.to_datetime(str(row["expiry_date"]))
            dte = max(1, (exp_date - d_obj).days)
            T = dte / 365.0

            # Compute BS price using flat India VIX
            if opt_type == "CE":
                bs_price_vix = bs_call_price(S, K, T, r, vix_sigma)
            else:
                bs_price_vix = bs_put_price(S, K, T, r, vix_sigma)

            pricing_err = bs_price_vix - mkt_price
            pricing_errors.append(pricing_err)
            if mkt_price > 5.0:
                pct_errors.append((pricing_err / mkt_price) * 100.0)

            # Extract contract IV
            iv = implied_volatility(mkt_price, S, K, T, r, opt_type)
            if iv is not None:
                moneyness = K / S
                iv_records.append({
                    "strike": K,
                    "moneyness": moneyness,
                    "opt_type": opt_type,
                    "dte": dte,
                    "mkt_price": mkt_price,
                    "implied_iv": iv,
                })

        if not iv_records:
            return None

        iv_df = pd.DataFrame(iv_records)
        mean_iv = float(iv_df["implied_iv"].mean()) * 100.0

        # ATM strike is closest to S
        atm_strike = iv_df.iloc[(iv_df["strike"] - S).abs().argsort()[:1]]["strike"].values[0]
        atm_sub = iv_df[iv_df["strike"] == atm_strike]
        atm_iv = float(atm_sub["implied_iv"].mean()) * 100.0 if not atm_sub.empty else mean_iv

        # OTM Put (moneyness ~ 0.95)
        otm_puts = iv_df[(iv_df["opt_type"] == "PE") & (iv_df["moneyness"] <= 0.96)]
        otm_put_iv = float(otm_puts["implied_iv"].mean()) * 100.0 if not otm_puts.empty else atm_iv

        # OTM Call (moneyness ~ 1.04)
        otm_calls = iv_df[(iv_df["opt_type"] == "CE") & (iv_df["moneyness"] >= 1.04)]
        otm_call_iv = float(otm_calls["implied_iv"].mean()) * 100.0 if not otm_calls.empty else atm_iv

        mean_err = float(np.mean(pricing_errors))
        mean_pct_err = float(np.mean(pct_errors)) if pct_errors else 0.0

        return IVSurfaceComparisonResult(
            trade_date=date_str,
            underlying_price=S,
            india_vix_flat=india_vix_val,
            total_contracts_analyzed=len(iv_df),
            mean_implied_iv=mean_iv,
            atm_implied_iv=atm_iv,
            iv_skew_otm_put_minus_atm=otm_put_iv - atm_iv,
            iv_skew_otm_call_minus_atm=otm_call_iv - atm_iv,
            mean_pricing_error_pts=mean_err,
            mean_percentage_pricing_error=mean_pct_err,
            is_vix_underpricing=bool(mean_err < 0.0),
        )


def run_iv_surface_audit() -> List[IVSurfaceComparisonResult]:
    """Audit all available Bhavcopies against corresponding India VIX readings."""
    auditor = IVSurfaceAuditor()
    # Verified India VIX close values for the 4 dates from INDEX_INDIAVIX_daily.csv
    vix_map = {
        "2026-03-19": 14.85,
        "2026-06-18": 13.90,
        "2026-08-27": 13.10,
        "2026-09-15": 12.95,
    }

    results = []
    for dt_str, vix_val in vix_map.items():
        res = auditor.audit_bhavcopy_date(dt_str, vix_val)
        if res:
            results.append(res)
    return results

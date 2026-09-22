"""
Regime classification: trend vs range, and a volatility bucket.

Both are deliberately crude and explainable. A regime label is context for the
decision, never a signal on its own, and a crude label that a human can verify from
a chart is worth more here than a fitted one that cannot be checked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class Regime:
    trend: str          # "UP" | "DOWN" | "RANGE"
    trend_strength: float   # 0..1
    vol_bucket: str     # "LOW" | "MEDIUM" | "HIGH"
    vol_pct_rank: Optional[float]
    tradable: bool
    why: str


def classify(ema_fast: Optional[float], ema_mid: Optional[float],
             ema_slow: Optional[float], adx_proxy: Optional[float],
             structure: str, vol_pct_rank: Optional[float],
             compression_ratio: Optional[float]) -> Regime:
    """
    `adx_proxy` is the absolute EMA-fast slope in percent per bar — a cheap stand-in
    for trend strength that needs no extra state.

    A market is called RANGE unless the moving-average stack AND the swing structure
    agree. Requiring two independent confirmations is what stops a single crossing
    from being read as a trend.
    """
    votes_up = votes_dn = 0
    if None not in (ema_fast, ema_mid, ema_slow):
        if ema_fast > ema_mid > ema_slow:
            votes_up += 1
        elif ema_fast < ema_mid < ema_slow:
            votes_dn += 1
    if structure == "HH_HL":
        votes_up += 1
    elif structure == "LH_LL":
        votes_dn += 1

    if votes_up >= 2:
        trend, why = "UP", "EMA stack and structure both bullish"
    elif votes_dn >= 2:
        trend, why = "DOWN", "EMA stack and structure both bearish"
    else:
        trend, why = "RANGE", f"no agreement (up_votes={votes_up} dn_votes={votes_dn})"

    strength = 0.0
    if adx_proxy is not None:
        strength = float(min(1.0, abs(adx_proxy) / 0.15))    # 0.15%/bar saturates
    if trend == "RANGE":
        strength *= 0.5

    if vol_pct_rank is None:
        bucket = "MEDIUM"
    elif vol_pct_rank < 30:
        bucket = "LOW"
    elif vol_pct_rank > 70:
        bucket = "HIGH"
    else:
        bucket = "MEDIUM"

    # An extremely compressed market is not untradable, but it is not a trend either.
    if compression_ratio is not None and compression_ratio < 0.25 and trend != "RANGE":
        trend = "RANGE"
        why += "; overridden to RANGE by severe compression"

    return Regime(trend=trend, trend_strength=round(strength, 3), vol_bucket=bucket,
                  vol_pct_rank=(round(vol_pct_rank, 1) if vol_pct_rank is not None else None),
                  tradable=True, why=why)

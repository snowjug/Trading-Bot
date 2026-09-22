"""
Candle geometry as numbers, not as folklore.

The directive is explicit: "DO NOT treat textbook candle names as magic signals.
Represent them as quantitative features." So the primary output is geometry —
body fraction, wick fractions, direction, size relative to recent range — and the
named patterns are derived booleans built from that geometry with stated thresholds,
present only because they are convenient labels for a compact state.

Nothing here decides anything.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CandleFeatures:
    direction: int                  # +1 up close, -1 down close, 0 doji-ish
    range_pts: float
    body_pts: float
    body_frac: float                # |close-open| / range
    upper_wick_frac: float
    lower_wick_frac: float
    close_position: float           # 0 = closed at low, 1 = closed at high
    size_vs_atr: Optional[float]    # range / ATR14
    # derived labels, thresholds stated in the code below
    is_momentum_bar: bool           # body_frac >= 0.65 and size_vs_atr >= 1.0
    is_pin_bar: bool                # one wick >= 0.60 of range, body <= 0.30
    is_rejection_up: bool           # long upper wick, closed in lower third
    is_rejection_down: bool         # long lower wick, closed in upper third
    is_inside_bar: bool
    is_outside_bar: bool
    is_bullish_engulf: bool
    is_bearish_engulf: bool

    def to_dict(self) -> Dict:
        return asdict(self)


def _safe(x: float, d: float = 0.0) -> float:
    return float(x) if np.isfinite(x) else d


def candle_features(df: pd.DataFrame, atr14: Optional[float] = None
                    ) -> Optional[CandleFeatures]:
    """Features of the LAST bar in `df`, using the previous bar for engulf/inside."""
    if df is None or df.empty:
        return None
    last = df.iloc[-1]
    o, h, l, c = (float(last["open"]), float(last["high"]),
                  float(last["low"]), float(last["close"]))
    rng = h - l
    body = abs(c - o)
    if rng <= 0:
        return CandleFeatures(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5, None,
                              False, False, False, False, False, False, False, False)
    body_frac = body / rng
    upper = (h - max(o, c)) / rng
    lower = (min(o, c) - l) / rng
    close_pos = (c - l) / rng
    direction = 1 if c > o else (-1 if c < o else 0)
    size_vs_atr = (rng / atr14) if (atr14 and atr14 > 0) else None

    prev = df.iloc[-2] if len(df) >= 2 else None
    inside = outside = bull_eng = bear_eng = False
    if prev is not None:
        ph, pl = float(prev["high"]), float(prev["low"])
        po, pc = float(prev["open"]), float(prev["close"])
        inside = (h <= ph) and (l >= pl)
        outside = (h > ph) and (l < pl)
        pbody_lo, pbody_hi = min(po, pc), max(po, pc)
        bull_eng = (c > o) and (pc < po) and (c >= pbody_hi) and (o <= pbody_lo)
        bear_eng = (c < o) and (pc > po) and (o >= pbody_hi) and (c <= pbody_lo)

    return CandleFeatures(
        direction=direction, range_pts=_safe(rng), body_pts=_safe(body),
        body_frac=_safe(body_frac), upper_wick_frac=_safe(upper),
        lower_wick_frac=_safe(lower), close_position=_safe(close_pos, 0.5),
        size_vs_atr=size_vs_atr,
        is_momentum_bar=bool(body_frac >= 0.65 and (size_vs_atr or 0) >= 1.0),
        is_pin_bar=bool(body_frac <= 0.30 and max(upper, lower) >= 0.60),
        is_rejection_up=bool(upper >= 0.50 and close_pos <= 0.34),
        is_rejection_down=bool(lower >= 0.50 and close_pos >= 0.66),
        is_inside_bar=bool(inside), is_outside_bar=bool(outside),
        is_bullish_engulf=bool(bull_eng), is_bearish_engulf=bool(bear_eng),
    )

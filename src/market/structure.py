"""
Market structure: swings, the HH/HL/LH/LL sequence, breakouts, and levels.

Everything here is a QUANTITATIVE feature. A "breakout" is not a verdict — it is
"the last close is above the prior confirmed swing high, by this many points, on
this much volume". Whether that is tradable is decided later, with costs in hand.

A swing is confirmed only when `k` bars on BOTH sides are lower (for a high) or
higher (for a low). That is what makes it causally safe: a pivot at index i is only
knowable at i+k, so `swings()` never reports a pivot whose right-hand confirmation
bars are not already in the frame.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Swing:
    idx: int
    price: float
    kind: str          # "high" | "low"
    confirmed_at: int  # bar index at which this pivot became knowable


def swings(df: pd.DataFrame, k: int = 2) -> List[Swing]:
    """
    Confirmed pivots. A pivot at i needs k lower highs (or higher lows) on each side,
    so it is reported with confirmed_at = i + k and never earlier.

    Vectorised: the naive double loop is O(n*k) in Python and dominated replay cost
    at ~400 ms per decision bar across five timeframes. Sliding-window maxima make it
    O(n) in numpy. The semantics are unchanged and `test_swings_match_reference`
    pins the two implementations together.
    """
    out: List[Swing] = []
    n = len(df)
    if n < 2 * k + 1:
        return out
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    try:
        from numpy.lib.stride_tricks import sliding_window_view as swv
    except ImportError:                                    # very old numpy
        return _swings_reference(df, k)

    # windows of length k immediately left and right of each candidate index
    left_h = swv(h[:-k - 1], k).max(axis=1) if n > k + 1 else np.empty(0)
    right_h = swv(h[k + 1:], k).max(axis=1) if n > k + 1 else np.empty(0)
    left_l = swv(l[:-k - 1], k).min(axis=1) if n > k + 1 else np.empty(0)
    right_l = swv(l[k + 1:], k).min(axis=1) if n > k + 1 else np.empty(0)

    m = min(len(left_h), len(right_h), n - 2 * k)
    if m <= 0:
        return out
    idx = np.arange(k, k + m)
    mid_h, mid_l = h[idx], l[idx]
    is_hi = (mid_h > left_h[:m]) & (mid_h > right_h[:m])
    is_lo = (mid_l < left_l[:m]) & (mid_l < right_l[:m])
    for i in idx[is_hi]:
        out.append(Swing(int(i), float(h[i]), "high", int(i) + k))
    for i in idx[is_lo]:
        out.append(Swing(int(i), float(l[i]), "low", int(i) + k))
    return sorted(out, key=lambda s: s.idx)


def _swings_reference(df: pd.DataFrame, k: int = 2) -> List[Swing]:
    """The original explicit implementation, kept as the test oracle."""
    out: List[Swing] = []
    if len(df) < 2 * k + 1:
        return out
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    for i in range(k, len(df) - k):
        if h[i] > h[i - k:i].max() and h[i] > h[i + 1:i + 1 + k].max():
            out.append(Swing(i, float(h[i]), "high", i + k))
        if l[i] < l[i - k:i].min() and l[i] < l[i + 1:i + 1 + k].min():
            out.append(Swing(i, float(l[i]), "low", i + k))
    return sorted(out, key=lambda s: s.idx)


def last_swings(sw: List[Swing], kind: str, n: int = 2) -> List[Swing]:
    return [s for s in sw if s.kind == kind][-n:]


def structure_label(sw: List[Swing]) -> str:
    """
    The classic sequence, from the last two confirmed highs and lows.

    HH_HL  uptrend structure        LH_LL  downtrend structure
    HH_LL / LH_HL  expanding or contradictory -> reported as MIXED
    """
    hs, ls = last_swings(sw, "high", 2), last_swings(sw, "low", 2)
    if len(hs) < 2 or len(ls) < 2:
        return "UNKNOWN"
    hh = hs[-1].price > hs[-2].price
    hl = ls[-1].price > ls[-2].price
    if hh and hl:
        return "HH_HL"
    if (not hh) and (not hl):
        return "LH_LL"
    return "MIXED"


@dataclass(frozen=True)
class Levels:
    swing_high: Optional[float]
    swing_low: Optional[float]
    or_high: Optional[float]          # opening range
    or_low: Optional[float]
    prev_day_high: Optional[float]
    prev_day_low: Optional[float]
    prev_day_close: Optional[float]


def opening_range(df: pd.DataFrame, bars: int = 3) -> Tuple[Optional[float], Optional[float]]:
    """High/low of the first `bars` bars of the session in `df` (one session only)."""
    if df.empty:
        return None, None
    d = df.head(bars)
    return float(d["high"].max()), float(d["low"].min())


@dataclass(frozen=True)
class BreakState:
    broke_high: bool
    broke_low: bool
    break_points: Optional[float]      # distance beyond the level, in points
    failed_break_high: bool            # traded above then closed back inside
    failed_break_low: bool


def break_state(df: pd.DataFrame, level_high: Optional[float],
                level_low: Optional[float]) -> BreakState:
    """
    Breakout / breakdown / failed break, measured on the last bar.

    A FAILED break is the case a discretionary trader cares about most: the bar's
    HIGH exceeded the level but its CLOSE came back inside. That is a different
    event from never having reached it, and it is kept separate here.
    """
    if df.empty:
        return BreakState(False, False, None, False, False)
    last = df.iloc[-1]
    c, hi, lo = float(last["close"]), float(last["high"]), float(last["low"])
    bh = bl = fh = fl = False
    pts: Optional[float] = None
    if level_high is not None and np.isfinite(level_high):
        if c > level_high:
            bh, pts = True, c - level_high
        elif hi > level_high:
            fh = True
    if level_low is not None and np.isfinite(level_low):
        if c < level_low:
            bl = True
            pts = (level_low - c) if pts is None else pts
        elif lo < level_low:
            fl = True
    return BreakState(bh, bl, (float(pts) if pts is not None else None), fh, fl)


def compression(df: pd.DataFrame, lookback: int = 20, short: int = 5
                ) -> Optional[float]:
    """
    Range compression ratio: recent `short`-bar range over the `lookback`-bar range.
    Below ~0.35 is a coiled market; above ~1.0 is expansion. None if not enough bars.
    """
    if len(df) < lookback:
        return None
    lb = df.tail(lookback)
    sh = df.tail(short)
    wide = float(lb["high"].max() - lb["low"].min())
    if wide <= 0:
        return None
    return float((sh["high"].max() - sh["low"].min()) / wide)


def significant_levels(df: pd.DataFrame, lookback: int = 40, exclude_recent: int = 1
                       ) -> Tuple[Optional[float], Optional[float]]:
    """
    The levels a trader would actually draw: the extreme of a meaningful window,
    EXCLUDING the most recent bars so the level is not defined by the bar testing it.

    This is the difference between a breakout and noise. `last swing high` from a
    k=2 pivot is only a handful of bars old, so on a 5-minute chart price crosses it
    constantly and every other bar looks like a "breakout". A level taken from the
    prior `lookback` bars, excluding the current one, is a level that has HELD.
    """
    if df is None or len(df) < lookback + exclude_recent:
        return None, None
    w = df.iloc[-(lookback + exclude_recent):-exclude_recent] if exclude_recent > 0 \
        else df.iloc[-lookback:]
    if w.empty:
        return None, None
    return float(w["high"].max()), float(w["low"].min())


def is_new_break(df: pd.DataFrame, level: Optional[float], side: str) -> bool:
    """
    True only on the bar that CROSSES the level, not on every bar that remains
    beyond it. A breakout is a transition; without this a position would be
    re-signalled on every subsequent bar.
    """
    if level is None or not np.isfinite(level) or len(df) < 2:
        return False
    c_now = float(df["close"].iloc[-1])
    c_prev = float(df["close"].iloc[-2])
    if side == "high":
        return c_prev <= level < c_now
    return c_prev >= level > c_now

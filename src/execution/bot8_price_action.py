"""
Bot 8 — price action / market structure.

The edge here is meant to come from STRUCTURE, not from an indicator stack. The
only non-price inputs are ATR (to size risk and to scale what counts as a
meaningful break) and India VIX (to stand aside in disordered conditions). Neither
generates a signal; both only permit or size one.

THE SETUP, in one sentence: price breaks a confirmed swing level, pulls back to it
without giving it up, and then resumes — so the break is traded on its RETEST
rather than on the impulse itself.

WHY A RETEST RATHER THAN THE BREAK. Buying the impulse means paying the widest
spread of the move at its worst price, and a failed break is indistinguishable from
a real one at the moment it happens. Waiting for the pullback costs some moves
entirely, but it supplies the one thing the impulse cannot: a structural level that
defines where the idea is WRONG. The stop is that level, so risk is defined by the
market's own structure instead of by an arbitrary percentage.

STATES
  WAIT          no confirmed structure, or conditions disallow trading
  ARMED         a confirmed swing level exists and price has broken it
  LONG_SETUP    broken up, price has pulled back into the retest zone
  SHORT_SETUP   broken down, price has pulled back into the retest zone
  LONG_ENTRY    retest held and price resumed upward
  SHORT_ENTRY   retest held and price resumed downward
  REJECTED      the break failed — price gave the level back

CHRONOLOGY. Every value is computed from bars at or before the decision bar.
Swing confirmation requires `k` bars on BOTH sides, so a swing is only ever
confirmed `k` bars after it happened — it is never read at the moment it formed.
That lag is the cost of not using hindsight, and it is deliberate.
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import time as dtime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.utils.logging import setup_logging

logger = setup_logging("execution.bot8")

SWING_K = 3                 # bars either side needed to confirm a swing
BREAK_ATR = 0.25            # a break must clear the level by this much ATR
RETEST_ATR = 0.22           # how close to the level a pullback must come
RESUME_ATR = 0.06           # confirmation that the retest held
MAX_VIX = 26.0
MIN_RR = 1.3                # setups worse than this are not worth the spread
REQUIRE_TREND_ALIGNMENT = True
# TWO REWORKS, both recorded rather than quietly replaced.
#   v1  break 0.10 ATR, no trend gate      -> traded 91.5% of sessions. A
#       "structural break" that happens almost every day is noise with a label.
#   v2  break 0.25 ATR, gated on the INTRADAY swing sequence -> 0.7% of sessions.
#       A single session rarely prints enough confirmed swings to label a clean
#       uptrend, so the gate was effectively an off switch.
#   v3  break 0.25 ATR, gated on the DAILY structure supplied by the caller.
#       Daily structure is what "the trend" normally means, it is stable enough to
#       classify, and it expresses the actual discipline: take intraday breaks in
#       the direction of the higher-timeframe structure, not against it.


@dataclass
class Structure:
    """What the market's own swings say, at this bar."""
    swing_high: Optional[float] = None
    swing_low: Optional[float] = None
    prior_swing_high: Optional[float] = None
    prior_swing_low: Optional[float] = None
    trend: str = "UNDEFINED"        # UPTREND | DOWNTREND | RANGE | UNDEFINED
    support: Optional[float] = None
    resistance: Optional[float] = None


@dataclass
class PriceActionSignal:
    """Everything the ledger and the dashboard need to explain this decision."""
    state: str
    reason: str
    direction: int = 0
    setup_type: Optional[str] = None
    structure: Structure = field(default_factory=Structure)
    breakout_state: str = "NONE"     # NONE | BROKEN_UP | BROKEN_DOWN | FAILED
    retest_state: str = "NONE"       # NONE | PENDING | HELD | FAILED
    entry: Optional[float] = None
    stop: Optional[float] = None
    target: Optional[float] = None
    risk_reward: Optional[float] = None
    atr: Optional[float] = None
    meta: Dict[str, Any] = field(default_factory=dict)


# ─────────────────────────── STRUCTURE ───────────────────────────

def find_swings(prices: List[float], k: int = SWING_K) -> Tuple[List[int], List[int]]:
    """
    Confirmed swing pivots.

    A pivot at i needs k bars on BOTH sides, so index i is only confirmed once bar
    i+k exists. Scanning stops at len-k for exactly that reason: including the last
    k bars would be claiming to know a pivot before the bars that confirm it have
    printed.
    """
    highs, lows = [], []
    n = len(prices)
    for i in range(k, n - k):
        window = prices[i - k:i + k + 1]
        if prices[i] == max(window) and prices[i] > prices[i - 1]:
            highs.append(i)
        if prices[i] == min(window) and prices[i] < prices[i - 1]:
            lows.append(i)
    return highs, lows


def read_structure(prices: List[float], k: int = SWING_K) -> Structure:
    """
    Classifies trend from the sequence of confirmed swings.

    Higher highs AND higher lows is an uptrend; lower highs AND lower lows a
    downtrend; anything else is a range. Requiring both legs to agree is what stops
    a single spike being read as a trend.
    """
    s = Structure()
    if len(prices) < 2 * k + 3:
        return s
    hi_idx, lo_idx = find_swings(prices, k)
    if hi_idx:
        s.swing_high = prices[hi_idx[-1]]
        s.resistance = s.swing_high
        if len(hi_idx) >= 2:
            s.prior_swing_high = prices[hi_idx[-2]]
    if lo_idx:
        s.swing_low = prices[lo_idx[-1]]
        s.support = s.swing_low
        if len(lo_idx) >= 2:
            s.prior_swing_low = prices[lo_idx[-2]]

    if s.swing_high and s.prior_swing_high and s.swing_low and s.prior_swing_low:
        hh, hl = s.swing_high > s.prior_swing_high, s.swing_low > s.prior_swing_low
        lh, ll = s.swing_high < s.prior_swing_high, s.swing_low < s.prior_swing_low
        if hh and hl:
            s.trend = "UPTREND"
        elif lh and ll:
            s.trend = "DOWNTREND"
        else:
            s.trend = "RANGE"
    return s



def daily_bias_from(closes: pd.Series, fast: int = 20, slow: int = 50) -> str:
    """
    Higher-timeframe structure from COMPLETED daily closes.

    Deliberately simple: an EMA stack is a stable, unambiguous read of daily
    direction, where an intraday swing sequence is not. Anything that is not a
    clean stack is RANGE, and a range permits breaks in either direction.
    """
    if closes is None or len(closes) < slow + 2:
        return "UNDEFINED"
    f = closes.ewm(span=fast, adjust=False).mean().iloc[-1]
    s = closes.ewm(span=slow, adjust=False).mean().iloc[-1]
    last = float(closes.iloc[-1])
    if last > f > s:
        return "UPTREND"
    if last < f < s:
        return "DOWNTREND"
    return "RANGE"

# ─────────────────────────── SIGNAL ───────────────────────────

def evaluate(prices: List[float], atr: float, vix: Optional[float], now: dtime,
             prev_day_high: Optional[float] = None,
             prev_day_low: Optional[float] = None,
             daily_bias: str = "UNDEFINED",
             k: int = SWING_K, min_rr: float = MIN_RR,
             open_time: dtime = dtime(9, 45),
             close_time: dtime = dtime(15, 0)) -> PriceActionSignal:
    """
    One decision from the session's price path so far.

    `prices` is the intraday spot path up to and including the decision bar. Only
    that history is read; nothing later exists at this point by construction.
    """
    st = Structure()
    if vix is None or vix <= 0:
        return PriceActionSignal("WAIT", "NO_VIX", structure=st)
    if vix >= MAX_VIX:
        return PriceActionSignal("WAIT", f"VIX_TOO_HIGH {vix:.1f} >= {MAX_VIX}", structure=st)
    if not np.isfinite(atr) or atr <= 0:
        return PriceActionSignal("WAIT", "NO_ATR", structure=st)
    if now < open_time:
        return PriceActionSignal("WAIT", "AWAITING_STRUCTURE — session too young", structure=st)
    if now >= close_time:
        return PriceActionSignal("WAIT", "TOO_LATE_TO_OPEN", structure=st)
    if len(prices) < 2 * k + 6:
        return PriceActionSignal("WAIT", f"INSUFFICIENT_BARS {len(prices)}", structure=st)

    st = read_structure(prices, k)
    price = prices[-1]
    brk, rtst = BREAK_ATR * atr, RETEST_ATR * atr
    resume = RESUME_ATR * atr

    # Previous-day levels are structure too, and they are the levels most other
    # participants are watching. Where one sits beyond the intraday swing it
    # becomes the operative resistance/support.
    if prev_day_high and st.resistance:
        st.resistance = max(st.resistance, prev_day_high) if price < prev_day_high else st.resistance
    if prev_day_low and st.support:
        st.support = min(st.support, prev_day_low) if price > prev_day_low else st.support

    if st.swing_high is None or st.swing_low is None:
        return PriceActionSignal("WAIT", "NO_CONFIRMED_SWINGS", structure=st, atr=atr)

    # ── did price break a level, and how has it behaved since? ──
    # Index of the most recent break, so "since the break" means exactly that.
    recent = prices[-12:]
    up_idx = [i for i, p in enumerate(recent) if p > st.swing_high + brk]
    dn_idx = [i for i, p in enumerate(recent) if p < st.swing_low - brk]
    since_break_up = [recent[i] for i in up_idx]
    since_break_dn = [recent[i] for i in dn_idx]

    if since_break_up:
        peak = max(prices[-12:])
        # Retest: pulled back toward the broken level without surrendering it.
        if price < st.swing_high - rtst:
            return PriceActionSignal(
                "REJECTED", f"FAILED_BREAKOUT — gave back {st.swing_high:.0f}",
                structure=st, breakout_state="FAILED", retest_state="FAILED", atr=atr)
        # Did price actually COME BACK to the level at some point since the break?
        # The retest and the resumption are two events in sequence, not one bar that
        # happens to satisfy both. Checking them on the same bar is what held entries
        # to 5 sessions out of 400 while 74 reached the setup: price would enter the
        # zone on one bar and resume on a later one, and neither bar passed alone.
        # A retest only counts if it happened AFTER the break. Scanning a fixed
        # trailing window would also see the pre-break consolidation, which sits at
        # the level by construction — that would read an extended break that never
        # pulled back as though it had already been retested.
        after_break = recent[up_idx[0] + 1:]
        touched = any(p <= st.swing_high + rtst for p in after_break)
        if touched:
            if REQUIRE_TREND_ALIGNMENT and daily_bias == "DOWNTREND":
                return PriceActionSignal(
                    "WAIT", "COUNTER_STRUCTURE — break up against a DOWNTREND daily bias",
                    structure=st, breakout_state="BROKEN_UP", retest_state="HELD", atr=atr)
            if price >= st.swing_high + resume and price > prices[-2]:
                # The BROKEN LEVEL is the invalidation. That is the entire thesis
                # of trading the retest: if price gives the level back, the idea is
                # wrong. The previous `min(prices[-6:])` was an arbitrary lookback
                # with no structural meaning, and it produced stops so wide that the
                # measured-move target could rarely clear the R:R floor.
                stop = st.swing_high - 0.15 * atr
                risk = price - stop
                if risk <= 0:
                    return PriceActionSignal("WAIT", "DEGENERATE_RISK", structure=st, atr=atr)
                # MEASURED MOVE, not a multiple of the stop. Deriving the target
                # from min_rr would make the R:R test circular — raising the floor
                # would raise the target with it and the check could never bind.
                # The projection is the height of the base that broke, which is a
                # structural quantity the market supplied.
                base_height = max(st.swing_high - st.swing_low, 0.5 * atr)
                target = st.swing_high + base_height
                rr = (target - price) / risk
                if rr < min_rr:
                    return PriceActionSignal(
                        "WAIT", f"RR_BELOW_THRESHOLD {rr:.2f} < {min_rr}",
                        structure=st, breakout_state="BROKEN_UP", retest_state="HELD",
                        risk_reward=round(rr, 2), atr=atr)
                return PriceActionSignal(
                    "LONG_ENTRY",
                    f"BREAK_RETEST_CONTINUATION above {st.swing_high:.0f} "
                    f"({st.trend}) rr={rr:.2f}",
                    direction=1, setup_type="BREAKOUT_RETEST_LONG", structure=st,
                    breakout_state="BROKEN_UP", retest_state="HELD",
                    entry=price, stop=round(stop, 2), target=round(target, 2),
                    risk_reward=round(rr, 2), atr=atr,
                    meta={"peak_since_break": peak, "level": st.swing_high,
                          "daily_bias": daily_bias})
            return PriceActionSignal(
                "LONG_SETUP", f"RETEST_PENDING at {st.swing_high:.0f}, awaiting resumption",
                direction=1, setup_type="BREAKOUT_RETEST_LONG", structure=st,
                breakout_state="BROKEN_UP", retest_state="PENDING", atr=atr)
        return PriceActionSignal(
            "ARMED", f"BROKEN_UP through {st.swing_high:.0f}, extended "
                     f"{price - st.swing_high:.0f} pts — awaiting retest",
            direction=1, structure=st, breakout_state="BROKEN_UP",
            retest_state="NONE", atr=atr)

    if since_break_dn:
        trough = min(prices[-12:])
        if price > st.swing_low + rtst:
            return PriceActionSignal(
                "REJECTED", f"FAILED_BREAKDOWN — reclaimed {st.swing_low:.0f}",
                structure=st, breakout_state="FAILED", retest_state="FAILED", atr=atr)
        after_break = recent[dn_idx[0] + 1:]
        touched = any(p >= st.swing_low - rtst for p in after_break)
        if touched:
            if REQUIRE_TREND_ALIGNMENT and daily_bias == "UPTREND":
                return PriceActionSignal(
                    "WAIT", "COUNTER_STRUCTURE — break down against an UPTREND daily bias",
                    structure=st, breakout_state="BROKEN_DOWN", retest_state="HELD", atr=atr)
            if price <= st.swing_low - resume and price < prices[-2]:
                stop = st.swing_low + 0.15 * atr
                risk = stop - price
                if risk <= 0:
                    return PriceActionSignal("WAIT", "DEGENERATE_RISK", structure=st, atr=atr)
                base_height = max(st.swing_high - st.swing_low, 0.5 * atr)
                target = st.swing_low - base_height
                rr = (price - target) / risk
                if rr < min_rr:
                    return PriceActionSignal(
                        "WAIT", f"RR_BELOW_THRESHOLD {rr:.2f} < {min_rr}",
                        structure=st, breakout_state="BROKEN_DOWN", retest_state="HELD",
                        risk_reward=round(rr, 2), atr=atr)
                return PriceActionSignal(
                    "SHORT_ENTRY",
                    f"BREAK_RETEST_CONTINUATION below {st.swing_low:.0f} "
                    f"({st.trend}) rr={rr:.2f}",
                    direction=-1, setup_type="BREAKDOWN_RETEST_SHORT", structure=st,
                    breakout_state="BROKEN_DOWN", retest_state="HELD",
                    entry=price, stop=round(stop, 2), target=round(target, 2),
                    risk_reward=round(rr, 2), atr=atr,
                    meta={"trough_since_break": trough, "level": st.swing_low,
                          "daily_bias": daily_bias})
            return PriceActionSignal(
                "SHORT_SETUP", f"RETEST_PENDING at {st.swing_low:.0f}, awaiting resumption",
                direction=-1, setup_type="BREAKDOWN_RETEST_SHORT", structure=st,
                breakout_state="BROKEN_DOWN", retest_state="PENDING", atr=atr)
        return PriceActionSignal(
            "ARMED", f"BROKEN_DOWN through {st.swing_low:.0f}, extended "
                     f"{st.swing_low - price:.0f} pts — awaiting retest",
            direction=-1, structure=st, breakout_state="BROKEN_DOWN",
            retest_state="NONE", atr=atr)

    return PriceActionSignal(
        "WAIT",
        f"NO_STRUCTURAL_BREAK — {st.trend}, price {price:.0f} inside "
        f"[{st.swing_low:.0f}, {st.swing_high:.0f}]",
        structure=st, atr=atr)

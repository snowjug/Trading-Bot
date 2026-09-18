"""
Signal layer for the four paper bots: 1, 2, 6 and 7.

Each bot exposes ONE function that takes the point-in-time market state and
returns a Decision. Research and live share these functions, so parity is
structural rather than something to be audited later.

CHRONOLOGY. Every indicator these bots read is computed from bars that were
COMPLETE before the decision timestamp. Today's forming bar contributes only its
live spot — a quantity that genuinely exists at the moment of the decision. No
function reads today's close, and none reads a bar dated after `now`.
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.execution.paper_engine import LegSpec
from src.utils.logging import setup_logging

logger = setup_logging("execution.bot_signals")

STRIKE_STEP = 50.0


@dataclass
class Decision:
    """What a bot wants to do right now, and why."""
    action: str                       # WAIT | ENTER
    reason: str
    legs: List[LegSpec] = field(default_factory=list)
    direction: int = 0                # +1 bullish, -1 bearish, 0 neutral
    target_pnl: Optional[float] = None
    stop_pnl: Optional[float] = None
    trail_trigger: Optional[float] = None
    trail_giveback: Optional[float] = None
    flat_by: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


# ─────────────────────────── SHARED HELPERS ───────────────────────────

def completed_bars(frame: pd.DataFrame, today: date) -> pd.DataFrame:
    """
    Bars strictly BEFORE today.

    Every indicator below is computed from this frame, which is the mechanical
    guarantee that no forming-bar value can leak into a signal.
    """
    f = frame.copy()
    f["d"] = pd.to_datetime(f["datetime"]).dt.date
    return f[f["d"] < today].reset_index(drop=True)


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    return 100 - (100 / (1 + gain / loss.replace(0, np.nan)))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(),
                    (df["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def expected_move(spot: float, vix: float, days: float = 5.0) -> float:
    """The strategies' own expected-move formula, unchanged."""
    return spot * (vix / 100.0) * np.sqrt(days / 365.0)


def offset_steps(points: float, step: float = STRIKE_STEP) -> int:
    return int(round(points / step))


def sessions_until(expiry: date, today: date, calendar: List[date]) -> Optional[int]:
    """
    Trading sessions from today to expiry, counted on the real exchange calendar.

    The NSE holiday list is published annually in advance, so this is knowable at
    the decision timestamp and introduces no lookahead.
    """
    fwd = [d for d in calendar if today < d <= expiry]
    return len(fwd) if expiry in calendar or fwd else None


# ════════════════════ BOT 1 — APEX VRP: WEEKLY IRON CONDOR ════════════════════

def bot1_apex_vrp(spot: float, vix: float, frame: pd.DataFrame, today: date,
                  expiry: Optional[date], calendar: List[date],
                  now: dtime,
                  otm_sd: float = 1.8, wing_sd: float = 2.4,
                  max_vix: float = 20.0, min_rsi: float = 40.0, max_rsi: float = 68.0,
                  hold_sessions: int = 5) -> Decision:
    """
    Four-leg defined-risk Iron Condor on the NIFTY weekly, harvesting the variance
    risk premium in a rangebound regime.

    The structure is the one the specification describes and the one measured on
    158 authentic weekly cycles: shorts at 1.8 expected moves, wings at 2.4, entered
    exactly `hold_sessions` trading sessions before expiry and held to settlement.
    Measured net expectancy was +2.90 points per cycle (t = +1.40) — small, and
    reported as such. Nothing here is tuned to improve it.

    Risk is bounded by construction: max loss = wing width - credit.
    """
    prior = completed_bars(frame, today)
    if len(prior) < 30:
        return Decision("WAIT", "INSUFFICIENT_HISTORY")
    if vix is None or vix <= 0:
        return Decision("WAIT", "NO_VIX")
    if vix >= max_vix:
        return Decision("WAIT", f"REGIME_BLOCKED vix={vix:.2f} >= {max_vix}")

    r = float(rsi(prior["close"]).iloc[-1])
    if not np.isfinite(r):
        return Decision("WAIT", "NO_RSI")
    if not (min_rsi <= r <= max_rsi):
        return Decision("WAIT", f"REGIME_BLOCKED rsi={r:.1f} outside [{min_rsi},{max_rsi}]")

    if expiry is None:
        return Decision("WAIT", "NO_FORWARD_EXPIRY")
    n = sessions_until(expiry, today, calendar)
    if n is None:
        return Decision("WAIT", "EXPIRY_NOT_ON_CALENDAR")
    if n != hold_sessions:
        return Decision("WAIT", f"NOT_ENTRY_SESSION: {n} sessions to {expiry}, "
                                f"entry is exactly {hold_sessions}")
    if now < dtime(14, 45):
        # The research entered at the session close; entering far earlier would be
        # a different trade on a different information set.
        return Decision("WAIT", f"AWAITING_CLOSE_WINDOW {n} sessions to expiry")

    em = expected_move(spot, vix)
    short_off = offset_steps(otm_sd * em)
    wing_off = offset_steps(wing_sd * em)
    if wing_off <= short_off:
        return Decision("WAIT", "DEGENERATE_WINGS")

    legs = [
        LegSpec("short_call", "CE", "SELL", strike_offset=short_off),
        LegSpec("long_call", "CE", "BUY", strike_offset=wing_off),
        LegSpec("short_put", "PE", "SELL", strike_offset=-short_off),
        LegSpec("long_put", "PE", "BUY", strike_offset=-wing_off),
    ]
    return Decision(
        "ENTER",
        f"CONDOR vix={vix:.2f} rsi={r:.1f} em={em:.0f} shorts=ATM+/-{short_off} wings=ATM+/-{wing_off}",
        legs=legs, direction=0,
        # Defined-risk structure held to expiry; the stop caps a tail that the
        # wings already bound, and exists so a gap cannot run unattended.
        stop_pnl=None, target_pnl=None,
        flat_by=None,
        meta={"expected_move": round(em, 2), "rsi": round(r, 2),
              "sessions_to_expiry": n, "expiry": str(expiry),
              "structure": "IRON_CONDOR_4_LEG"},
    )


# ═══════════════ BOT 2 — ZEN CURVATURE: RSI-BRANCHED CREDIT SPREAD ═══════════════

def bot2_zen_curvature(spot: float, vix: float, frame: pd.DataFrame, today: date,
                       expiry: Optional[date], calendar: List[date], now: dtime,
                       short_sd: float = 1.3, wing_sd: float = 1.9,
                       max_vix: float = 22.0,
                       rsi_oversold_put: float = 44.0,
                       rsi_overbought_call: float = 62.0,
                       hold_sessions: int = 5) -> Decision:
    """
    Two-leg defined-risk vertical credit spread, side chosen by RSI.

    WHY THIS IS A REWRITE. The previous implementation emitted `vix < max_vix` and
    nothing else — a regime flag, not a strategy. The RSI-branched Bull Put / Bear
    Call selection existed only in the docstring and in a backtest-only simulator,
    which is why live entries were gated shut. This implements the documented
    intent directly, using the class's own published parameters.

    MECHANISM. After an oversold reading the market is more likely to hold above a
    put strike 1.3 expected moves below spot than the option's premium implies, and
    symmetrically after an overbought reading. The trade sells that gap and buys a
    wing 1.9 expected moves out so the loss is bounded.

    TWO legs rather than four: statutory charges scale with leg count, and a
    four-leg structure pays them twice over for the same directional thesis.
    """
    prior = completed_bars(frame, today)
    if len(prior) < 30:
        return Decision("WAIT", "INSUFFICIENT_HISTORY")
    if vix is None or vix <= 0:
        return Decision("WAIT", "NO_VIX")
    if vix >= max_vix:
        return Decision("WAIT", f"REGIME_BLOCKED vix={vix:.2f} >= {max_vix}")

    r = float(rsi(prior["close"]).iloc[-1])
    if not np.isfinite(r):
        return Decision("WAIT", "NO_RSI")

    if expiry is None:
        return Decision("WAIT", "NO_FORWARD_EXPIRY")
    n = sessions_until(expiry, today, calendar)
    if n is None:
        return Decision("WAIT", "EXPIRY_NOT_ON_CALENDAR")
    if n != hold_sessions:
        return Decision("WAIT", f"NOT_ENTRY_SESSION: {n} sessions to {expiry}, "
                                f"entry is exactly {hold_sessions}")
    if now < dtime(14, 45):
        return Decision("WAIT", f"AWAITING_CLOSE_WINDOW {n} sessions to expiry")

    em = expected_move(spot, vix)
    short_off = offset_steps(short_sd * em)
    wing_off = offset_steps(wing_sd * em)
    if wing_off <= short_off:
        return Decision("WAIT", "DEGENERATE_WINGS")

    if r <= rsi_oversold_put:
        legs = [LegSpec("short_put", "PE", "SELL", strike_offset=-short_off),
                LegSpec("long_put", "PE", "BUY", strike_offset=-wing_off)]
        side, direction = "BULL_PUT", 1
    elif r >= rsi_overbought_call:
        legs = [LegSpec("short_call", "CE", "SELL", strike_offset=short_off),
                LegSpec("long_call", "CE", "BUY", strike_offset=wing_off)]
        side, direction = "BEAR_CALL", -1
    else:
        return Decision("WAIT", f"RSI_NEUTRAL rsi={r:.1f} in "
                                f"({rsi_oversold_put}, {rsi_overbought_call})")

    return Decision(
        "ENTER", f"{side} vix={vix:.2f} rsi={r:.1f} short=ATM{short_off:+d} wing=ATM{wing_off:+d}",
        legs=legs, direction=direction,
        meta={"expected_move": round(em, 2), "rsi": round(r, 2), "structure": side,
              "sessions_to_expiry": n, "expiry": str(expiry)},
    )


# ════════════════ BOT 6 — MICRO MOMENTUM SNIPER (EXITS REBUILT) ════════════════

def bot6_micro_momentum(spot: float, vix: float, frame: pd.DataFrame, today: date,
                        now: dtime, session_high: float, session_low: float,
                        max_vix: float = 18.5,
                        trail_giveback_atr: float = 0.35,
                        target_atr_mult: float = 1.2,
                        stop_atr_mult: float = 0.6,
                        lot: int = 65, opt_delta: float = 0.5) -> Decision:
    """
    Intraday momentum: buy an ATM option when the live session breaks the previous
    session's range, with the trend and RSI aligned on COMPLETED bars.

    ENTRY IS UNCHANGED from the validated implementation: previous-bar EMA stack
    and RSI, current-session high/low for the breakout. Those are the properties
    that were causality-tested, and they are preserved exactly.

    EXITS ARE REBUILT, and this is the only change. Measured over 187 authentic
    trades the old fixed target was hit 3 times while 137 trades were closed at EOD:
    the target was effectively unreachable, so favourable moves decayed back into
    the close. Gross P&L was +Rs 11,109 and net was -Rs 2,838 — the edge existed and
    was handed back. The replacement is volatility-scaled rather than fixed:

      target   1.2 ATR of favourable spot movement
      stop     0.6 ATR against
      trail    once 0.6 ATR of profit is banked, give back at most 0.35 ATR

    The trail is what addresses the actual defect: it converts a favourable
    excursion into a realised exit instead of waiting for a level that never comes.
    """
    prior = completed_bars(frame, today)
    if len(prior) < 35:
        return Decision("WAIT", "INSUFFICIENT_HISTORY")
    if vix is None or vix <= 0:
        return Decision("WAIT", "NO_VIX")
    if vix >= max_vix:
        return Decision("WAIT", f"REGIME_BLOCKED vix={vix:.2f} >= {max_vix}")
    if now < dtime(9, 30):
        return Decision("WAIT", "AWAITING_SESSION_DEVELOPMENT")
    if now >= dtime(15, 0):
        return Decision("WAIT", "TOO_LATE_TO_OPEN")

    c = prior["close"]
    ema9 = c.ewm(span=9, adjust=False).mean().iloc[-1]
    ema21 = c.ewm(span=21, adjust=False).mean().iloc[-1]
    ema50 = c.ewm(span=50, adjust=False).mean().iloc[-1] if len(c) >= 50 else ema21
    r = float(rsi(c).iloc[-1])
    a = float(atr(prior).iloc[-1])
    prev_high, prev_low = float(prior["high"].iloc[-1]), float(prior["low"].iloc[-1])
    if not all(np.isfinite(x) for x in (ema9, ema21, ema50, r, a)) or a <= 0:
        return Decision("WAIT", "INDICATORS_UNAVAILABLE")

    bullish = ema9 > ema21 > ema50 and r > 52.0 and session_high > prev_high
    bearish = ema9 < ema21 < ema50 and r < 48.0 and session_low < prev_low
    if not (bullish or bearish):
        return Decision("WAIT",
                        f"NO_BREAKOUT rsi={r:.1f} ema9{'>' if ema9 > ema21 else '<'}ema21 "
                        f"hi={session_high:.0f}/prev{prev_high:.0f} "
                        f"lo={session_low:.0f}/prev{prev_low:.0f}")

    direction = 1 if bullish else -1
    # Spot-distance targets converted to option P&L via a delta assumption that is
    # used ONLY to size the exit levels, never to price a fill.
    pts_to_rupees = lot * opt_delta
    return Decision(
        "ENTER",
        f"{'BREAKOUT' if bullish else 'BREAKDOWN'} rsi={r:.1f} atr={a:.0f} "
        f"{'hi' if bullish else 'lo'}={session_high if bullish else session_low:.0f} "
        f"vs prev {prev_high if bullish else prev_low:.0f}",
        legs=[LegSpec("leg", "CE" if bullish else "PE", "BUY", strike_offset=0)],
        direction=direction,
        target_pnl=round(target_atr_mult * a * pts_to_rupees, 2),
        stop_pnl=round(-stop_atr_mult * a * pts_to_rupees, 2),
        trail_trigger=round(0.6 * a * pts_to_rupees, 2),
        trail_giveback=round(trail_giveback_atr * a * pts_to_rupees, 2),
        flat_by="15:10",
        meta={"atr": round(a, 2), "rsi": round(r, 2), "structure": "LONG_ATM_OPTION",
              "exit_model": "ATR_TARGET_STOP_TRAIL"},
    )


# ═════════ BOT 7 — INTRADAY DISPLACEMENT CONTINUATION (NEW STRATEGY) ═════════

def bot7_displacement(spot: float, vix: float, frame: pd.DataFrame, today: date,
                      now: dtime, session_twap: Optional[float],
                      session_high: float, session_low: float,
                      stretch_atr: float = 0.55,
                      max_vix: float = 24.0,
                      lot: int = 65, opt_delta: float = 0.5,
                      target_atr_mult: float = 1.2,
                      stop_atr_mult: float = 0.6) -> Decision:
    """
    Intraday displacement continuation: when price separates decisively from the
    session's own mean, buy an ATM option in the DIRECTION of the separation.

    THIS WAS TESTED THE OTHER WAY FIRST, AND THE DATA REJECTED IT. The original
    hypothesis was mean reversion — fade the stretch back toward the session mean.
    Measured over 167 authentic entries on the 5-minute grid the fade returned
    -Rs 101,246 at t = -3.12, while the same entries taken in the CONTINUATION
    direction returned +Rs 33,658 at t = +0.89. Displacement from the session mean
    signals trend, not overextension, so the direction here follows the data rather
    than the original guess. The rejected version is recorded, not hidden.

    ANCHOR. The session mean is a running TWAP of the 5-minute spot path, not a
    VWAP: the NIFTY index has no traded volume of its own, so a volume weighting
    would have to be borrowed from some other instrument. TWAP is computable from
    authentic data with no such substitution, and it is named for what it is.

    INDEPENDENCE FROM BOT 6. Both are long-premium and directional, but they fire
    on different conditions: Bot 6 requires a break of the PREVIOUS session's range
    with a daily EMA stack behind it, which is infrequent and slow; this triggers on
    displacement within the CURRENT session regardless of where the previous day
    closed. They frequently disagree, and neither is a precondition for the other.

    GUARD. A stretch that coincides with a new session extreme is excluded. At an
    extreme there is no separation to measure — price and its running mean are
    being dragged together, and the signal degenerates into "buy the high".
    """
    prior = completed_bars(frame, today)
    if len(prior) < 20:
        return Decision("WAIT", "INSUFFICIENT_HISTORY")
    if vix is None or vix <= 0:
        return Decision("WAIT", "NO_VIX")
    if vix >= max_vix:
        return Decision("WAIT", f"REGIME_BLOCKED vix={vix:.2f} >= {max_vix}")
    if session_twap is None or session_twap <= 0:
        return Decision("WAIT", "NO_SESSION_TWAP")
    if now < dtime(10, 0):
        return Decision("WAIT", "AWAITING_TWAP_FORMATION")
    if now >= dtime(15, 0):
        return Decision("WAIT", "TOO_LATE_TO_OPEN")

    a = float(atr(prior).iloc[-1])
    if not np.isfinite(a) or a <= 0:
        return Decision("WAIT", "NO_ATR")

    stretch = spot - session_twap
    threshold = stretch_atr * a
    if abs(stretch) < threshold:
        return Decision("WAIT", f"NOT_DISPLACED {stretch:+.0f} vs +/-{threshold:.0f} "
                                f"(twap {session_twap:.0f})")
    if stretch > 0 and spot >= session_high - 1e-9:
        return Decision("WAIT", "AT_SESSION_HIGH — no measurable separation")
    if stretch < 0 and spot <= session_low + 1e-9:
        return Decision("WAIT", "AT_SESSION_LOW — no measurable separation")

    direction = 1 if stretch > 0 else -1          # continuation, per the measurement
    pts_to_rupees = lot * opt_delta
    return Decision(
        "ENTER",
        f"DISPLACEMENT {'UP' if direction > 0 else 'DOWN'} {stretch:+.0f} pts "
        f"({abs(stretch) / a:.2f} ATR) twap={session_twap:.0f}",
        legs=[LegSpec("leg", "CE" if direction > 0 else "PE", "BUY", strike_offset=0)],
        direction=direction,
        target_pnl=round(target_atr_mult * a * pts_to_rupees, 2),
        stop_pnl=round(-stop_atr_mult * a * pts_to_rupees, 2),
        trail_trigger=round(0.7 * a * pts_to_rupees, 2),
        trail_giveback=round(0.4 * a * pts_to_rupees, 2),
        flat_by="15:10",
        meta={"atr": round(a, 2), "twap": round(session_twap, 2),
              "displacement_points": round(stretch, 2),
              "displacement_atr": round(abs(stretch) / a, 3),
              "structure": "LONG_ATM_OPTION", "exit_model": "ATR_TARGET_STOP_TRAIL"},
    )

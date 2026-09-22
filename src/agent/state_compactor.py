"""
MarketState -> a compact, human-readable brief + a stable hash.

Two jobs:

1. **Compaction.** The model sees roughly forty lines of already-computed numbers.
   It never sees bars, never sees a dataset, and is never asked to compute an
   indicator. This is the difference between a project that costs a few thousand
   tokens a decision and one that costs a few hundred thousand.

2. **A stable hash.** `state_hash` is computed from the ROUNDED, decision-relevant
   fields, so two bars that are materially identical hash the same and the second
   one is served from cache. Rounding is what makes the cache actually hit: raw
   floats almost never repeat, and an unrounded hash would make the cache useless
   while looking like it worked.

The brief reads like something a trader would write, because that is the form the
model reasons about best — but every number in it came from Python.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from src.market.market_state import MarketState
from src.market.setups import CandidateSetup

PROMPT_VERSION = "agent-brief-v1"


def _f(x: Optional[float], nd: int = 2) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def _tf_line(v) -> str:
    return (f"  {v.tf:<4} close={_f(v.close)} trend={v.trend:<5} stack={v.ema_stack:<7} "
            f"struct={v.structure:<8} rsi={_f(v.rsi14, 1)} atr={_f(v.atr14, 1)} "
            f"slope%={_f(v.slope_fast_pct, 3)}")


def compact(st: MarketState, candidates: List[CandidateSetup],
            options_note: Optional[str] = None,
            position_note: Optional[str] = None) -> str:
    """The brief the model actually receives."""
    L: List[str] = []
    L.append(f"UNDERLYING {st.symbol}   bar {st.bar_time:%Y-%m-%d %H:%M}   "
             f"spot {st.spot:.2f}")
    L.append(f"SESSION    {st.minutes_into_session}m in, {st.minutes_to_close}m to close")
    L.append("")
    L.append("TIMEFRAMES")
    for tf in ("5m", "15m", "30m", "1h", "1d"):
        v = st.views.get(tf)
        if v is not None:
            L.append(_tf_line(v))
    L.append("")
    L.append(f"REGIME     {st.regime_trend} strength={st.regime_strength:.2f} "
             f"vol={st.regime_vol_bucket} htf_alignment={st.htf_alignment:+d}")
    L.append(f"           {st.regime_why}")
    L.append(f"VWAP       {_f(st.vwap)}  price is {_f(st.dist_vwap_pct, 3)}% from it")
    L.append(f"SESSION HL {_f(st.session_high)} / {_f(st.session_low)}   "
             f"open {_f(st.session_open)}  gap {_f(st.gap_pct, 2)}%")
    if st.or_high is not None:
        L.append(f"OPEN RANGE {_f(st.or_high)} / {_f(st.or_low)}")
    if st.prev_day_close is not None:
        L.append(f"PREV DAY   H {_f(st.prev_day_high)} L {_f(st.prev_day_low)} "
                 f"C {_f(st.prev_day_close)}")
    if st.volume_ratio is not None:
        L.append(f"ACTIVITY   option-ladder volume {st.volume_ratio:.2f}x its 20-bar mean")
    if st.india_vix is not None:
        L.append(f"INDIA VIX  {st.india_vix:.2f}")

    c = st.candle or {}
    if c:
        flags = [k.replace("is_", "") for k in
                 ("is_momentum_bar", "is_pin_bar", "is_rejection_up",
                  "is_rejection_down", "is_inside_bar", "is_outside_bar",
                  "is_bullish_engulf", "is_bearish_engulf") if c.get(k)]
        L.append(f"LAST BAR   dir={c.get('direction'):+d} body={_f(c.get('body_frac'))} "
                 f"upper_wick={_f(c.get('upper_wick_frac'))} "
                 f"lower_wick={_f(c.get('lower_wick_frac'))} "
                 f"close_pos={_f(c.get('close_position'))}"
                 + (f"  [{', '.join(flags)}]" if flags else ""))
    b = st.breaks or {}
    if b:
        L.append(f"LEVELS     held-high {_f(b.get('level_high'))} "
                 f"held-low {_f(b.get('level_low'))} "
                 f"(last {b.get('level_lookback')} bars)")
        ev = []
        if b.get("new_break_high"):
            ev.append(f"NEW BREAK ABOVE by {_f(b.get('break_points'), 1)} pts")
        if b.get("new_break_low"):
            ev.append(f"NEW BREAK BELOW by {_f(b.get('break_points'), 1)} pts")
        if b.get("failed_break_high"):
            ev.append("FAILED break above (closed back inside)")
        if b.get("failed_break_low"):
            ev.append("FAILED break below (closed back inside)")
        if ev:
            L.append("           " + "; ".join(ev))

    L.append("")
    L.append("CANDIDATE SETUPS (detected deterministically; you judge them)")
    if not candidates:
        L.append("  none")
    for s in candidates:
        L.append(f"  {s.kind} dir={s.direction:+d} hint={s.quality_hint} "
                 f"level={_f(s.level)} expected_move={_f(s.expected_move_pts, 1)}pts "
                 f"invalidation={_f(s.invalidation)}")
        L.append(f"     because: {', '.join(s.reason_codes)}")

    if options_note:
        L.append("")
        L.append("OPTIONS")
        for ln in options_note.strip().splitlines():
            L.append("  " + ln)
    if position_note:
        L.append("")
        L.append("OPEN POSITION")
        for ln in position_note.strip().splitlines():
            L.append("  " + ln)
    return "\n".join(L)


# Fields that decide the trade. Rounded so that materially identical bars collide
# and the cache actually hits.
def _hash_payload(st: MarketState, candidates: List[CandidateSetup]) -> Dict[str, Any]:
    prim = st.views.get(st.primary_tf)
    b = st.breaks or {}
    c = st.candle or {}
    return {
        "sym": st.symbol,
        "regime": st.regime_trend,
        "strength": round(st.regime_strength, 1),
        "vol": st.regime_vol_bucket,
        "htf": st.htf_alignment,
        "stack": (prim.ema_stack if prim else None),
        "struct": (prim.structure if prim else None),
        "rsi": (round(prim.rsi14 / 5) if (prim and prim.rsi14) else None),
        "vwap_side": (None if st.dist_vwap_pct is None
                      else round(st.dist_vwap_pct, 1)),
        "cand": sorted((s.kind, s.direction, s.quality_hint) for s in candidates),
        "new_hi": bool(b.get("new_break_high")), "new_lo": bool(b.get("new_break_low")),
        "fail_hi": bool(b.get("failed_break_high")),
        "fail_lo": bool(b.get("failed_break_low")),
        "bar_dir": c.get("direction"),
        "mom": bool(c.get("is_momentum_bar")),
        "tod": st.minutes_into_session // 30,      # half-hour bucket
        "prompt": PROMPT_VERSION,
    }


def state_hash(st: MarketState, candidates: List[CandidateSetup]) -> str:
    raw = json.dumps(_hash_payload(st, candidates), sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:20]

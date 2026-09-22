"""
Candidate setup engine — the gate that keeps this project affordable.

It answers one question per bar: "is there anything here worth a second look?"
It never decides to trade. It emits zero or more `CandidateSetup` objects, and only
when at least one exists does the pipeline build a compact state and consult the AI.

Every detector is deterministic and reads only a `MarketState`. Thresholds live in
`configs/market.yaml` and are passed in, so tuning never means editing code.

The six families in the directive, in order:
  A TREND_CONTINUATION      B BREAKOUT            C FAILED_BREAK_REVERSAL
  D VWAP_REVERSION          E VOLATILITY_EXPANSION F OPTIONS_VOL (needs a chain)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.market.market_state import MarketState


@dataclass(frozen=True)
class CandidateSetup:
    kind: str                     # family name
    direction: int                # +1 bullish, -1 bearish, 0 non-directional
    quality_hint: str             # "LOW" | "MEDIUM" | "HIGH" — a hint, not a verdict
    reason_codes: List[str]
    level: Optional[float] = None         # the level that matters, if any
    expected_move_pts: Optional[float] = None
    # The horizon `expected_move_pts` refers to. Without this the number is
    # meaningless: a 250-point daily ATR and a 16-point 5-minute ATR are both "the
    # expected move", and comparing either against an option premium without knowing
    # which one it is produced a real false positive here (see the risk gate).
    expected_move_horizon_minutes: int = 5
    invalidation: Optional[float] = None  # price at which the premise is wrong
    evidence: Dict[str, Any] = field(default_factory=dict)


# One NSE session, 09:15 to 15:30.
SESSION_MINUTES = 375

DEFAULTS: Dict[str, float] = {
    "min_bars_primary": 60,
    "vol_expansion_ratio": 1.40,      # volume vs 20-bar mean
    "break_min_atr_frac": 0.15,       # break must clear the level by this much ATR
    "vwap_stretch_atr": 1.50,         # distance from VWAP in ATR units
    "compression_max": 0.35,          # coiled market
    "trend_strength_min": 0.35,
    "min_minutes_into_session": 15,   # let the open settle
    "min_minutes_to_close": 30,       # do not open into the bell
    "rsi_overbought": 72.0,
    "rsi_oversold": 28.0,
    "expected_move_atr_mult": 1.0,
}


def _cfg(cfg: Optional[Dict[str, float]], k: str) -> float:
    if cfg and k in cfg and cfg[k] is not None:
        return float(cfg[k])
    return float(DEFAULTS[k])


def _timing_ok(st: MarketState, cfg: Optional[Dict[str, float]]) -> bool:
    return (st.in_session
            and st.minutes_into_session >= _cfg(cfg, "min_minutes_into_session")
            and st.minutes_to_close >= _cfg(cfg, "min_minutes_to_close"))


def detect(st: MarketState, cfg: Optional[Dict[str, float]] = None
           ) -> List[CandidateSetup]:
    """All candidates present at this bar. Empty list is the normal, common answer."""
    out: List[CandidateSetup] = []
    prim = st.views.get(st.primary_tf)
    if prim is None or prim.bars < _cfg(cfg, "min_bars_primary"):
        return out
    if not _timing_ok(st, cfg):
        return out

    atr = prim.atr14
    if not atr or atr <= 0:
        return out
    c = st.candle or {}
    b = st.breaks or {}
    vr = st.volume_ratio
    em = atr * _cfg(cfg, "expected_move_atr_mult")

    vol_ok = (vr is not None and vr >= _cfg(cfg, "vol_expansion_ratio"))
    break_clear = _cfg(cfg, "break_min_atr_frac") * atr

    # ── A. TREND CONTINUATION ────────────────────────────────────────────────
    if (st.regime_trend in ("UP", "DOWN")
            and st.regime_strength >= _cfg(cfg, "trend_strength_min")):
        d = 1 if st.regime_trend == "UP" else -1
        aligned = (st.htf_alignment >= 1) if d > 0 else (st.htf_alignment <= -1)
        vwap_side = (st.dist_vwap_pct is not None
                     and ((d > 0 and st.dist_vwap_pct > 0)
                          or (d < 0 and st.dist_vwap_pct < 0)))
        codes = [f"REGIME_{st.regime_trend}", f"EMA_STACK_{prim.ema_stack}",
                 f"STRUCTURE_{prim.structure}"]
        if aligned:
            codes.append("HTF_TREND_ALIGNED")
        if vwap_side:
            codes.append("VWAP_SIDE_CONFIRMS")
        if vol_ok:
            codes.append("VOLUME_EXPANSION")
        if c.get("is_momentum_bar") and c.get("direction") == d:
            codes.append("MOMENTUM_BAR")
        # A standing trend is a CONTEXT, not an event. Require a trigger on this
        # bar as well, otherwise every bar of a trend is a "setup".
        trigger = bool(c.get("is_momentum_bar")) or bool(b.get("new_break_high") if d > 0
                                                         else b.get("new_break_low"))
        score = sum([aligned, vwap_side, vol_ok, bool(c.get("is_momentum_bar"))])
        if trigger and score >= 2:
            out.append(CandidateSetup(
                kind="TREND_CONTINUATION", direction=d,
                quality_hint=("HIGH" if score >= 3 else "MEDIUM"),
                reason_codes=codes, level=st.vwap, expected_move_pts=round(em, 1),
                expected_move_horizon_minutes=5,
                invalidation=(prim.swing_low if d > 0 else prim.swing_high),
                evidence={"regime_strength": st.regime_strength,
                          "htf_alignment": st.htf_alignment, "volume_ratio": vr}))

    # ── B. BREAKOUT ──────────────────────────────────────────────────────────
    # Requires a NEW break (the bar that crosses) of a level that HAS HELD for
    # `level_lookback` bars. Without the transition requirement the same breakout
    # re-signals on every subsequent bar and the gate fires on a third of all bars.
    bp = b.get("break_points")
    if b.get("new_break_high") and bp is not None and bp >= break_clear:
        codes = ["BREAKOUT_HIGH", f"CLEARED_{bp:.0f}PTS"]
        if vol_ok:
            codes.append("VOLUME_EXPANSION")
        if prim.compression is not None and prim.compression <= _cfg(cfg, "compression_max"):
            codes.append("FROM_COMPRESSION")
        if st.htf_alignment >= 1:
            codes.append("HTF_TREND_ALIGNED")
        if vol_ok or "FROM_COMPRESSION" in codes:
            out.append(CandidateSetup(
                kind="BREAKOUT", direction=1,
                quality_hint=("HIGH" if (vol_ok and st.htf_alignment >= 1) else "MEDIUM"),
                reason_codes=codes, level=b.get("level_high"),
                expected_move_pts=round(em, 1), expected_move_horizon_minutes=5,
                invalidation=b.get("level_high"),
                evidence={"break_points": bp, "volume_ratio": vr,
                          "compression": prim.compression}))
    if b.get("new_break_low") and bp is not None and bp >= break_clear:
        codes = ["BREAKDOWN_LOW", f"CLEARED_{bp:.0f}PTS"]
        if vol_ok:
            codes.append("VOLUME_EXPANSION")
        if prim.compression is not None and prim.compression <= _cfg(cfg, "compression_max"):
            codes.append("FROM_COMPRESSION")
        if st.htf_alignment <= -1:
            codes.append("HTF_TREND_ALIGNED")
        if vol_ok or "FROM_COMPRESSION" in codes:
            out.append(CandidateSetup(
                kind="BREAKOUT", direction=-1,
                quality_hint=("HIGH" if (vol_ok and st.htf_alignment <= -1) else "MEDIUM"),
                reason_codes=codes, level=b.get("level_low"),
                expected_move_pts=round(em, 1), expected_move_horizon_minutes=5,
                invalidation=b.get("level_low"),
                evidence={"break_points": bp, "volume_ratio": vr,
                          "compression": prim.compression}))

    # ── C. FAILED BREAK / REVERSAL ───────────────────────────────────────────
    if b.get("failed_break_high") and (c.get("is_rejection_up") or c.get("is_pin_bar")):
        out.append(CandidateSetup(
            kind="FAILED_BREAK_REVERSAL", direction=-1, quality_hint="MEDIUM",
            reason_codes=["FAILED_BREAK_HIGH", "UPPER_WICK_REJECTION"],
            level=b.get("level_high"), expected_move_pts=round(em, 1),
            expected_move_horizon_minutes=5, invalidation=st.session_high,
            evidence={"upper_wick_frac": c.get("upper_wick_frac"),
                      "close_position": c.get("close_position")}))
    if b.get("failed_break_low") and (c.get("is_rejection_down") or c.get("is_pin_bar")):
        out.append(CandidateSetup(
            kind="FAILED_BREAK_REVERSAL", direction=1, quality_hint="MEDIUM",
            reason_codes=["FAILED_BREAK_LOW", "LOWER_WICK_REJECTION"],
            level=b.get("level_low"), expected_move_pts=round(em, 1),
            expected_move_horizon_minutes=5, invalidation=st.session_low,
            evidence={"lower_wick_frac": c.get("lower_wick_frac"),
                      "close_position": c.get("close_position")}))

    # ── D. VWAP REVERSION ────────────────────────────────────────────────────
    if st.vwap and st.dist_vwap_pct is not None:
        stretch_pts = abs(st.spot - st.vwap)
        if stretch_pts >= _cfg(cfg, "vwap_stretch_atr") * atr and st.regime_trend == "RANGE":
            d = -1 if st.spot > st.vwap else 1
            rsi_extreme = (prim.rsi14 is not None and
                           ((d < 0 and prim.rsi14 >= _cfg(cfg, "rsi_overbought"))
                            or (d > 0 and prim.rsi14 <= _cfg(cfg, "rsi_oversold"))))
            rejecting = (c.get("is_rejection_up") if d < 0 else c.get("is_rejection_down"))
            if (rsi_extreme or rejecting) and c.get("direction") == d:
                out.append(CandidateSetup(
                    kind="VWAP_REVERSION", direction=d,
                    quality_hint=("MEDIUM" if (rsi_extreme and rejecting) else "LOW"),
                    reason_codes=["RANGE_REGIME", "VWAP_STRETCH",
                                  *(["RSI_EXTREME"] if rsi_extreme else []),
                                  *(["REJECTION_CANDLE"] if rejecting else [])],
                    level=st.vwap, expected_move_pts=round(stretch_pts * 0.6, 1),
                    expected_move_horizon_minutes=30,
                    invalidation=(st.session_high if d < 0 else st.session_low),
                    evidence={"dist_vwap_pct": st.dist_vwap_pct, "rsi14": prim.rsi14,
                              "stretch_atr": round(stretch_pts / atr, 2)}))

    # ── E. VOLATILITY EXPANSION (non-directional) ────────────────────────────
    if (prim.compression is not None
            and prim.compression <= _cfg(cfg, "compression_max") and vol_ok):
        out.append(CandidateSetup(
            kind="VOLATILITY_EXPANSION", direction=0, quality_hint="MEDIUM",
            reason_codes=["COMPRESSION", "VOLUME_EXPANSION"],
            level=st.spot, expected_move_pts=round(em * 1.5, 1),
            expected_move_horizon_minutes=15, invalidation=None,
            evidence={"compression": prim.compression, "volume_ratio": vr,
                      "vol_bucket": st.regime_vol_bucket}))

    return out


def options_vol_setup(st: MarketState, atm_straddle_pts: Optional[float],
                      iv_atm: Optional[float], cfg: Optional[Dict[str, float]] = None
                      ) -> Optional[CandidateSetup]:
    """
    Family F. Needs an authentic chain snapshot, so it is separate: the caller
    supplies the ATM straddle price and ATM IV, or nothing happens.

    The comparison is the option market's own expected move (the straddle) against
    the realised move the index has actually been making. A straddle far above
    realised favours the seller; far below favours the buyer. Both are only
    CANDIDATES — the risk boundary still has to clear the structure on cost.
    """
    prim = st.views.get(st.primary_tf)
    if prim is None or atm_straddle_pts is None or atm_straddle_pts <= 0:
        return None
    day = st.views.get("1d")
    ref_atr = (day.atr14 if (day and day.atr14) else (prim.atr14 or 0) * 4.0)
    if not ref_atr or ref_atr <= 0:
        return None
    ratio = atm_straddle_pts / ref_atr
    if ratio >= 1.30:
        return CandidateSetup(
            kind="OPTIONS_VOL_RICH", direction=0, quality_hint="MEDIUM",
            reason_codes=["STRADDLE_ABOVE_REALISED", f"RATIO_{ratio:.2f}"],
            level=st.spot, expected_move_pts=round(ref_atr, 1),
            expected_move_horizon_minutes=SESSION_MINUTES, invalidation=None,
            evidence={"atm_straddle_pts": atm_straddle_pts, "daily_atr": ref_atr,
                      "ratio": round(ratio, 3), "iv_atm": iv_atm})
    if ratio <= 0.75:
        return CandidateSetup(
            kind="OPTIONS_VOL_CHEAP", direction=0, quality_hint="MEDIUM",
            reason_codes=["STRADDLE_BELOW_REALISED", f"RATIO_{ratio:.2f}"],
            level=st.spot, expected_move_pts=round(ref_atr, 1),
            expected_move_horizon_minutes=SESSION_MINUTES, invalidation=None,
            evidence={"atm_straddle_pts": atm_straddle_pts, "daily_atr": ref_atr,
                      "ratio": round(ratio, 3), "iv_atm": iv_atm})
    return None

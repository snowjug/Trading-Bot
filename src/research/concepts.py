"""
THIRTY DISTINCT STRATEGY CONCEPTS for the 6-month money study.

Each is a deterministic rule set with a stated mechanism. Signals return a Setup
carrying SPOT levels, so reward/risk is a property of the setup rather than a
tuned constant. Nothing here reads a future bar: every quantity comes from
`Ctx2`, which exposes only bars 0..i of the session and daily rows strictly
before it.

EXTERNAL SOURCES, reduced to explicit rules. Claims are recorded as claims.

  ORB family  — Opening Range Breakout is public domain; the specific framing used
    here (OR from 09:15, stop at the opposite side of the range, fixed-R target,
    square-off before close, large-range sessions favoured) follows the publicly
    documented NIFTY/BankNifty write-ups listed in the report. Their headline
    figures are NOT carried over; only the rules are.

  VWAP pullback — the widely published continuation framing: trade with the side
    of the anchor, enter on a pullback to it, stop through it, target 1.5-2R.
    Adapted: this dataset has no index volume, so the anchor is either session
    TWAP or spot weighted by CE+PE option volume. Both are named honestly.

  Market Intraday Momentum — Gao, Han, Li & Zhou, "Market intraday momentum",
    Journal of Financial Economics 2018 (SSRN 2440866). Finding: the first
    half-hour return predicts the last half-hour return (scaled slope 6.94,
    significant at 1%, R^2 1.6% on SPY 1993-2013), stronger on high-volatility
    and high-volume days. Mechanism offered: day-trader and informed-trader flow.
    Adapted to NIFTY: first half-hour is 09:15-09:45 measured from the previous
    close; the last half-hour trade is entered at 15:00 and squared off at 15:20,
    because this dataset stops at 15:25 and the close auction is not modelled.
    Unchanged: the sign rule, the conditioning variables, the timed exit.
    Risk: the original is a US equity-index ETF over 1993-2013; nothing about it
    guarantees an Indian index in 2020-2026, which is exactly what is measured.
"""

from datetime import time as dtime
from typing import Optional

import numpy as np

from src.research.lab2 import Ctx2, Setup, Spec2


# ───────────────────────── helpers ─────────────────────────

def _tgt(entry: float, stop: float, direction: int, rr: float) -> float:
    return entry + (entry - stop) * rr * 0 + direction * abs(entry - stop) * rr


def _mk(direction: int, entry: float, stop: float, rr: float, tag: str,
        off: int = 0, hold: Optional[int] = None) -> Optional[Setup]:
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    return Setup(direction=direction, stop=stop,
                 target=entry + direction * risk * rr, tag=tag,
                 strike_offset=off, max_hold_bars=hold)


def _broke_above(c: Ctx2, level: float) -> bool:
    return bool(np.any(c.path > level))


def _broke_below(c: Ctx2, level: float) -> bool:
    return bool(np.any(c.path < level))


def _first_cross_idx(c: Ctx2, level: float, up: bool) -> Optional[int]:
    w = np.where(c.path > level)[0] if up else np.where(c.path < level)[0]
    return int(w[0]) if len(w) else None


# ═════════════════ A. OPENING RANGE BREAKOUT ═════════════════

def orb(which: str = "15", rr: float = 1.5, buf_pts: float = 0.0,
        need_stack: bool = False, need_anchor: bool = False,
        min_range_pct: float = 0.0, max_range_pct: float = 1e9,
        stop_mode: str = "opposite", off: int = 0):
    """Break of the opening range, stop at the other side of that range."""
    def sig(c: Ctx2) -> Optional[Setup]:
        hi, lo = (c.or_hi, c.or_lo) if which == "15" else (c.or30_hi, c.or30_lo)
        if not np.isfinite(hi) or not np.isfinite(lo) or hi <= lo:
            return None
        rng = hi - lo
        rp = rng / c.spot * 100
        if not (min_range_pct <= rp <= max_range_pct):
            return None
        anchor = c.vwap_opt
        if c.spot > hi + buf_pts:
            if need_stack and c.ema_stack < 0:
                return None
            if need_anchor and c.spot < anchor:
                return None
            stop = lo if stop_mode == "opposite" else c.spot - rng * 0.5
            return _mk(+1, c.spot, stop, rr, f"ORB{which}_up", off)
        if c.spot < lo - buf_pts:
            if need_stack and c.ema_stack > 0:
                return None
            if need_anchor and c.spot > anchor:
                return None
            stop = hi if stop_mode == "opposite" else c.spot + rng * 0.5
            return _mk(-1, c.spot, stop, rr, f"ORB{which}_dn", off)
        return None
    return sig


def orb_retest(which: str = "15", rr: float = 2.0, near_pts: float = 15.0):
    """Break the range, return to the level, then resume. Entry on the resume bar."""
    def sig(c: Ctx2) -> Optional[Setup]:
        hi, lo = (c.or_hi, c.or_lo) if which == "15" else (c.or30_hi, c.or30_lo)
        if not np.isfinite(hi) or not np.isfinite(lo) or hi <= lo:
            return None
        bi = _first_cross_idx(c, hi, up=True)
        if bi is not None and bi < c.i:
            after = c.path[bi:c.i + 1]
            if after.min() <= hi + near_pts and c.spot > hi and c.spot > c.path[c.i - 1]:
                return _mk(+1, c.spot, min(hi - near_pts, after.min() - 2), rr, "ORB_retest_up")
        si = _first_cross_idx(c, lo, up=False)
        if si is not None and si < c.i:
            after = c.path[si:c.i + 1]
            if after.max() >= lo - near_pts and c.spot < lo and c.spot < c.path[c.i - 1]:
                return _mk(-1, c.spot, max(lo + near_pts, after.max() + 2), rr, "ORB_retest_dn")
        return None
    return sig


def orb_fade(which: str = "15", rr: float = 1.5):
    """Failed breakout: price broke the range and has closed back inside it."""
    def sig(c: Ctx2) -> Optional[Setup]:
        hi, lo = (c.or_hi, c.or_lo) if which == "15" else (c.or30_hi, c.or30_lo)
        if not np.isfinite(hi) or not np.isfinite(lo) or hi <= lo:
            return None
        if _broke_above(c, hi) and lo < c.spot < hi:
            return _mk(-1, c.spot, float(c.path.max()) + 2, rr, "ORB_fade_dn")
        if _broke_below(c, lo) and lo < c.spot < hi:
            return _mk(+1, c.spot, float(c.path.min()) - 2, rr, "ORB_fade_up")
        return None
    return sig


# ═════════════════ B. PREVIOUS-DAY LEVELS ═════════════════

def pd_break(rr: float = 1.5, buf: float = 0.0):
    def sig(c: Ctx2) -> Optional[Setup]:
        if c.spot > c.prev_high + buf and not _broke_below(c, c.prev_low):
            return _mk(+1, c.spot, max(c.prev_high - c.atr * 0.25, c.sess_lo), rr, "PDH_break")
        if c.spot < c.prev_low - buf and not _broke_above(c, c.prev_high):
            return _mk(-1, c.spot, min(c.prev_low + c.atr * 0.25, c.sess_hi), rr, "PDL_break")
        return None
    return sig


def pd_fade(rr: float = 1.5):
    def sig(c: Ctx2) -> Optional[Setup]:
        if c.spot > c.prev_high and c.spot < float(c.path.max()):
            return _mk(-1, c.spot, float(c.path.max()) + 2, rr, "PDH_fade")
        if c.spot < c.prev_low and c.spot > float(c.path.min()):
            return _mk(+1, c.spot, float(c.path.min()) - 2, rr, "PDL_fade")
        return None
    return sig


# ═════════════════ C. GAP ═════════════════

def gap_go(rr: float = 1.5, lo_pct: float = 0.3, hi_pct: float = 3.0):
    def sig(c: Ctx2) -> Optional[Setup]:
        g = c.gap_pct
        if not np.isfinite(g) or not (lo_pct <= abs(g) <= hi_pct):
            return None
        d = 1 if g > 0 else -1
        if d > 0 and c.spot > c.or_hi:
            return _mk(+1, c.spot, c.or_lo, rr, "gap_go_up")
        if d < 0 and c.spot < c.or_lo:
            return _mk(-1, c.spot, c.or_hi, rr, "gap_go_dn")
        return None
    return sig


def gap_fade(rr: float = 1.5, lo_pct: float = 0.4, hi_pct: float = 3.0):
    def sig(c: Ctx2) -> Optional[Setup]:
        g = c.gap_pct
        if not np.isfinite(g) or not (lo_pct <= abs(g) <= hi_pct):
            return None
        if g > 0 and c.spot < c.or_lo:
            return _mk(-1, c.spot, float(c.path.max()) + 2, rr, "gap_fade_dn")
        if g < 0 and c.spot > c.or_hi:
            return _mk(+1, c.spot, float(c.path.min()) - 2, rr, "gap_fade_up")
        return None
    return sig


# ═════════════════ D. ANCHOR (TWAP / option-volume-weighted) ═════════════════

def anchor_pullback(rr: float = 2.0, anchor: str = "vwap_opt",
                    near_atr: float = 0.06, min_ext_atr: float = 0.15):
    """Trend side taken from the anchor; entry on a pullback to it; stop through it."""
    def sig(c: Ctx2) -> Optional[Setup]:
        a = c.vwap_opt if anchor == "vwap_opt" else c.twap
        if c.i < 12:
            return None
        ext = (c.path.max() - a) if c.spot >= a else (a - c.path.min())
        if ext < min_ext_atr * c.atr:
            return None
        near = abs(c.spot - a) <= near_atr * c.atr
        if not near:
            return None
        up = c.path[:c.i + 1].max() - a > a - c.path[:c.i + 1].min()
        if up and c.spot >= a and c.spot > c.path[c.i - 1]:
            return _mk(+1, c.spot, a - near_atr * c.atr, rr, f"{anchor}_pb_up")
        if not up and c.spot <= a and c.spot < c.path[c.i - 1]:
            return _mk(-1, c.spot, a + near_atr * c.atr, rr, f"{anchor}_pb_dn")
        return None
    return sig


def anchor_revert(rr: float = 1.0, ext_atr: float = 0.35):
    """Fade an extension away from the session anchor."""
    def sig(c: Ctx2) -> Optional[Setup]:
        a = c.vwap_opt
        if c.i < 12:
            return None
        d = c.spot - a
        if d >= ext_atr * c.atr:
            return _mk(-1, c.spot, c.spot + 0.5 * abs(d), rr, "revert_dn")
        if d <= -ext_atr * c.atr:
            return _mk(+1, c.spot, c.spot - 0.5 * abs(d), rr, "revert_up")
        return None
    return sig


# ═════════════════ E. MARKET INTRADAY MOMENTUM (Gao/Han/Li/Zhou) ═════════════════

def mim(stop_atr: float = 0.50, tgt_atr: float = 1.00, min_abs_ret: float = 0.0,
        hi_vol_only: bool = False, hi_rvol_only: bool = False,
        use_penultimate: bool = False):
    """
    Sign of the first half-hour return (or of the 14:30-15:00 return) sets the
    side of a timed last-half-hour trade. The protective stop is an adaptation for
    risk control, not part of the original paper; the dominant exit is the clock.
    """
    def sig(c: Ctx2) -> Optional[Setup]:
        if use_penultimate:
            j = [k for k, tt in enumerate(c.times[:c.i + 1]) if tt <= dtime(14, 30)]
            if not j:
                return None
            r = (c.spot - float(c.path[j[-1]])) / float(c.path[j[-1]]) * 100
        else:
            r = c.first30_ret
        if not np.isfinite(r) or abs(r) < min_abs_ret:
            return None
        if hi_vol_only and c.prev_range_pct <= c.range20:
            return None
        if hi_rvol_only and c.rel_vol(6) < 1.0:
            return None
        d = 1 if r > 0 else -1
        return Setup(direction=d, stop=c.spot - d * stop_atr * c.atr,
                     target=c.spot + d * tgt_atr * c.atr,
                     tag=f"MIM_{'pen' if use_penultimate else 'first30'}_{'up' if d>0 else 'dn'}")
    return sig


# ═════════════════ F. TREND / CHANNEL ═════════════════

def donchian(n: int = 20, rr: float = 1.5, need_stack: bool = False):
    def sig(c: Ctx2) -> Optional[Setup]:
        if c.i < n + 2:
            return None
        w = c.path[c.i - n:c.i]
        hi, lo = float(w.max()), float(w.min())
        if c.spot > hi:
            if need_stack and c.ema_stack < 0:
                return None
            return _mk(+1, c.spot, lo, rr, f"donch{n}_up")
        if c.spot < lo:
            if need_stack and c.ema_stack > 0:
                return None
            return _mk(-1, c.spot, hi, rr, f"donch{n}_dn")
        return None
    return sig


def trend_pullback(rr: float = 2.0, pb_atr: float = 0.20):
    """Daily EMA stack sets the side; entry after an intraday pullback resumes."""
    def sig(c: Ctx2) -> Optional[Setup]:
        if c.ema_stack == 0 or c.i < 10:
            return None
        d = c.ema_stack
        if d > 0:
            pk = float(c.path.max())
            if pk - c.spot >= pb_atr * c.atr and c.spot > c.path[c.i - 1]:
                return _mk(+1, c.spot, float(c.path[c.i - 4:c.i + 1].min()) - 2, rr, "trend_pb_up")
        else:
            tr = float(c.path.min())
            if c.spot - tr >= pb_atr * c.atr and c.spot < c.path[c.i - 1]:
                return _mk(-1, c.spot, float(c.path[c.i - 4:c.i + 1].max()) + 2, rr, "trend_pb_dn")
        return None
    return sig


# ═════════════════ G. VOLATILITY ═════════════════

def compression_break(rr: float = 2.0, max_or_pct: float = 0.30):
    """A first hour that is unusually quiet, then the first decisive break of it."""
    def sig(c: Ctx2) -> Optional[Setup]:
        j = [k for k, tt in enumerate(c.times[:c.i + 1]) if tt < dtime(10, 15)]
        if not j or c.times[c.i] < dtime(10, 15):
            return None
        w = c.path[j]
        hi, lo = float(w.max()), float(w.min())
        if (hi - lo) / c.spot * 100 > max_or_pct:
            return None
        if c.spot > hi:
            return _mk(+1, c.spot, lo, rr, "compress_up")
        if c.spot < lo:
            return _mk(-1, c.spot, hi, rr, "compress_dn")
        return None
    return sig


def range_expansion(rr: float = 1.5, k: float = 1.8, look: int = 6):
    """A bar-to-bar move far larger than the session's own recent average."""
    def sig(c: Ctx2) -> Optional[Setup]:
        if c.i < look + 2:
            return None
        steps = np.abs(np.diff(c.path[:c.i + 1]))
        if len(steps) < look + 1:
            return None
        cur, base = steps[-1], steps[:-1].mean()
        if base <= 0 or cur < k * base:
            return None
        d = 1 if c.path[c.i] > c.path[c.i - 1] else -1
        return _mk(d, c.spot, c.spot - d * cur * 1.2, rr, "range_exp")
    return sig


def vix_band_orb(rr: float = 1.5, lo: float = 10.0, hi: float = 18.0):
    def base(c: Ctx2) -> Optional[Setup]:
        if not (lo <= c.vix < hi):
            return None
        return orb("15", rr)(c)
    return base


# ═════════════════ H. MEAN REVERSION ═════════════════

def session_extreme_fade(rr: float = 1.0, z: float = 1.6):
    def sig(c: Ctx2) -> Optional[Setup]:
        if c.i < 20:
            return None
        mu, sd = float(c.path.mean()), float(c.path.std(ddof=1))
        if sd <= 0:
            return None
        zz = (c.spot - mu) / sd
        if zz >= z:
            return _mk(-1, c.spot, float(c.path.max()) + 3, rr, "zfade_dn")
        if zz <= -z:
            return _mk(+1, c.spot, float(c.path.min()) - 3, rr, "zfade_up")
        return None
    return sig


def rsi_extreme_revert(rr: float = 1.0, lo: float = 32.0, hi: float = 68.0):
    def sig(c: Ctx2) -> Optional[Setup]:
        if c.i < 12:
            return None
        if c.rsi <= lo and c.spot > c.path[c.i - 1]:
            return _mk(+1, c.spot, float(c.path.min()) - 3, rr, "rsi_rev_up")
        if c.rsi >= hi and c.spot < c.path[c.i - 1]:
            return _mk(-1, c.spot, float(c.path.max()) + 3, rr, "rsi_rev_dn")
        return None
    return sig


# ═════════════════ I. LIQUIDITY / STRUCTURE ═════════════════

def liquidity_sweep(rr: float = 2.0, which: str = "15"):
    """Range extreme is taken out and then reclaimed — the stop-run reversal."""
    def sig(c: Ctx2) -> Optional[Setup]:
        hi, lo = (c.or_hi, c.or_lo) if which == "15" else (c.or30_hi, c.or30_lo)
        if not np.isfinite(hi) or not np.isfinite(lo):
            return None
        si = _first_cross_idx(c, lo, up=False)
        if si is not None and si < c.i and c.spot > lo:
            trough = float(c.path[si:c.i + 1].min())
            if c.spot > c.path[c.i - 1]:
                return _mk(+1, c.spot, trough - 2, rr, "sweep_up")
        bi = _first_cross_idx(c, hi, up=True)
        if bi is not None and bi < c.i and c.spot < hi:
            peak = float(c.path[bi:c.i + 1].max())
            if c.spot < c.path[c.i - 1]:
                return _mk(-1, c.spot, peak + 2, rr, "sweep_dn")
        return None
    return sig


def structure_break(rr: float = 2.0, k: int = 3):
    """
    Confirmed swing structure, then a break of the last confirmed swing.
    A swing at j needs k bars either side, so it is only ever read from bars
    strictly older than i-k. No forming swing is used.
    """
    def sig(c: Ctx2) -> Optional[Setup]:
        p = c.path
        n = len(p)
        if n < 4 * k + 4:
            return None
        hs, ls = [], []
        for j in range(k, n - k - 1):
            w = p[j - k:j + k + 1]
            if p[j] == w.max():
                hs.append(j)
            if p[j] == w.min():
                ls.append(j)
        if not hs or not ls:
            return None
        lh, ll = hs[-1], ls[-1]
        if c.spot > p[lh] and lh > ll:
            return _mk(+1, c.spot, float(p[ll]) - 2, rr, "bos_up")
        if c.spot < p[ll] and ll > lh:
            return _mk(-1, c.spot, float(p[lh]) + 2, rr, "bos_dn")
        return None
    return sig


# ═════════════════ J. OPTION-CONDITIONED ═════════════════

def expiry_only(inner, expiry_days):
    def sig(c: Ctx2) -> Optional[Setup]:
        return inner(c) if c.sess in expiry_days else None
    return sig


def non_expiry_only(inner, expiry_days):
    def sig(c: Ctx2) -> Optional[Setup]:
        return None if c.sess in expiry_days else inner(c)
    return sig


def vix_filtered(inner, lo: float, hi: float):
    def sig(c: Ctx2) -> Optional[Setup]:
        return inner(c) if lo <= c.vix < hi else None
    return sig

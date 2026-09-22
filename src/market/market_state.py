"""
MarketState — the one canonical snapshot of the market at a decision bar.

CAUSALITY IS ENFORCED HERE, and only here. `build_state` takes frames and a
`bar_time`, truncates every frame to bars closing at or before `bar_time`, and
builds features from the truncated frames. Nothing downstream can reach past it,
because nothing downstream receives raw bars.

The object carries three provenance fields, and the replay engine asserts them:

    bar_time            close of the decision bar
    data_available_at   the earliest moment this state could have been observed
    source              where the bars came from

There is deliberately NO field whose name begins with `fwd`. `assert_no_lookahead`
checks that, so a future column cannot be added by accident.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, time as dtime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.market import indicators as I
from src.market.candles import CandleFeatures, candle_features
from src.market.regime import Regime, classify
from src.market.structure import (
    BreakState, Levels, Swing, break_state, compression, is_new_break,
    opening_range, significant_levels, structure_label, swings,
)

# NSE equity/derivative session, IST.
SESSION_OPEN = dtime(9, 15)
SESSION_CLOSE = dtime(15, 30)


@dataclass(frozen=True)
class TimeframeView:
    """Per-timeframe features. Every value is None when there are too few bars."""
    tf: str
    bars: int
    close: Optional[float]
    ema5: Optional[float] = None
    ema9: Optional[float] = None
    ema21: Optional[float] = None
    ema31: Optional[float] = None
    ema50: Optional[float] = None
    sma20: Optional[float] = None
    sma50: Optional[float] = None
    rsi14: Optional[float] = None
    atr14: Optional[float] = None
    roc5: Optional[float] = None
    slope_fast_pct: Optional[float] = None
    realized_vol: Optional[float] = None
    dist_ema21_pct: Optional[float] = None
    dist_sma50_pct: Optional[float] = None
    ema_stack: str = "UNKNOWN"          # "BULL" | "BEAR" | "MIXED"
    structure: str = "UNKNOWN"
    consecutive: int = 0
    compression: Optional[float] = None
    swing_high: Optional[float] = None
    swing_low: Optional[float] = None
    trend: str = "RANGE"


@dataclass(frozen=True)
class MarketState:
    # ── provenance ──
    symbol: str
    bar_time: datetime
    data_available_at: datetime
    source: str

    # ── spot / session ──
    spot: float
    session_date: Any
    minutes_into_session: int
    minutes_to_close: int
    in_session: bool

    # ── primary timeframe (5m) ──
    primary_tf: str
    views: Dict[str, TimeframeView]

    # ── session aggregates ──
    session_open: Optional[float] = None
    session_high: Optional[float] = None
    session_low: Optional[float] = None
    vwap: Optional[float] = None
    dist_vwap_pct: Optional[float] = None
    volume_ratio: Optional[float] = None
    or_high: Optional[float] = None
    or_low: Optional[float] = None
    gap_pct: Optional[float] = None

    prev_day_high: Optional[float] = None
    prev_day_low: Optional[float] = None
    prev_day_close: Optional[float] = None

    # ── candle + breaks on the primary timeframe ──
    candle: Optional[Dict[str, Any]] = None
    breaks: Optional[Dict[str, Any]] = None

    # ── regime ──
    regime_trend: str = "RANGE"
    regime_strength: float = 0.0
    regime_vol_bucket: str = "MEDIUM"
    regime_why: str = ""
    htf_alignment: int = 0      # -3..+3, how many higher timeframes agree

    # ── volatility context ──
    india_vix: Optional[float] = None

    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["views"] = {k: asdict(v) for k, v in self.views.items()}
        return d


FORBIDDEN_PREFIXES = ("fwd", "future_", "next_", "settle")


def assert_no_lookahead(st: MarketState) -> None:
    """
    A state must not carry any field that could only be known later. Checked
    structurally so a careless addition fails loudly instead of quietly biasing a
    backtest.
    """
    bad = [k for k in st.to_dict() if k.lower().startswith(FORBIDDEN_PREFIXES)]
    if bad:
        raise AssertionError(f"MarketState carries forward-looking fields: {bad}")
    for name, v in st.views.items():
        vb = [k for k in asdict(v) if k.lower().startswith(FORBIDDEN_PREFIXES)]
        if vb:
            raise AssertionError(f"TimeframeView[{name}] carries forward fields: {vb}")
    if st.data_available_at < st.bar_time:
        raise AssertionError(
            f"data_available_at {st.data_available_at} precedes bar_time {st.bar_time}")


def _truncate(df: pd.DataFrame, bar_time: datetime) -> pd.DataFrame:
    """Bars whose close is at or before the decision bar. This is the causality gate."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["datetime", "open", "high", "low", "close", "volume"])
    d = df.copy()
    d["datetime"] = pd.to_datetime(d["datetime"])
    return d[d["datetime"] <= pd.Timestamp(bar_time)].reset_index(drop=True)


def _ema_stack(f: Optional[float], m: Optional[float], s: Optional[float]) -> str:
    if None in (f, m, s):
        return "UNKNOWN"
    if f > m > s:
        return "BULL"
    if f < m < s:
        return "BEAR"
    return "MIXED"


def build_view(tf: str, df: pd.DataFrame, vol_history: Optional[List[float]] = None
               ) -> TimeframeView:
    n = len(df)
    if n == 0:
        return TimeframeView(tf=tf, bars=0, close=None)
    c = df["close"]
    e5, e9, e21 = I.ema(c, 5), I.ema(c, 9), I.ema(c, 21)
    e31, e50 = I.ema(c, 31), I.ema(c, 50)
    s20, s50 = I.sma(c, 20), I.sma(c, 50)
    a14 = I.atr(df, 14)
    sw = swings(df, k=2)
    hs = [x for x in sw if x.kind == "high"]
    ls = [x for x in sw if x.kind == "low"]
    stack = _ema_stack(e5, e31, e50)
    struct = structure_label(sw)
    slope = I.slope_pct(c, 5)
    rv = I.realized_vol(c, 20)
    reg = classify(e5, e31, e50, slope, struct,
                   I.percentile_rank(rv, vol_history or []), compression(df))
    return TimeframeView(
        tf=tf, bars=n, close=float(c.iloc[-1]),
        ema5=e5, ema9=e9, ema21=e21, ema31=e31, ema50=e50, sma20=s20, sma50=s50,
        rsi14=I.rsi(c, 14), atr14=a14, roc5=I.roc(c, 5), slope_fast_pct=slope,
        realized_vol=rv,
        dist_ema21_pct=I.distance_pct(float(c.iloc[-1]), e21),
        dist_sma50_pct=I.distance_pct(float(c.iloc[-1]), s50),
        ema_stack=stack, structure=struct,
        consecutive=I.consecutive_direction(c), compression=compression(df),
        swing_high=(hs[-1].price if hs else None),
        swing_low=(ls[-1].price if ls else None),
        trend=reg.trend,
    )


def build_state(
    symbol: str,
    frames: Dict[str, pd.DataFrame],
    bar_time: datetime,
    primary_tf: str = "5m",
    source: str = "REPLAY_GRID",
    data_available_at: Optional[datetime] = None,
    prev_day: Optional[Dict[str, float]] = None,
    india_vix: Optional[float] = None,
    vol_history: Optional[List[float]] = None,
    or_bars: int = 3,
    level_lookback: int = 40,
) -> MarketState:
    """
    Build the canonical state at `bar_time` from a dict of timeframe frames.

    `frames` maps e.g. {"1m": df, "5m": df, "15m": df, "30m": df, "1h": df, "1d": df}.
    Each frame is truncated to `bar_time` before anything is computed, so passing a
    frame that extends into the future is harmless.
    """
    trunc = {tf: _truncate(df, bar_time) for tf, df in frames.items()}
    if primary_tf not in trunc or trunc[primary_tf].empty:
        raise ValueError(f"no bars for primary timeframe {primary_tf} at {bar_time}")

    p = trunc[primary_tf]
    spot = float(p["close"].iloc[-1])
    sess_date = pd.Timestamp(bar_time).date()
    today = p[pd.to_datetime(p["datetime"]).dt.date == sess_date]

    views = {tf: build_view(tf, d, vol_history) for tf, d in trunc.items() if not d.empty}

    s_open = float(today["open"].iloc[0]) if len(today) else None
    s_high = float(today["high"].max()) if len(today) else None
    s_low = float(today["low"].min()) if len(today) else None
    vwap = I.session_vwap(today) if len(today) else None
    orh, orl = opening_range(today, or_bars) if len(today) else (None, None)
    vr = I.volume_ratio(p, 20)

    pdc = (prev_day or {}).get("close")
    gap = None
    if s_open is not None and pdc:
        gap = float((s_open - pdc) / pdc * 100.0)

    a14 = views[primary_tf].atr14
    cf: Optional[CandleFeatures] = candle_features(p, a14)

    # Break state is measured against a level that HAS HELD: the extreme of the
    # prior `level_lookback` bars, excluding the current bar so the level is not
    # defined by the bar testing it. A recent k=2 swing is far too close on a
    # 5-minute chart and makes almost every bar look like a breakout.
    lvl_h, lvl_l = significant_levels(p, lookback=level_lookback, exclude_recent=1)
    if lvl_h is None:
        lvl_h, lvl_l = orh, orl
    bs: BreakState = break_state(p, lvl_h, lvl_l)
    new_hi = is_new_break(p, lvl_h, "high")
    new_lo = is_new_break(p, lvl_l, "low")

    prim = views[primary_tf]
    reg = classify(prim.ema5, prim.ema31, prim.ema50, prim.slope_fast_pct,
                   prim.structure, I.percentile_rank(prim.realized_vol, vol_history or []),
                   prim.compression)

    align = 0
    for tf in ("15m", "30m", "1h"):
        v = views.get(tf)
        if v is None:
            continue
        if v.trend == "UP":
            align += 1
        elif v.trend == "DOWN":
            align -= 1

    bt = pd.Timestamp(bar_time)
    mins_in = int(max(0, (bt - bt.normalize() - pd.Timedelta(hours=9, minutes=15))
                      .total_seconds() // 60))
    mins_to = int(max(0, (bt.normalize() + pd.Timedelta(hours=15, minutes=30) - bt)
                      .total_seconds() // 60))
    in_sess = SESSION_OPEN <= bt.time() <= SESSION_CLOSE

    st = MarketState(
        symbol=symbol, bar_time=bt.to_pydatetime(),
        data_available_at=(data_available_at or bt.to_pydatetime()),
        source=source, spot=spot, session_date=sess_date,
        minutes_into_session=mins_in, minutes_to_close=mins_to, in_session=in_sess,
        primary_tf=primary_tf, views=views,
        session_open=s_open, session_high=s_high, session_low=s_low,
        vwap=vwap, dist_vwap_pct=I.distance_pct(spot, vwap), volume_ratio=vr,
        or_high=orh, or_low=orl, gap_pct=gap,
        prev_day_high=(prev_day or {}).get("high"),
        prev_day_low=(prev_day or {}).get("low"),
        prev_day_close=pdc,
        candle=(cf.to_dict() if cf else None),
        breaks={"broke_high": bs.broke_high, "broke_low": bs.broke_low,
                "break_points": bs.break_points,
                "failed_break_high": bs.failed_break_high,
                "failed_break_low": bs.failed_break_low,
                "level_high": lvl_h, "level_low": lvl_l,
                "new_break_high": new_hi, "new_break_low": new_lo,
                "level_lookback": level_lookback},
        regime_trend=reg.trend, regime_strength=reg.trend_strength,
        regime_vol_bucket=reg.vol_bucket, regime_why=reg.why,
        htf_alignment=align, india_vix=india_vix,
    )
    assert_no_lookahead(st)
    return st


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """
    Resample a 1m/5m frame to a higher timeframe with LEFT-closed, LEFT-labelled
    bins, then drop the still-forming last bar unless it is complete.

    Labelling matters for causality: a bar labelled 10:00 on a 15m rule covers
    10:00-10:14, so it is only complete at 10:15. `build_state` truncates on the
    label, so an incomplete bar would leak. We therefore stamp each bar with its
    CLOSE time.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["datetime", "open", "high", "low", "close", "volume"])
    d = df.copy()
    d["datetime"] = pd.to_datetime(d["datetime"])
    d = d.set_index("datetime").sort_index()
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in d.columns:
        agg["volume"] = "sum"
    out = d.resample(rule, label="left", closed="left").agg(agg).dropna(subset=["close"])
    delta = pd.tseries.frequencies.to_offset(rule)
    out.index = out.index + delta          # stamp with the bar's CLOSE time
    return out.reset_index().rename(columns={"index": "datetime"})


class StateBuilder:
    """
    Incremental state construction for replay.

    `build_state` re-truncates every frame from scratch, which is correct but
    quadratic: replaying N bars over frames of N rows is O(N^2) and a few thousand
    bars is already minutes. Indicators here need at most ~260 trailing bars, so
    this class pre-sorts each frame once and hands `build_state` a trailing WINDOW
    located by binary search.

    The causality guarantee is unchanged — the window still ends at or before
    `bar_time`, it simply does not carry rows nobody reads. A too-small window would
    silently change indicator values, so `window` is generous by default and the
    class refuses to go below the longest lookback any indicator uses.
    """

    MIN_WINDOW = 260          # ema50 + sma50 + rolling(250) headroom

    def __init__(self, symbol: str, frames: Dict[str, pd.DataFrame],
                 primary_tf: str = "5m", source: str = "REPLAY_GRID",
                 window: int = 400):
        if window < self.MIN_WINDOW:
            raise ValueError(f"window {window} below the {self.MIN_WINDOW}-bar minimum "
                             f"needed by the longest indicator lookback")
        self.symbol = symbol
        self.primary_tf = primary_tf
        self.source = source
        self.window = int(window)
        self._frames: Dict[str, pd.DataFrame] = {}
        self._ts: Dict[str, np.ndarray] = {}
        for tf, df in frames.items():
            if df is None or df.empty:
                continue
            d = df.copy()
            d["datetime"] = pd.to_datetime(d["datetime"])
            d = d.sort_values("datetime").reset_index(drop=True)
            self._frames[tf] = d
            self._ts[tf] = d["datetime"].to_numpy("datetime64[ns]")

    def window_frames(self, bar_time: datetime) -> Dict[str, pd.DataFrame]:
        t = np.datetime64(pd.Timestamp(bar_time), "ns")
        out: Dict[str, pd.DataFrame] = {}
        for tf, d in self._frames.items():
            j = int(np.searchsorted(self._ts[tf], t, side="right"))
            if j == 0:
                continue
            out[tf] = d.iloc[max(0, j - self.window):j]
        return out

    def at(self, bar_time: datetime, **kw) -> MarketState:
        return build_state(self.symbol, self.window_frames(bar_time), bar_time,
                           primary_tf=self.primary_tf, source=self.source, **kw)

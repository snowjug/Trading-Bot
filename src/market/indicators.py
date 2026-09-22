"""
Indicator primitives. Pure functions over a bar frame, no state, no LLM.

Every function here returns a value computed ONLY from the rows it is given. The
caller is responsible for passing a frame that ends at the decision bar — that is
where causality is enforced (see `market_state.build_state`), not here, so these
stay trivially testable.

Bars are expected as a DataFrame with columns: datetime, open, high, low, close,
volume. Missing volume is tolerated (index feeds often carry none) and every
volume-derived value then returns None rather than a fabricated number.
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import pandas as pd


def ema(s: pd.Series, span: int) -> Optional[float]:
    s = s.dropna()
    if len(s) < 2:
        return None
    return float(s.ewm(span=span, adjust=False).mean().iloc[-1])


def sma(s: pd.Series, n: int) -> Optional[float]:
    s = s.dropna()
    if len(s) < n:
        return None
    return float(s.tail(n).mean())


def rsi(s: pd.Series, period: int = 14) -> Optional[float]:
    s = s.dropna()
    if len(s) < period + 1:
        return None
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    last_dn = float(dn.iloc[-1])
    if last_dn == 0:
        return 100.0
    rs = float(up.iloc[-1]) / last_dn
    return float(100 - 100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    if len(df) < period + 1:
        return None
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(),
                    (df["low"] - prev).abs()], axis=1).max(axis=1)
    v = tr.rolling(period).mean().iloc[-1]
    return float(v) if np.isfinite(v) else None


def roc(s: pd.Series, n: int) -> Optional[float]:
    s = s.dropna()
    if len(s) < n + 1:
        return None
    prev = float(s.iloc[-(n + 1)])
    if prev == 0:
        return None
    return float((float(s.iloc[-1]) / prev - 1.0) * 100.0)


def realized_vol(s: pd.Series, n: int, bars_per_year: float = 252.0) -> Optional[float]:
    """Annualised realised volatility in percent, from log returns of `n` bars."""
    s = s.dropna()
    if len(s) < n + 1:
        return None
    r = np.diff(np.log(s.tail(n + 1).to_numpy(float)))
    if len(r) < 2:
        return None
    sd = float(np.std(r, ddof=1))
    return float(sd * np.sqrt(bars_per_year) * 100.0)


def session_vwap(df: pd.DataFrame) -> Optional[float]:
    """
    Volume-weighted average price over the rows given, using the typical price.

    Returns None when volume is absent or zero throughout — an unweighted mean would
    be a different quantity wearing VWAP's name.
    """
    if "volume" not in df.columns or df.empty:
        return None
    v = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
    if float(v.sum()) <= 0:
        return None
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    return float((tp * v).sum() / v.sum())


def volume_ratio(df: pd.DataFrame, lookback: int = 20) -> Optional[float]:
    """Current bar volume over the mean of the previous `lookback` bars."""
    if "volume" not in df.columns or len(df) < lookback + 1:
        return None
    v = pd.to_numeric(df["volume"], errors="coerce")
    if v.isna().all():
        return None
    base = float(v.iloc[-(lookback + 1):-1].mean())
    if not np.isfinite(base) or base <= 0:
        return None
    return float(float(v.iloc[-1]) / base)


def slope_pct(s: pd.Series, n: int = 5) -> Optional[float]:
    """
    Least-squares slope over the last `n` points, expressed as percent of the last
    value per bar, so it is comparable across price levels and instruments.
    """
    s = s.dropna()
    if len(s) < n or n < 2:
        return None
    y = s.tail(n).to_numpy(float)
    x = np.arange(len(y), dtype=float)
    b = float(np.polyfit(x, y, 1)[0])
    last = float(y[-1])
    if last == 0:
        return None
    return float(b / last * 100.0)


def consecutive_direction(s: pd.Series) -> int:
    """
    Signed run length of same-direction closes ending at the last bar.
    +3 means three consecutive up closes; -2 two consecutive down closes.
    """
    s = s.dropna()
    if len(s) < 2:
        return 0
    d = np.sign(np.diff(s.to_numpy(float)))
    if len(d) == 0 or d[-1] == 0:
        return 0
    run, last = 0, d[-1]
    for x in d[::-1]:
        if x == last:
            run += 1
        else:
            break
    return int(run * (1 if last > 0 else -1))


def distance_pct(price: float, level: Optional[float]) -> Optional[float]:
    if level is None or not np.isfinite(level) or level == 0:
        return None
    return float((price - level) / level * 100.0)


def percentile_rank(value: Optional[float], history: Sequence[float]) -> Optional[float]:
    """Where `value` sits in `history`, 0-100. Used for volatility bucketing."""
    if value is None:
        return None
    h = np.asarray([x for x in history if x is not None and np.isfinite(x)], float)
    if len(h) < 20:
        return None
    return float((h < value).mean() * 100.0)

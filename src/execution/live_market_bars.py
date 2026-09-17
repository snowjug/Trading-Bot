"""
Live intraday bar state for the paper-trading session.

Supplies two things the live execution path needs and previously fabricated:

1. The AUTHENTIC exchange session open (never the spot price at process start).
2. A strategy-ready OHLCV frame (historical daily bars + today's forming bar)
   so the validated strategy classes in src/strategies/ can run causally on
   live data instead of being re-implemented as inline threshold rules.

Fail-closed contract: every accessor returns None when authentic data is
unavailable. No synthetic bars, no spot-for-open substitution, no index
cross-multiples, no carried-forward values.
"""

import os
import sys
import time
from datetime import datetime, date, time as dtime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.utils.logging import setup_logging

logger = setup_logging("execution.live_bars")

# Official Dhan IDX_I security IDs
INDEX_SECURITY_IDS: Dict[str, str] = {
    "NIFTY": "13",
    "BANKNIFTY": "25",
    "INDIAVIX": "21",
}

# Historical daily bar files in the local data lake
INDEX_HISTORY_FILES: Dict[str, str] = {
    "NIFTY": "data/real_2026/INDEX_NIFTY50_daily.csv",
    "BANKNIFTY": "data/real_2026/INDEX_BANKNIFTY_daily.csv",
    "INDIAVIX": "data/real_2026/INDEX_INDIAVIX_daily.csv",
}

_REQUIRED_BAR_COLUMNS = ("datetime", "open", "high", "low", "close", "volume")

# Cache of today's session bar, keyed by (symbol, trading date).
# The forming bar is a LIVE object: its high/low/close/volume evolve all day, so
# the cache is deliberately short-lived. Caching it for the whole session (the
# previous behaviour) froze OHLCV at the first fetch and made every downstream
# indicator stale. Settled historical bars are immutable and are NOT cached here.
_session_bar_cache: Dict[str, Any] = {}
_session_bar_fetched_at: Dict[str, float] = {}
FORMING_BAR_TTL_SECONDS: float = 20.0


def _dhan_intraday_session_bar(symbol: str, trading_day: date) -> Optional[Dict[str, float]]:
    """Aggregates today's Dhan intraday candles into a single session bar."""
    sec_id = INDEX_SECURITY_IDS.get(symbol.upper())
    if not sec_id:
        return None
    try:
        from src.data.dhan_client import DhanAPIClient

        client = DhanAPIClient()
        if not client.access_token or not client.client_id:
            return None
        day_str = trading_day.strftime("%Y-%m-%d")
        to_dt = datetime.combine(trading_day, datetime.min.time()).replace(hour=15, minute=30)
        df = client.fetch_intraday_candles(
            security_id=sec_id,
            exchange_segment="IDX_I",
            instrument="INDEX",
            interval="5",
            from_date=f"{day_str} 09:15:00",
            to_date=f"{day_str} 15:30:00",
        )
        if df is None or df.empty:
            return None
        df = df.sort_values("datetime")

        # VERIFIED AGAINST THE LIVE API (2026-09-17): /charts/intraday ignores the
        # requested `toDate` and appends a post-close settlement candle (e.g. a
        # 19:25 stamp after a 15:30 close, 240 minutes after the prior candle).
        # Candles outside the requested window are dropped so the session bar
        # reflects the trading session rather than a settlement marker.
        if to_dt is not None:
            df = df[df["datetime"] <= pd.Timestamp(to_dt)]
        if df.empty:
            return None

        o = float(df["open"].iloc[0])
        h = float(df["high"].max())
        low = float(df["low"].min())
        c = float(df["close"].iloc[-1])
        v = float(df["volume"].sum())
        if o <= 0 or h <= 0 or low <= 0 or c <= 0:
            return None
        return {
            "open": o, "high": h, "low": low, "close": c, "volume": v,
            "source": "DHAN_INTRADAY_5M",
            # The EXCHANGE time of the last candle. Without this the bar carries
            # only a local fetch time, which looks fresh even hours after close.
            "market_timestamp": df["datetime"].iloc[-1].to_pydatetime().isoformat(),
        }
    except Exception as e:
        logger.debug(f"Dhan intraday session bar unavailable for {symbol}: {e}")
        return None


def _yfinance_session_bar(symbol: str, trading_day: date) -> Optional[Dict[str, float]]:
    """Secondary authentic source: yfinance 5-minute intraday series."""
    ticker_map = {"NIFTY": "^NSEI", "BANKNIFTY": "^NSEBANK", "INDIAVIX": "^INDIAVIX"}
    ticker = ticker_map.get(symbol.upper())
    if not ticker:
        return None
    try:
        import yfinance as yf

        raw = yf.download(tickers=ticker, period="1d", interval="5m", progress=False)
        if raw is None or raw.empty:
            return None
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw = raw.dropna(subset=["Open", "High", "Low", "Close"])
        if raw.empty:
            return None
        o = float(raw["Open"].iloc[0])
        h = float(raw["High"].max())
        low = float(raw["Low"].min())
        c = float(raw["Close"].iloc[-1])
        v = float(raw["Volume"].sum()) if "Volume" in raw.columns else 0.0
        if o <= 0 or h <= 0 or low <= 0 or c <= 0:
            return None
        return {
            "open": o, "high": h, "low": low, "close": c, "volume": v,
            "source": "YFINANCE_INTRADAY_5M",
        }
    except Exception as e:
        logger.debug(f"yfinance session bar unavailable for {symbol}: {e}")
        return None


def get_today_session_bar(
    symbol: str,
    trading_day: Optional[date] = None,
    use_cache: bool = True,
) -> Optional[Dict[str, float]]:
    """
    Returns today's authentic exchange session bar for an index.

    Fail-closed: returns None when no authentic intraday source is reachable.
    The caller MUST treat None as DATA_UNAVAILABLE -> NO SIGNAL -> NO TRADE.
    The session open is NEVER approximated by the current spot price.
    """
    day = trading_day or datetime.now().date()
    cache_key = f"{symbol.upper()}_{day.isoformat()}"
    if use_cache and cache_key in _session_bar_cache:
        age = time.time() - _session_bar_fetched_at.get(cache_key, 0.0)
        if age < FORMING_BAR_TTL_SECONDS:
            return _session_bar_cache[cache_key]

    bar = _dhan_intraday_session_bar(symbol, day) or _yfinance_session_bar(symbol, day)
    if bar is None:
        logger.warning(
            f"Authentic session bar unavailable for {symbol} on {day}. "
            "Fail-closed: DATA_UNAVAILABLE -> NO SIGNAL."
        )
        return None

    bar["symbol"] = symbol.upper()
    bar["trading_day"] = day.isoformat()
    bar["fetched_at"] = datetime.now().isoformat()
    if use_cache:
        _session_bar_cache[cache_key] = bar
        _session_bar_fetched_at[cache_key] = time.time()
    return bar


SESSION_CLOSE = dtime(15, 30)


def is_session_bar_settled(bar: Optional[Dict[str, Any]], now: Optional[datetime] = None) -> bool:
    """
    True only when today's daily bar is FINAL (the session has closed).

    A daily bar settles at 15:30 IST. Before that its close, volume, high and low
    are all still moving, so any indicator derived from them (EMA, RSI, VWAP,
    volume ratios) is provisional. Strategies validated on settled daily bars
    must not be evaluated against such a bar.

    Determined from the bar's own EXCHANGE timestamp, never from the local clock
    alone, so a stale or undateable bar is never reported as settled.
    """
    if not bar:
        return False
    ts = bar.get("market_timestamp")
    if not ts:
        return False
    try:
        bar_dt = datetime.fromisoformat(str(ts))
    except Exception:
        return False

    ref = now or datetime.now()
    # The bar is settled once the session has closed on the bar's own trading day.
    if bar_dt.date() < ref.date():
        return True
    return bar_dt.time() >= SESSION_CLOSE and ref.time() >= SESSION_CLOSE


def load_daily_history(symbol: str, before_day: Optional[date] = None) -> Optional[pd.DataFrame]:
    """
    Loads authentic historical daily bars strictly BEFORE `before_day`.

    The strict cutoff is what keeps the live frame causal: today's bar is
    supplied separately from live intraday data, never read from history.
    """
    path = INDEX_HISTORY_FILES.get(symbol.upper())
    if not path or not Path(path).exists():
        logger.warning(f"Daily history file missing for {symbol} ({path}). Fail-closed.")
        return None
    try:
        df = pd.read_csv(path)
    except Exception as e:
        logger.warning(f"Failed to read daily history for {symbol}: {e}")
        return None

    missing = set(_REQUIRED_BAR_COLUMNS) - set(df.columns)
    if missing:
        logger.warning(f"Daily history for {symbol} missing columns {missing}. Fail-closed.")
        return None

    df["datetime"] = pd.to_datetime(df["datetime"])
    cutoff = before_day or datetime.now().date()
    df = df[df["datetime"].dt.date < cutoff]
    return df.sort_values("datetime").reset_index(drop=True)


def _attach_vix_column(
    frame: pd.DataFrame,
    trading_day: date,
    today_vix: Optional[float],
) -> Optional[pd.DataFrame]:
    """
    Joins an authentic INDIA VIX close onto the frame.

    Several validated strategies read `df["vix"]` and silently fall back to a
    hardcoded constant (16.0 / 15.0) when the column is absent. That fallback is
    fabricated volatility, so the column is either built from real data or the
    whole frame fails closed.
    """
    if today_vix is None or float(today_vix) <= 0:
        logger.warning("Live INDIA VIX unavailable. Fail-closed: strategy frame not built.")
        return None

    vix_hist = load_daily_history("INDIAVIX", before_day=trading_day)
    if vix_hist is None or vix_hist.empty:
        logger.warning("INDIA VIX history unavailable. Fail-closed: strategy frame not built.")
        return None

    vix_map = dict(zip(vix_hist["datetime"].dt.date, vix_hist["close"].astype(float)))
    vix_map[trading_day] = float(today_vix)

    frame = frame.copy()
    frame["vix"] = frame["datetime"].dt.date.map(vix_map)
    # Forward-fill only. Back-filling would pull a future VIX print into an
    # earlier bar, which is lookahead; leading bars with no prior VIX are
    # dropped instead.
    frame["vix"] = frame["vix"].ffill()
    frame = frame[frame["vix"].notna()].reset_index(drop=True)
    if frame.empty:
        logger.warning("No overlapping INDIA VIX history. Fail-closed.")
        return None
    return frame


def _attach_rsi_column(frame: pd.DataFrame, period: int = 14) -> Optional[pd.DataFrame]:
    """
    Computes RSI(14) from authentic close prices and attaches it as `rsi_14`.

    Strategies 1 and 2 read `df["rsi_14"]` and silently fall back to a constant
    50.0 when the column is absent — a fabricated "perfectly neutral momentum"
    reading that sits inside their entry condition. The column is therefore
    computed from real closes, or the frame fails closed.

    Causality: RSI at bar i uses only closes up to and including bar i. The
    leading `period` bars have no defined RSI and are dropped rather than
    back-filled, because back-filling would import future information.
    """
    if "close" not in frame.columns or len(frame) <= period + 1:
        logger.warning("Insufficient closes to compute RSI. Fail-closed.")
        return None

    frame = frame.copy()
    delta = frame["close"].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    frame[f"rsi_{period}"] = 100 - (100 / (1 + rs))

    frame = frame[frame[f"rsi_{period}"].notna()].reset_index(drop=True)
    if frame.empty:
        logger.warning("RSI could not be computed on any bar. Fail-closed.")
        return None
    return frame


def build_strategy_frame(
    symbol: str,
    session_bar: Optional[Dict[str, float]] = None,
    trading_day: Optional[date] = None,
    min_bars: int = 1,
    today_vix: Optional[float] = None,
    require_vix: bool = False,
    require_rsi: bool = False,
) -> Optional[pd.DataFrame]:
    """
    Builds the OHLCV frame consumed by the validated strategy classes:
    authentic historical daily bars plus today's forming session bar.

    Returns None (fail-closed) when history is missing/too short, when today's
    authentic session bar is unavailable, or when `require_vix` is set and an
    authentic VIX series cannot be assembled.

    NOTE ON SEMANTICS: today's bar is a FORMING bar. Its high/low/close move
    intraday, so a signal computed at 10:00 may differ from the same strategy
    evaluated on the settled daily bar. This is inherent to live evaluation of
    a daily-bar strategy and is recorded on the frame as `is_forming_bar`.
    """
    day = trading_day or datetime.now().date()
    hist = load_daily_history(symbol, before_day=day)
    if hist is None or hist.empty:
        return None

    bar = session_bar if session_bar is not None else get_today_session_bar(symbol, day)
    if bar is None:
        return None

    today_row = pd.DataFrame([{
        "datetime": pd.Timestamp(day),
        "open": float(bar["open"]),
        "high": float(bar["high"]),
        "low": float(bar["low"]),
        "close": float(bar["close"]),
        "volume": float(bar.get("volume", 0.0)),
    }])
    frame = pd.concat([hist[list(_REQUIRED_BAR_COLUMNS)], today_row], ignore_index=True)

    source = bar.get("source", "UNKNOWN")
    if require_vix:
        frame = _attach_vix_column(frame, day, today_vix)
        if frame is None:
            return None
    if require_rsi:
        frame = _attach_rsi_column(frame)
        if frame is None:
            return None

    # Length is checked after the VIX join, because the causality-safe join can
    # trim leading bars that have no prior VIX print.
    if len(frame) < max(1, min_bars):
        logger.warning(
            f"Insufficient bar history for {symbol}: {len(frame)} < {min_bars}. Fail-closed."
        )
        return None

    frame.attrs["is_forming_bar"] = True
    frame.attrs["session_bar_source"] = source
    return frame


def clear_session_bar_cache() -> None:
    """Clears the cached session bars (used on new-day rollover and in tests)."""
    _session_bar_cache.clear()
    _session_bar_fetched_at.clear()

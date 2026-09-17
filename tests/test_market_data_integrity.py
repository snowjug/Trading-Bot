"""
Regression suite for market-data integrity blockers B3, B4 and B16.

B3: BANKNIFTY must never be synthesised from NIFTY (the `nifty * 2.35` fallback).
B4: The session open must be an authentic exchange open, never the current spot.
B16: An executable quote requires a real exchange timestamp; local receipt time
     is not evidence of market freshness.

Every assertion here is fail-closed: missing authentic data must yield
DATA_UNAVAILABLE -> NO SIGNAL -> NO TRADE.
"""
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.execution import live_market_bars
from src.execution.dhan_contract_resolver import DhanContractResolver, _quote_cache


class FakeResp:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture
def clean_caches():
    _quote_cache.clear()
    live_market_bars.clear_session_bar_cache()
    yield
    _quote_cache.clear()
    live_market_bars.clear_session_bar_cache()


def _index_payload(nifty=23250.0, vix=13.2, bank=56300.0):
    return {"data": {"IDX_I": {
        "13": {"last_price": nifty},
        "21": {"last_price": vix},
        "25": {"last_price": bank},
    }}}


def _session_bar(open_px, close_px=None):
    # market_timestamp is required: the index path now refuses undateable or
    # stale bars (verified against the live API — /marketfeed/ltp carries no
    # timestamp of its own, so freshness comes from the intraday bar).
    return {
        "open": open_px, "high": open_px + 50, "low": open_px - 50,
        "close": close_px if close_px is not None else open_px + 10,
        "volume": 100000.0, "source": "TEST_INTRADAY",
        "market_timestamp": datetime.now().isoformat(),
    }


# ─── B3: NO SYNTHETIC BANKNIFTY ───

def test_b3_missing_banknifty_fails_closed_and_never_derives_from_nifty(clean_caches):
    """Missing BANKNIFTY must return None, not nifty * 2.35."""
    sess = MagicMock()
    sess.post.return_value = FakeResp(_index_payload(bank=0))  # BANKNIFTY absent

    with patch("src.execution.dhan_contract_resolver._pace_dhan_request"), \
         patch.object(live_market_bars, "get_today_session_bar", return_value=_session_bar(23200.0)), \
         patch("yfinance.download", side_effect=AssertionError("must not reach yfinance index fallback")):
        mkt = DhanContractResolver.get_live_market_state(dhan_session=sess)

    assert mkt is None, "Missing BANKNIFTY must fail closed -> DATA_UNAVAILABLE -> NO TRADE"


def test_b3_no_2_35_multiple_anywhere_in_resolver_source():
    """The nifty * 2.35 fabrication must not exist in source at all."""
    src = open("src/execution/dhan_contract_resolver.py", encoding="utf-8").read()
    assert "2.35" not in src, "Synthetic BANKNIFTY cross-multiple still present in source"


def test_b3_real_banknifty_is_used_verbatim(clean_caches):
    """When BANKNIFTY is genuinely present it is passed through unmodified."""
    sess = MagicMock()
    sess.post.return_value = FakeResp(_index_payload(bank=56300.0))

    with patch("src.execution.dhan_contract_resolver._pace_dhan_request"), \
         patch.object(live_market_bars, "get_today_session_bar",
                      side_effect=lambda sym, *a, **k: _session_bar(23200.0 if sym == "NIFTY" else 56100.0)):
        mkt = DhanContractResolver.get_live_market_state(dhan_session=sess)

    assert mkt is not None
    assert mkt["bank_spot"] == 56300.0
    assert abs(mkt["bank_spot"] - mkt["nifty_spot"] * 2.35) > 1.0, "bank_spot must not be a NIFTY multiple"


# ─── B4: AUTHENTIC SESSION OPEN ───

def test_b4_missing_session_open_fails_closed(clean_caches):
    """No authentic intraday open -> no market state at all."""
    sess = MagicMock()
    sess.post.return_value = FakeResp(_index_payload())

    with patch("src.execution.dhan_contract_resolver._pace_dhan_request"), \
         patch.object(live_market_bars, "get_today_session_bar", return_value=None):
        mkt = DhanContractResolver.get_live_market_state(dhan_session=sess)

    assert mkt is None, "Unavailable session open must fail closed, never fall back to spot"


def test_b4_open_is_never_substituted_by_current_spot(clean_caches):
    """The returned open must come from the intraday bar, not the live spot."""
    sess = MagicMock()
    sess.post.return_value = FakeResp(_index_payload(nifty=23250.0, bank=56300.0))

    with patch("src.execution.dhan_contract_resolver._pace_dhan_request"), \
         patch.object(live_market_bars, "get_today_session_bar",
                      side_effect=lambda sym, *a, **k: _session_bar(23111.0 if sym == "NIFTY" else 56011.0)):
        mkt = DhanContractResolver.get_live_market_state(dhan_session=sess)

    assert mkt is not None
    assert mkt["nifty_open"] == 23111.0
    assert mkt["nifty_open"] != mkt["nifty_spot"], "open must not equal the current spot"
    assert mkt["bank_open"] == 56011.0
    assert mkt["bank_open"] != mkt["bank_spot"]


def test_b4_session_bar_provider_fails_closed_when_no_source(clean_caches):
    """Both authentic intraday sources unavailable -> None."""
    with patch.object(live_market_bars, "_dhan_intraday_session_bar", return_value=None), \
         patch.object(live_market_bars, "_yfinance_session_bar", return_value=None):
        assert live_market_bars.get_today_session_bar("NIFTY") is None


def test_b4_session_bar_uses_first_candle_open(clean_caches):
    """The session open is the first intraday candle's open, not the latest close."""
    candles = pd.DataFrame({
        "datetime": pd.to_datetime(["2026-09-17 09:15", "2026-09-17 09:20", "2026-09-17 09:25"]),
        "open": [23100.0, 23150.0, 23180.0],
        "high": [23160.0, 23190.0, 23240.0],
        "low": [23090.0, 23140.0, 23170.0],
        "close": [23150.0, 23180.0, 23230.0],
        "volume": [1000.0, 1200.0, 900.0],
    })
    fake_client = MagicMock()
    fake_client.access_token = "tok"
    fake_client.client_id = "cid"
    fake_client.fetch_intraday_candles.return_value = candles

    with patch("src.data.dhan_client.DhanAPIClient", return_value=fake_client):
        bar = live_market_bars.get_today_session_bar("NIFTY", trading_day=date(2026, 9, 17), use_cache=False)

    assert bar is not None
    assert bar["open"] == 23100.0      # first candle open
    assert bar["high"] == 23240.0      # session high
    assert bar["low"] == 23090.0       # session low
    assert bar["close"] == 23230.0     # latest close
    assert bar["volume"] == 3100.0


# ─── B4/B1: STRATEGY FRAME CAUSALITY ───

def test_strategy_frame_is_causal_and_appends_today(clean_caches):
    """History must stop strictly before today; today's bar comes from live data."""
    frame = live_market_bars.build_strategy_frame(
        "NIFTY",
        session_bar=_session_bar(23100.0, close_px=23230.0),
        trading_day=date(2026, 9, 17),
    )
    assert frame is not None
    assert list(frame.columns) == ["datetime", "open", "high", "low", "close", "volume"]
    assert frame["datetime"].dt.date.max() == date(2026, 9, 17)
    assert (frame["datetime"].dt.date[: len(frame) - 1] < date(2026, 9, 17)).all()
    assert frame["open"].iloc[-1] == 23100.0
    assert frame["close"].iloc[-1] == 23230.0
    assert frame.attrs["is_forming_bar"] is True


def test_strategy_frame_fails_closed_without_session_bar(clean_caches):
    with patch.object(live_market_bars, "get_today_session_bar", return_value=None):
        assert live_market_bars.build_strategy_frame("NIFTY", trading_day=date(2026, 9, 17)) is None


def test_strategy_frame_fails_closed_on_insufficient_history(clean_caches):
    frame = live_market_bars.build_strategy_frame(
        "NIFTY",
        session_bar=_session_bar(23100.0),
        trading_day=date(2026, 9, 17),
        min_bars=100000,
    )
    assert frame is None, "Insufficient bar history must fail closed"


# ─── B16: EXCHANGE TIMESTAMP REQUIRED ───

def test_b16_quote_without_exchange_timestamp_is_rejected(clean_caches):
    """A quote lacking last_trade_time must not be returned or cached."""
    sess = MagicMock()
    sess.post.return_value = FakeResp({"data": {"NSE_FNO": {"56983": {
        "last_price": 120.0,
        "depth": {"buy": [{"price": 119.5}], "sell": [{"price": 120.5}]},
        # no last_trade_time
    }}}})

    with patch("src.execution.dhan_contract_resolver._pace_dhan_request"):
        res = DhanContractResolver.prefetch_quotes(["56983"], dhan_session=sess)

    assert res == {}, "Quote without exchange timestamp must be rejected"
    assert "56983" not in _quote_cache, "Rejected quote must not be cached"


def test_b16_quote_with_exchange_timestamp_is_accepted(clean_caches):
    sess = MagicMock()
    sess.post.return_value = FakeResp({"data": {"NSE_FNO": {"56983": {
        "last_price": 120.0,
        "depth": {"buy": [{"price": 119.5}], "sell": [{"price": 120.5}]},
        "last_trade_time": "17/09/2026 11:30:00",
    }}}})

    with patch("src.execution.dhan_contract_resolver._pace_dhan_request"):
        res = DhanContractResolver.prefetch_quotes(["56983"], dhan_session=sess)

    assert "56983" in res
    assert res["56983"]["market_timestamp"] == "17/09/2026 11:30:00"
    assert res["56983"]["timestamp"] == "17/09/2026 11:30:00"
    assert res["56983"]["received_at"] != res["56983"]["timestamp"]


def test_b17_quote_age_policy_is_tightened():
    """Freshness bound must be a defensible intraday value, not 300s."""
    from src.config import Config
    assert Config.MAX_QUOTE_AGE_SECONDS <= 60, "Executable quote age bound must be <= 60s"

"""
Regression tests for defects found by VERIFYING AGAINST THE LIVE DHAN API
(2026-09-17, account 1000000000, strictly read-only).

Two real defects were discovered that no amount of reading the repo would have
revealed:

1. TIMEZONE. `/charts/intraday` returns UNIX epochs. The client converted them
   with `pd.to_datetime(unit="s")`, producing UTC-naive timestamps 5h30m behind
   the naive-IST clock the rest of the system compares against. Verified: epoch
   1789616700 is the 09:15 IST opening candle, which the old code read as 03:45.
   Any freshness gate on candle data would therefore have been permanently stale.

2. POST-CLOSE CANDLE + NO STALENESS GATE. `/charts/intraday` ignores the
   requested `toDate` and appends a settlement candle (observed: 19:25 after a
   15:30 close, a 240-minute gap). Separately, `/marketfeed/ltp` returns
   `last_price` with NO timestamp at all, so six hours after the close the
   system happily reported stale index prices stamped with the LOCAL fetch time.

All tests here are offline and deterministic; no network call is made.
"""
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.execution import live_market_bars as lmb

# Real epochs captured from the live API on 2026-09-17.
EPOCH_FIRST_CANDLE = 1789616700   # 09:15 IST — NSE open
EPOCH_POST_CLOSE = 1789653300     # 19:25 IST — settlement marker, after 15:30


def _epoch_to_ist(epoch):
    return (
        pd.to_datetime(epoch, unit="s", utc=True)
        .tz_convert("Asia/Kolkata")
        .tz_localize(None)
    )


# ─────────────────── DEFECT 1: EPOCH TIMEZONE ───────────────────

def test_dhan_epochs_convert_to_ist_not_utc_naive():
    """The opening candle epoch must read as 09:15 IST, not 03:45."""
    assert _epoch_to_ist(EPOCH_FIRST_CANDLE).strftime("%H:%M") == "09:15"
    # The old (wrong) conversion, kept here to document the defect:
    assert pd.to_datetime(EPOCH_FIRST_CANDLE, unit="s").strftime("%H:%M") == "03:45"


def test_client_converts_intraday_candles_to_ist():
    """fetch_intraday_candles must return naive IST timestamps."""
    from src.data.dhan_client import DhanAPIClient

    payload = {
        "timestamp": [EPOCH_FIRST_CANDLE, EPOCH_FIRST_CANDLE + 300],
        "open": [23212.05, 23220.0], "high": [23230.0, 23240.0],
        "low": [23200.0, 23210.0], "close": [23220.0, 23235.0],
        "volume": [1000.0, 1200.0],
    }
    resp = MagicMock(status_code=200)
    resp.json.return_value = payload

    client = DhanAPIClient(client_id="x", access_token="y")
    with patch.object(client, "_post", return_value=resp):
        df = client.fetch_intraday_candles("13", "IDX_I", "INDEX", "5")

    assert df["datetime"].iloc[0].strftime("%H:%M") == "09:15", \
        "opening candle must be 09:15 IST, not 03:45 UTC-naive"
    assert df["datetime"].iloc[1].strftime("%H:%M") == "09:20"


def test_source_has_no_utc_naive_epoch_conversion_left():
    """No conversion site may fall back to the UTC-naive form."""
    src = open("src/data/dhan_client.py", encoding="utf-8").read()
    assert 'pd.to_datetime(df["timestamp"], unit="s")' not in src
    assert src.count('tz_convert("Asia/Kolkata")') >= 3, \
        "every epoch conversion site must localise to IST"


# ─────────── DEFECT 2: POST-CLOSE CANDLE AND SESSION-BAR TIMESTAMP ───────────

def _fake_candles():
    """09:15-15:25 session plus the observed 19:25 settlement candle."""
    epochs, o, h, low, c, v = [], [], [], [], [], []
    for i in range(75):                       # 09:15 .. 15:25 inclusive
        epochs.append(EPOCH_FIRST_CANDLE + i * 300)
        o.append(23212.05); h.append(23363.55); low.append(23197.0)
        c.append(23270.6); v.append(100.0)
    epochs.append(EPOCH_POST_CLOSE)           # 19:25 settlement marker
    o.append(23270.6); h.append(99999.0); low.append(1.0)
    c.append(23270.6); v.append(0.0)
    return pd.DataFrame({
        "datetime": [_epoch_to_ist(e) for e in epochs],
        "open": o, "high": h, "low": low, "close": c, "volume": v,
        "timestamp": epochs,
    })


def test_post_close_settlement_candle_is_excluded_from_session_bar():
    """
    The 19:25 candle is outside the trading session and must not shape the bar.

    Its poisoned high (99999) and low (1.0) would otherwise corrupt every
    indicator built on the session bar.
    """
    fake_client = MagicMock()
    fake_client.access_token = "t"
    fake_client.client_id = "c"
    fake_client.fetch_intraday_candles.return_value = _fake_candles()

    lmb.clear_session_bar_cache()
    with patch("src.data.dhan_client.DhanAPIClient", return_value=fake_client):
        bar = lmb.get_today_session_bar("NIFTY", trading_day=date(2026, 9, 17), use_cache=False)

    assert bar is not None
    assert bar["market_timestamp"].endswith("15:25:00"), \
        "session bar must end at the last in-session candle, not the settlement marker"
    assert bar["high"] != 99999.0, "post-close candle must not contaminate the session high"
    assert bar["low"] != 1.0, "post-close candle must not contaminate the session low"


def test_session_bar_carries_an_exchange_timestamp():
    """Without this the bar has only a local fetch time and always looks fresh."""
    fake_client = MagicMock()
    fake_client.access_token = "t"
    fake_client.client_id = "c"
    fake_client.fetch_intraday_candles.return_value = _fake_candles()

    lmb.clear_session_bar_cache()
    with patch("src.data.dhan_client.DhanAPIClient", return_value=fake_client):
        bar = lmb.get_today_session_bar("NIFTY", trading_day=date(2026, 9, 17), use_cache=False)
    assert "market_timestamp" in bar and bar["market_timestamp"]


# ─────────── DEFECT 2b: INDEX SPOT HAD NO STALENESS GATE ───────────

class _LtpResp:
    status_code = 200

    @staticmethod
    def json():
        # Exactly the observed shape: last_price only, NO timestamp anywhere.
        return {"data": {"IDX_I": {
            "13": {"last_price": 23270.6},
            "21": {"last_price": 12.29},
            "25": {"last_price": 56055.75},
        }}, "status": "success"}


def test_ltp_response_shape_has_no_timestamp():
    """Documents why index freshness cannot come from /marketfeed/ltp."""
    row = _LtpResp.json()["data"]["IDX_I"]["13"]
    assert "last_price" in row
    assert not any("time" in k.lower() for k in row), \
        "the LTP payload carries no timestamp, so it cannot establish freshness"


def test_stale_index_data_fails_closed():
    """Six hours after the close the market state must be refused."""
    from src.execution.dhan_contract_resolver import DhanContractResolver

    stale_bar = {
        "open": 23212.05, "high": 23363.55, "low": 23197.0, "close": 23270.6,
        "volume": 1.0, "source": "TEST",
        "market_timestamp": (datetime.now() - timedelta(hours=6)).isoformat(),
    }
    sess = MagicMock()
    sess.post.return_value = _LtpResp()

    with patch("src.execution.dhan_contract_resolver._pace_dhan_request"), \
         patch.object(lmb, "get_today_session_bar", return_value=stale_bar):
        mkt = DhanContractResolver.get_live_market_state(dhan_session=sess)

    assert mkt is None, "stale index data must never be served as a live market state"


def test_fresh_index_data_is_accepted():
    """Control: during live hours the gate must not block."""
    from src.execution.dhan_contract_resolver import DhanContractResolver

    fresh_bar = {
        "open": 23212.05, "high": 23363.55, "low": 23197.0, "close": 23270.6,
        "volume": 1.0, "source": "TEST",
        "market_timestamp": datetime.now().isoformat(),
    }
    sess = MagicMock()
    sess.post.return_value = _LtpResp()

    with patch("src.execution.dhan_contract_resolver._pace_dhan_request"), \
         patch.object(lmb, "get_today_session_bar", return_value=fresh_bar):
        mkt = DhanContractResolver.get_live_market_state(dhan_session=sess)

    assert mkt is not None
    assert mkt["nifty_spot"] == 23270.6
    assert mkt["nifty_open"] == 23212.05


def test_missing_index_timestamp_fails_closed():
    """A bar with no exchange timestamp is undateable and must be refused."""
    from src.execution.dhan_contract_resolver import DhanContractResolver

    undateable = {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5,
                  "volume": 1.0, "source": "TEST"}
    sess = MagicMock()
    sess.post.return_value = _LtpResp()

    with patch("src.execution.dhan_contract_resolver._pace_dhan_request"), \
         patch.object(lmb, "get_today_session_bar", return_value=undateable):
        assert DhanContractResolver.get_live_market_state(dhan_session=sess) is None


# ─────────── VERIFIED OPTION-QUOTE CONTRACT (unchanged, now asserted) ───────────

def test_option_quote_timestamp_format_matches_live_api():
    """`last_trade_time` arrives as '17/09/2026 15:39:59'; the parser must accept it."""
    from src.execution.dhan_contract_resolver import is_quote_fresh

    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    assert is_quote_fresh(now) is True

    stale = (datetime.now() - timedelta(hours=6)).strftime("%d/%m/%Y %H:%M:%S")
    assert is_quote_fresh(stale) is False


def test_broker_position_schema_matches_official_docs():
    """
    Official Dhan docs: GET /positions returns a BARE ARRAY whose rows carry
    `securityId` and `netQty`. Verified live: the endpoint returned [].
    """
    from src.execution.position_reconciler import BrokerStateStatus, parse_broker_payload

    assert parse_broker_payload([]).status is BrokerStateStatus.AVAILABLE_FLAT

    row = {
        "dhanClientId": "1000000000", "tradingSymbol": "NIFTY-Sep2026-23250-CE",
        "securityId": "56983", "positionType": "LONG", "exchangeSegment": "NSE_FNO",
        "productType": "INTRADAY", "buyAvg": 150.0, "buyQty": 65, "costPrice": 150.0,
        "sellAvg": 0.0, "sellQty": 0, "netQty": 65, "realizedProfit": 0.0,
        "unrealizedProfit": 520.0, "drvExpiryDate": "2026-09-22",
        "drvOptionType": "CALL", "drvStrikePrice": 23250.0,
    }
    snap = parse_broker_payload([row])
    assert snap.status is BrokerStateStatus.AVAILABLE_POSITIONS
    assert snap.as_quantity_map() == {"56983": 65.0}
    assert snap.positions[0].trading_symbol == "NIFTY-Sep2026-23250-CE"

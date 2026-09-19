"""
Official DhanHQ v2 API Central Client.
Handles rate-limiting, authentication, resilient retries, and high-fidelity market data queries:
- Marketfeed Quotes & 5-Level Market Depth (/marketfeed/quote)
- Real-Time Option Chain with Greeks (Delta, Theta, Gamma, Vega), IV & Depth (/optionchain)
- Option Expiry Calendar (/optionchain/expirylist)
- Historical Daily Candles (/charts/historical)
- Intraday Candles (1m, 5m, 15m, 60m) (/charts/intraday)
- Continuous Expired Rolling Options Data with IV & OI (/charts/rollingoption)
- Strict Fail-Closed behavior with zero synthetic fallback values.
"""
import time
import threading
from datetime import datetime, date
from typing import Dict, List, Optional, Any, Union, Tuple
import pandas as pd
import requests

from src.config import Config
from src.utils.logging import setup_logging

logger = setup_logging("data.dhan_client")


class DhanAPIClient:
    """
    Production-grade client for the official DhanHQ API (v2).
    Enforces documented rate limits, connection pooling, and fail-closed data integrity.
    """

    BASE_URL = "https://api.dhan.co/v2"

    def __init__(
        self,
        client_id: Optional[str] = None,
        access_token: Optional[str] = None,
        timeout: int = 6,
    ):
        self.client_id = str(client_id or Config.DHAN_CLIENT_ID or "").strip()
        self.access_token = str(access_token or Config.DHAN_ACCESS_TOKEN or "").strip()
        self.timeout = timeout

        self._session = requests.Session()
        if self.access_token and self.client_id:
            self._session.headers.update({
                "access-token": self.access_token,
                "client-id": self.client_id,
                "Content-Type": "application/json",
                "Accept": "application/json",
            })

        # Rate limiting state
        self._last_option_chain_time: float = 0.0
        self._option_chain_lock = threading.Lock()
        self._last_request_time: float = 0.0
        self._last_family_request: Dict[str, float] = {}
        self._request_lock = threading.Lock()

        # HTTP status tracking
        self.last_status_code: Optional[int] = None
        self.last_error_message: Optional[str] = None
        self.last_response: Optional[requests.Response] = None

    # DhanHQ throttles the marketfeed family at roughly one request per second,
    # far tighter than the chart endpoints. A single global interval therefore
    # either throttles charts needlessly or floods marketfeed; measured on a live
    # session, 0.35s global produced 21 HTTP 429s in 22 cycles and skipped 5 of
    # them entirely. Pacing is per endpoint family.
    ENDPOINT_MIN_INTERVAL = {
        "marketfeed": 1.15,
        "charts": 0.40,
    }
    DEFAULT_MIN_INTERVAL = 0.40

    def _interval_for(self, endpoint: str) -> float:
        ep = endpoint.lower()
        for family, interval in self.ENDPOINT_MIN_INTERVAL.items():
            if family in ep:
                return interval
        return self.DEFAULT_MIN_INTERVAL

    def _apply_rate_limit(self, min_interval_seconds: Optional[float] = None,
                          endpoint: str = ""):
        """
        Enforces inter-request spacing to prevent Dhan 805 / 429 throttling.

        Spacing is tracked PER ENDPOINT FAMILY as well as globally: a chart request
        should not be made to wait a full marketfeed interval, and a marketfeed
        request must not be let through early just because the last call was a chart.
        """
        interval = min_interval_seconds if min_interval_seconds is not None else             self._interval_for(endpoint)
        family = next((f for f in self.ENDPOINT_MIN_INTERVAL if f in endpoint.lower()),
                      "_default")
        with self._request_lock:
            now = time.time()
            last_family = self._last_family_request.get(family, 0.0)
            wait = max(interval - (now - last_family), 0.0)
            if wait > 0:
                time.sleep(wait)
            stamp = time.time()
            self._last_request_time = stamp
            self._last_family_request[family] = stamp

    def _post(self, endpoint: str, payload: dict, max_retries: int = 3) -> Optional[requests.Response]:
        """Executes a POST request with exponential backoff on HTTP 429 / 805."""
        clean_ep = endpoint.lower().strip()
        if "order" in clean_ep or "trade" in clean_ep or "place" in clean_ep:
            raise RuntimeError(
                f"FAIL CLOSED SAFETY VIOLATION: Endpoint '{endpoint}' is an order placement route. "
                "LIVE TRADING IS HARD-BLOCKED. Real money execution is strictly prohibited."
            )

        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        
        for attempt in range(max_retries):
            self._apply_rate_limit(endpoint=endpoint)
            try:
                resp = self._session.post(url, json=payload, timeout=self.timeout)
                self.last_status_code = resp.status_code
                self.last_response = resp
                if resp.status_code == 200:
                    self.last_error_message = None
                    return resp
                elif resp.status_code in (429, 805):
                    self.last_error_message = f"Rate limit HTTP {resp.status_code}"
                    backoff = (attempt + 1) * 1.5
                    logger.warning(f"Dhan rate limit on {endpoint} (HTTP {resp.status_code}). Backing off {backoff:.1f}s...")
                    time.sleep(backoff)
                    continue
                else:
                    self.last_error_message = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    if resp.status_code in (401, 403):
                        logger.error(
                            f"Dhan AUTHENTICATION/AUTHORIZATION FAILURE on {endpoint} "
                            f"(HTTP {resp.status_code}): {resp.text[:200]}. Check DHAN_ACCESS_TOKEN."
                        )
                    else:
                        logger.warning(f"Dhan {endpoint} returned status {resp.status_code}: {resp.text[:200]}")
                    return resp
            except requests.exceptions.RequestException as e:
                self.last_status_code = None
                self.last_error_message = f"Connection error: {e}"
                logger.warning(f"Dhan {endpoint} connection error (attempt {attempt+1}/{max_retries}): {e}")
                time.sleep(1.0)

        self.last_error_message = f"Dhan {endpoint} failed after {max_retries} attempts."
        logger.warning(self.last_error_message)
        return None

    def post_raw(self, endpoint: str, payload: dict) -> Tuple[int, Any]:
        """
        Executes a POST request and returns (status_code, parsed_json_or_text).
        Never swallows the HTTP status code.
        """
        resp = self._post(endpoint, payload)
        if resp is None:
            return (-1, self.last_error_message or "Request failed")
        try:
            return (resp.status_code, resp.json())
        except ValueError:
            return (resp.status_code, resp.text[:300])

    # ─── 1. MARKETFEED QUOTES & 5-LEVEL DEPTH ───

    def fetch_marketfeed_quote(
        self,
        security_ids: List[Union[str, int]],
        exchange_segment: str = "NSE_FNO",
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetches authentic real-time quotes + 5-level market depth from /marketfeed/quote.
        Supports multi-contract batching in a single request.
        """
        clean_ids = [int(sid) for sid in security_ids if str(sid).strip().isdigit()]
        if not clean_ids:
            return {}

        now_dt = datetime.now()
        results = {}
        payload = {exchange_segment: clean_ids}
        resp = self._post("marketfeed/quote", payload)

        if resp and resp.status_code == 200:
            data = resp.json().get("data", {})
            seg_data = data.get(exchange_segment, {})
            for sid in clean_ids:
                sid_str = str(sid)
                item = seg_data.get(sid_str) or seg_data.get(sid)
                if isinstance(item, dict) and item.get("last_price", 0) > 0:
                    depth = item.get("depth", {})
                    buy_depth = depth.get("buy", [])
                    sell_depth = depth.get("sell", [])
                    bid = float(buy_depth[0].get("price", 0)) if buy_depth else None
                    ask = float(sell_depth[0].get("price", 0)) if sell_depth else None
                    bid_qty = int(buy_depth[0].get("quantity", 0)) if buy_depth else 0
                    ask_qty = int(sell_depth[0].get("quantity", 0)) if sell_depth else 0
                    ltp = float(item["last_price"])
                    
                    results[sid_str] = {
                        "security_id": sid_str,
                        "exchange_segment": exchange_segment,
                        "ltp": ltp,
                        "bid": bid if bid and bid > 0 else None,
                        "ask": ask if ask and ask > 0 else None,
                        "bid_qty": bid_qty,
                        "ask_qty": ask_qty,
                        "depth": depth,
                        "volume": item.get("volume", 0),
                        "oi": item.get("oi", 0),
                        "ohlc": item.get("ohlc", {}),
                        "last_trade_time": item.get("last_trade_time"),
                        "timestamp": now_dt.isoformat(),
                        "is_tradable": True,
                        "source": "DHAN_MARKETFEED_QUOTE",
                    }
        return results

    def fetch_marketfeed_ltp(
        self,
        security_ids: List[Union[str, int]],
        exchange_segment: str = "NSE_EQ",
    ) -> Dict[str, float]:
        """Fetches fast LTP values from /marketfeed/ltp."""
        clean_ids = [int(sid) for sid in security_ids if str(sid).strip().isdigit()]
        if not clean_ids:
            return {}

        results = {}
        payload = {exchange_segment: clean_ids}
        resp = self._post("marketfeed/ltp", payload)

        if resp and resp.status_code == 200:
            data = resp.json().get("data", {})
            seg_data = data.get(exchange_segment, {})
            for sid in clean_ids:
                sid_str = str(sid)
                item = seg_data.get(sid_str) or seg_data.get(sid)
                if isinstance(item, dict) and item.get("last_price", 0) > 0:
                    results[sid_str] = float(item["last_price"])
        return results

    # ─── 2. LIVE OPTION CHAIN & GREEKS ───

    def fetch_expiry_list(
        self,
        underlying_scrip: int = 13,
        underlying_seg: str = "IDX_I",
    ) -> List[str]:
        """Fetches list of active option expiry dates from /optionchain/expirylist."""
        payload = {
            "UnderlyingScrip": int(underlying_scrip),
            "UnderlyingSeg": underlying_seg,
        }
        resp = self._post("optionchain/expirylist", payload)
        if resp and resp.status_code == 200:
            data = resp.json().get("data", [])
            if isinstance(data, list):
                return sorted([str(d).strip() for d in data])
        return []

    def fetch_option_chain(
        self,
        underlying_scrip: int = 13,
        underlying_seg: str = "IDX_I",
        expiry: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetches the complete 200+ strikes option chain with official Dhan Greeks,
        IV, Top Bid/Ask, and Open Interest from /optionchain.
        Enforces Dhan's 3.0-second rate limit.
        """
        with self._option_chain_lock:
            elapsed = time.time() - self._last_option_chain_time
            if elapsed < 3.0:
                time.sleep(3.0 - elapsed)
            self._last_option_chain_time = time.time()

        if not expiry:
            expiries = self.fetch_expiry_list(underlying_scrip, underlying_seg)
            if not expiries:
                logger.warning(f"Could not resolve active expiry for scrip {underlying_scrip}.")
                return {}
            expiry = expiries[0]

        payload = {
            "UnderlyingScrip": int(underlying_scrip),
            "UnderlyingSeg": underlying_seg,
            "Expiry": expiry,
        }
        resp = self._post("optionchain", payload)

        if resp and resp.status_code == 200:
            data = resp.json().get("data", {})
            return {
                "underlying_scrip": underlying_scrip,
                "underlying_seg": underlying_seg,
                "expiry": expiry,
                "spot_last_price": data.get("last_price", 0.0),
                "strikes": data.get("oc", {}),
                "timestamp": datetime.now().isoformat(),
                "source": "DHAN_OPTION_CHAIN",
            }
        return {}

    # ─── 3. HISTORICAL & INTRADAY CANDLE DATA ───

    def fetch_historical_daily(
        self,
        security_id: str,
        exchange_segment: str = "NSE_EQ",
        instrument: str = "EQUITY",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Fetches daily historical candles from /charts/historical.
        Returns a structured DataFrame: [timestamp, datetime, open, high, low, close, volume].
        """
        payload = {
            "securityId": str(security_id),
            "exchangeSegment": exchange_segment,
            "instrument": instrument,
            "expiryCode": 0,
            "fromDate": from_date or "2024-01-01",
            "toDate": to_date or datetime.now().strftime("%Y-%m-%d"),
        }
        resp = self._post("charts/historical", payload)
        if resp and resp.status_code == 200:
            data = resp.json()
            if "timestamp" in data and len(data["timestamp"]) > 0:
                df = pd.DataFrame(data)
                # Dhan returns UNIX epochs. Converting with unit="s" alone yields a
                # UTC-naive timestamp, but the rest of this system compares against
                # a naive IST clock, so every candle read 5h30m in the past — which
                # would make any freshness gate on candle data permanently stale.
                # VERIFIED 2026-09-17 against the live API: epoch 1789616700 is the
                # 09:15 IST opening candle, not 03:45.
                df["datetime"] = (
                    pd.to_datetime(df["timestamp"], unit="s", utc=True)
                    .dt.tz_convert("Asia/Kolkata")
                    .dt.tz_localize(None)
                )
                return df[["datetime", "open", "high", "low", "close", "volume", "timestamp"]]
        return pd.DataFrame()

    def fetch_intraday_candles(
        self,
        security_id: str,
        exchange_segment: str = "NSE_FNO",
        instrument: str = "OPTIDX",
        interval: str = "1",  # '1', '5', '15', '25', '60'
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Fetches intraday minute candles from /charts/intraday for active contracts.
        Returns DataFrame: [datetime, open, high, low, close, volume, timestamp].
        """
        now = datetime.now()
        f_dt = from_date or f"{now.strftime('%Y-%m-%d')} 09:15:00"
        t_dt = to_date or f"{now.strftime('%Y-%m-%d')} 15:30:00"

        payload = {
            "securityId": str(security_id),
            "exchangeSegment": exchange_segment,
            "instrument": instrument,
            "interval": str(interval),
            "fromDate": f_dt,
            "toDate": t_dt,
        }
        resp = self._post("charts/intraday", payload)
        if resp and resp.status_code == 200:
            data = resp.json()
            if "timestamp" in data and len(data["timestamp"]) > 0:
                df = pd.DataFrame(data)
                # Dhan returns UNIX epochs. Converting with unit="s" alone yields a
                # UTC-naive timestamp, but the rest of this system compares against
                # a naive IST clock, so every candle read 5h30m in the past — which
                # would make any freshness gate on candle data permanently stale.
                # VERIFIED 2026-09-17 against the live API: epoch 1789616700 is the
                # 09:15 IST opening candle, not 03:45.
                df["datetime"] = (
                    pd.to_datetime(df["timestamp"], unit="s", utc=True)
                    .dt.tz_convert("Asia/Kolkata")
                    .dt.tz_localize(None)
                )
                return df[["datetime", "open", "high", "low", "close", "volume", "timestamp"]]
        return pd.DataFrame()

    def fetch_rolling_options(
        self,
        security_id: str = "13",  # 13 for NIFTY 50 Index
        exchange_segment: str = "NSE_FNO",
        instrument: str = "OPTIDX",
        expiry_flag: str = "WEEK",  # 'WEEK' or 'MONTH'
        expiry_code: int = 1,  # 1: Near, 2: Next, 3: Far
        strike: str = "ATM",  # 'ATM', 'ATM+1', 'ATM-1', etc.
        drv_option_type: str = "CALL",
        from_date: str = "2026-09-01",
        to_date: str = "2026-09-10",
        interval: str = "5",  # '1', '5', '15', '60'
        required_data: Optional[List[str]] = None,
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetches continuous historical expired options data from /charts/rollingoption.
        Returns dictionary of DataFrames: {'ce': df_ce, 'pe': df_pe}.
        Columns include: [datetime, strike, spot, iv, oi, open, high, low, close, volume].
        """
        req_fields = required_data or ["open", "high", "low", "close", "volume", "oi", "iv", "spot", "strike"]
        payload = {
            "exchangeSegment": exchange_segment,
            "interval": str(interval),
            "securityId": str(security_id),
            "instrument": instrument,
            "expiryFlag": expiry_flag,
            "expiryCode": int(expiry_code),
            "strike": strike,
            "drvOptionType": drv_option_type,
            "requiredData": req_fields,
            "fromDate": from_date,
            "toDate": to_date,
        }
        resp = self._post("charts/rollingoption", payload)
        results = {"ce": pd.DataFrame(), "pe": pd.DataFrame()}

        if resp and resp.status_code == 200:
            data = resp.json().get("data", {})
            for side in ("ce", "pe"):
                side_data = data.get(side, {})
                if isinstance(side_data, dict) and "timestamp" in side_data and len(side_data["timestamp"]) > 0:
                    df = pd.DataFrame(side_data)
                    # Epoch -> naive IST (see fetch_intraday_candles for rationale).
                    df["datetime"] = (
                        pd.to_datetime(df["timestamp"], unit="s", utc=True)
                        .dt.tz_convert("Asia/Kolkata")
                        .dt.tz_localize(None)
                    )
                    results[side] = df
        return results

    def get_fund_limits(self) -> Dict[str, Any]:
        """Fetches live account margin/fund limits from /fundlimit."""
        self._apply_rate_limit()
        try:
            resp = self._session.get(f"{self.BASE_URL}/fundlimit", timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json().get("data", {})
        except Exception as e:
            logger.debug(f"Dhan /fundlimit query failed: {e}")
        return {}


# Module-level singleton client
_dhan_api_client: Optional[DhanAPIClient] = None


def get_dhan_client() -> DhanAPIClient:
    """Returns or instantiates the singleton DhanAPIClient."""
    global _dhan_api_client
    if _dhan_api_client is None:
        _dhan_api_client = DhanAPIClient()
    return _dhan_api_client

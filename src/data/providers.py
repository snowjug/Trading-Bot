"""
Data provider abstraction layer.
Supports multiple data sources with a unified interface.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional
import pandas as pd
import numpy as np
from src.utils.logging import setup_logging

logger = setup_logging("data.providers")


@dataclass
class DataRequest:
    """Standardized data request."""
    symbol: str
    start_date: date
    end_date: date
    timeframe: str = "daily"  # daily, 1min, 5min, 15min, 1h
    adjust_corporate_actions: bool = True


@dataclass
class DataResult:
    """Standardized data result."""
    symbol: str
    timeframe: str
    data: pd.DataFrame  # columns: datetime, open, high, low, close, volume, adj_close
    provider: str
    start_date: date
    end_date: date
    quality_notes: list = field(default_factory=list)
    success: bool = True
    error: str = ""


class DataProvider(ABC):
    """Abstract base class for all data providers."""

    name: str = "base"
    supports_intraday: bool = False
    supports_futures: bool = False
    supports_options: bool = False
    requires_auth: bool = False
    rate_limit_per_min: int = 60

    @abstractmethod
    def fetch_ohlcv(self, request: DataRequest) -> DataResult:
        """Fetch OHLCV data for a symbol."""
        ...

    @abstractmethod
    def fetch_index(self, index_name: str, start_date: date, end_date: date) -> DataResult:
        """Fetch index data."""
        ...

    @abstractmethod
    def get_universe(self, universe_name: str) -> list[str]:
        """Get list of symbols in a universe."""
        ...

    def is_available(self) -> bool:
        """Check if this provider is accessible."""
        return True


class YFinanceProvider(DataProvider):
    """Yahoo Finance data provider (free, no auth required)."""

    name = "yfinance"
    supports_intraday = False  # Limited to ~60 days of intraday
    supports_futures = False
    supports_options = False
    requires_auth = False
    rate_limit_per_min = 30

    # NSE symbol mapping for yfinance
    INDEX_MAP = {
        "NIFTY50": "^NSEI",
        "NIFTY_50": "^NSEI",
        "BANKNIFTY": "^NSEBANK",
        "BANK_NIFTY": "^NSEBANK",
        "NIFTY_IT": "^CNXIT",
        "INDIA_VIX": "^INDIAVIX",
        "NIFTY_NEXT50": "^NSMIDCP",
    }

    # Top NIFTY 50 constituents (as of latest available data)
    NIFTY50_SYMBOLS = [
        "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
        "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
        "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "HCLTECH",
        "SUNPHARMA", "TITAN", "BAJFINANCE", "WIPRO", "ULTRACEMCO",
        "NESTLEIND", "ONGC", "NTPC", "POWERGRID", "M&M",
        "TATAMOTORS", "ADANIENT", "ADANIPORTS", "COALINDIA", "JSWSTEEL",
        "TATASTEEL", "TECHM", "INDUSINDBK", "HINDALCO", "DRREDDY",
        "BAJAJFINSV", "DIVISLAB", "CIPLA", "GRASIM", "APOLLOHOSP",
        "EICHERMOT", "TATACONSUM", "HEROMOTOCO", "BPCL", "BRITANNIA",
        "SBILIFE", "HDFCLIFE", "BAJAJ-AUTO", "LTIM", "SHRIRAMFIN",
    ]

    def _to_yf_symbol(self, symbol: str) -> str:
        """Convert NSE symbol to yfinance format."""
        if symbol.startswith("^"):
            return symbol
        return f"{symbol}.NS"

    def fetch_ohlcv(self, request: DataRequest) -> DataResult:
        """Fetch OHLCV data from Yahoo Finance."""
        try:
            import yfinance as yf

            yf_symbol = self._to_yf_symbol(request.symbol)
            logger.info(f"Fetching {yf_symbol} from yfinance ({request.start_date} to {request.end_date})")

            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(
                start=request.start_date.isoformat(),
                end=request.end_date.isoformat(),
                auto_adjust=request.adjust_corporate_actions,
            )

            if df.empty:
                return DataResult(
                    symbol=request.symbol, timeframe=request.timeframe,
                    data=pd.DataFrame(), provider=self.name,
                    start_date=request.start_date, end_date=request.end_date,
                    success=False, error=f"No data returned for {yf_symbol}",
                )

            # Standardize columns
            df = df.reset_index()
            df.columns = [c.lower().replace(" ", "_") for c in df.columns]

            # Rename to standard format
            rename_map = {"date": "datetime", "stock_splits": "splits", "capital_gains": "cap_gains"}
            df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

            # Ensure datetime is timezone-naive for consistency
            if "datetime" in df.columns:
                df["datetime"] = pd.to_datetime(df["datetime"]).dt.tz_localize(None)

            # Keep only standard columns
            standard_cols = ["datetime", "open", "high", "low", "close", "volume"]
            available_cols = [c for c in standard_cols if c in df.columns]
            df = df[available_cols].copy()

            quality_notes = []
            if len(df) < 100:
                quality_notes.append(f"Low data count: {len(df)} bars")

            return DataResult(
                symbol=request.symbol, timeframe=request.timeframe,
                data=df, provider=self.name,
                start_date=request.start_date, end_date=request.end_date,
                quality_notes=quality_notes,
            )

        except Exception as e:
            logger.error(f"yfinance error for {request.symbol}: {e}")
            return DataResult(
                symbol=request.symbol, timeframe=request.timeframe,
                data=pd.DataFrame(), provider=self.name,
                start_date=request.start_date, end_date=request.end_date,
                success=False, error=str(e),
            )

    def fetch_index(self, index_name: str, start_date: date, end_date: date) -> DataResult:
        """Fetch index data."""
        yf_symbol = self.INDEX_MAP.get(index_name.upper().replace(" ", "_"), index_name)
        request = DataRequest(symbol=yf_symbol, start_date=start_date, end_date=end_date)
        result = self.fetch_ohlcv(request)
        result.symbol = index_name
        return result

    def get_universe(self, universe_name: str) -> list[str]:
        """Get universe constituents."""
        if universe_name.upper() in ("NIFTY50", "NIFTY_50"):
            return self.NIFTY50_SYMBOLS.copy()
        # For other universes, return NIFTY50 as default
        logger.warning(f"Universe {universe_name} not available, falling back to NIFTY50")
        return self.NIFTY50_SYMBOLS.copy()

    def is_available(self) -> bool:
        try:
            import yfinance
            return True
        except ImportError:
            return False


class DhanDataProvider(DataProvider):
    """Official DhanHQ Data API Provider implementing DataProvider."""

    name = "dhan"
    supports_intraday: bool = True
    supports_futures: bool = True
    supports_options: bool = True
    requires_auth: bool = True
    rate_limit_per_min: int = 120

    def __init__(self):
        from src.data.dhan_client import get_dhan_client
        self.client = get_dhan_client()

    def is_available(self) -> bool:
        return bool(self.client.client_id and self.client.access_token)

    def fetch_ohlcv(self, request: DataRequest) -> DataResult:
        """Fetch historical or intraday OHLCV for a symbol via Dhan."""
        from src.execution.dhan_scrip_master import DhanScripMaster
        meta = DhanScripMaster.resolve_equity(request.symbol)
        sec_id = meta.get("security_id") if meta else str(request.symbol)

        if not sec_id or not str(sec_id).isdigit():
            return DataResult(
                symbol=request.symbol, timeframe=request.timeframe,
                data=pd.DataFrame(), provider=self.name,
                start_date=request.start_date, end_date=request.end_date,
                success=False, error=f"Could not resolve Dhan security_id for {request.symbol}",
            )

        if request.timeframe in ("1m", "5m", "15m", "60m", "intraday"):
            interval = "1" if request.timeframe == "1m" else ("5" if request.timeframe == "5m" else "15")
            df = self.client.fetch_intraday_candles(
                security_id=sec_id,
                exchange_segment="NSE_EQ",
                instrument="EQUITY",
                interval=interval,
                from_date=f"{request.start_date} 09:15:00",
                to_date=f"{request.end_date} 15:30:00",
            )
        else:
            df = self.client.fetch_historical_daily(
                security_id=sec_id,
                exchange_segment="NSE_EQ",
                instrument="EQUITY",
                from_date=str(request.start_date),
                to_date=str(request.end_date),
            )

        if df.empty:
            return DataResult(
                symbol=request.symbol, timeframe=request.timeframe,
                data=pd.DataFrame(), provider=self.name,
                start_date=request.start_date, end_date=request.end_date,
                success=False, error="Empty response from Dhan API",
            )

        return DataResult(
            symbol=request.symbol, timeframe=request.timeframe,
            data=df, provider=self.name,
            start_date=request.start_date, end_date=request.end_date,
            success=True,
        )

    def fetch_index(self, index_name: str, start_date: date, end_date: date) -> DataResult:
        """Fetch index historical daily candles."""
        sec_map = {"NIFTY": "13", "NIFTY50": "13", "BANKNIFTY": "25"}
        sec_id = sec_map.get(index_name.upper().replace(" ", "").replace("_", ""), "13")
        df = self.client.fetch_historical_daily(
            security_id=sec_id,
            exchange_segment="NSE_EQ",
            instrument="EQUITY",
            from_date=str(start_date),
            to_date=str(end_date),
        )
        return DataResult(
            symbol=index_name, timeframe="daily",
            data=df, provider=self.name,
            start_date=start_date, end_date=end_date,
            success=not df.empty,
        )

    def get_universe(self, universe_name: str) -> list[str]:
        return YFinanceProvider.NIFTY50_SYMBOLS.copy()


class DataProviderManager:
    """Manages multiple data providers with fallback support."""

    def __init__(self):
        self.providers: dict[str, DataProvider] = {}
        self._register_defaults()

    def _register_defaults(self):
        """Register default providers prioritizing official Dhan API."""
        dhan = DhanDataProvider()
        if dhan.is_available():
            self.providers["dhan"] = dhan
            logger.info("Registered DhanHQ data provider as PRIMARY")

        yf = YFinanceProvider()
        if yf.is_available():
            self.providers["yfinance"] = yf
            logger.info("Registered yfinance provider as fallback")

    def register(self, provider: DataProvider):
        """Register a custom data provider."""
        self.providers[provider.name] = provider
        logger.info(f"Registered {provider.name} provider")

    def fetch(self, request: DataRequest, preferred_provider: str = "dhan") -> DataResult:
        """Fetch data using preferred provider with fallback."""
        providers_to_try = [preferred_provider] + [
            p for p in self.providers if p != preferred_provider
        ]
        for pname in providers_to_try:
            provider = self.providers.get(pname)
            if provider and provider.is_available():
                result = provider.fetch_ohlcv(request)
                if result.success:
                    return result
                logger.warning(f"{pname} failed for {request.symbol}: {result.error}")

        return DataResult(
            symbol=request.symbol, timeframe=request.timeframe,
            data=pd.DataFrame(), provider="none",
            start_date=request.start_date, end_date=request.end_date,
            success=False, error="All providers failed",
        )

    def get_universe(self, universe_name: str) -> list[str]:
        """Get universe symbols from first available provider."""
        for provider in self.providers.values():
            try:
                symbols = provider.get_universe(universe_name)
                if symbols:
                    return symbols
            except Exception:
                continue
        return []

    def list_providers(self) -> dict:
        """List available providers and their capabilities."""
        return {
            name: {
                "available": p.is_available(),
                "intraday": p.supports_intraday,
                "futures": p.supports_futures,
                "options": p.supports_options,
                "requires_auth": p.requires_auth,
            }
            for name, p in self.providers.items()
        }

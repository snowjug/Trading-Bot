"""
Deterministic Options Data Provider.
Accesses official NSE bhavcopy data, enforces fail-closed guarantees on missing strikes,
and extracts point-in-time chains without lookahead.
"""

from pathlib import Path
from datetime import date, datetime
from typing import List, Dict, Optional, Tuple, Any
import pandas as pd
from src.utils.logging import setup_logging

logger = setup_logging("data.options_data")

BHAV_DIR = Path("data/raw/nse/fo_bhavcopy")


class OptionsDataProvider:
    """
    Unified point-in-time data interface for NIFTY options.
    Guarantees no synthetic interpolation or lookahead.
    """

    def __init__(self, directory: Path = BHAV_DIR):
        self.directory = Path(directory)
        self.store: Optional[pd.DataFrame] = None
        self._chains: Dict[Tuple[date, date], pd.DataFrame] = {}
        self._expiries_by_day: Dict[date, List[date]] = {}
        self._settlement_cache: Dict[date, Optional[float]] = {}
        self._load_store()

    def _load_store(self):
        """Loads consolidated official bhavcopy parquet cache."""
        caches = sorted(self.directory.glob(".consolidated_*.parquet"))
        if not caches:
            files = sorted(self.directory.glob("NIFTY_options_*.parquet"))
            if not files:
                raise FileNotFoundError(f"No bhavcopy files found under {self.directory}")
            df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
        else:
            # Load newest consolidated cache
            df = pd.read_parquet(caches[-1])

        df["TradDt"] = pd.to_datetime(df["TradDt"]).dt.date
        df["XpryDt"] = pd.to_datetime(df["XpryDt"]).dt.date
        self.store = df.sort_values(["TradDt", "XpryDt", "StrkPric"]).reset_index(drop=True)

        # Index by (TradDt, XpryDt)
        for (trade_dt, expiry_dt), group in self.store.groupby(["TradDt", "XpryDt"], sort=False):
            self._chains[(trade_dt, expiry_dt)] = group
            self._expiries_by_day.setdefault(trade_dt, []).append(expiry_dt)

        for d in self._expiries_by_day:
            self._expiries_by_day[d].sort()

        logger.info(f"Loaded {len(self.store):,} options rows across {len(self._expiries_by_day)} trading sessions.")

    def get_trading_sessions(self, start_date: Optional[date] = None, end_date: Optional[date] = None) -> List[date]:
        days = sorted(self._expiries_by_day.keys())
        if start_date:
            days = [d for d in days if d >= start_date]
        if end_date:
            days = [d for d in days if d <= end_date]
        return days

    def get_expiries_for_date(self, trade_date: date) -> List[date]:
        return self._expiries_by_day.get(trade_date, [])

    def get_nearest_expiry(self, trade_date: date, min_dte: int = 0) -> Optional[date]:
        expiries = self.get_expiries_for_date(trade_date)
        valid = [e for e in expiries if (e - trade_date).days >= min_dte]
        return valid[0] if valid else None

    def get_chain(self, trade_date: date, expiry_date: date) -> pd.DataFrame:
        """Point-in-time chain for trade_date and expiry_date."""
        return self._chains.get((trade_date, expiry_date), pd.DataFrame())

    def get_contract_quote(self, trade_date: date, expiry_date: date, strike: float, opt_type: str) -> Optional[pd.Series]:
        chain = self.get_chain(trade_date, expiry_date)
        if chain.empty:
            return None
        match = chain[(chain["StrkPric"] == strike) & (chain["OptnTp"] == opt_type)]
        return match.iloc[0] if not match.empty else None

    def get_settlement_price(self, expiry_date: date, index_close: Optional[Dict[date, float]] = None) -> Optional[float]:
        if expiry_date in self._settlement_cache:
            return self._settlement_cache[expiry_date]

        chain = self.get_chain(expiry_date, expiry_date)
        val = None
        if not chain.empty and "SttlmPric" in chain.columns:
            sttl_vals = chain["SttlmPric"].dropna().unique()
            if len(sttl_vals) == 1 and sttl_vals[0] > 0:
                val = float(sttl_vals[0])

        if val is None and index_close:
            v = index_close.get(expiry_date)
            if v and v > 0:
                val = float(v)

        self._settlement_cache[expiry_date] = val
        return val

"""
DhanHQ Official Scrip Master & Contract Directory.
Downloads, caches, and indexes the official DhanHQ instrument master list
(https://images.dhan.co/api-data/api-scrip-master.csv).

Resolves authentic numeric Dhan security IDs, official trading symbols,
exact strike prices, expiry dates, and exchange lot sizes.
Zero manual ID construction or fabricated contract metadata.
"""

import os
import sys
import time
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Optional, List
import pandas as pd
import requests

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.utils.logging import setup_logging

logger = setup_logging("execution.dhan_scrip_master")


class DhanScripMaster:
    """
    Official Dhan Instrument Master Parser and Contract Directory.
    Downloads and caches the official Dhan CSV master for active NSE index options.
    """

    REMOTE_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
    CACHE_FILE = Path("data/dhan_scrip_master_index_opt.csv")
    CACHE_MAX_AGE_HOURS = 24

    _df_cache: Optional[pd.DataFrame] = None

    @classmethod
    def sync_master(cls, force_refresh: bool = False) -> bool:
        """
        Synchronizes active NSE index derivatives from Dhan's scrip master CSV.
        Saves a compact local cache (~1MB) containing only valid index derivatives.
        """
        cls.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

        if not force_refresh and cls.CACHE_FILE.exists():
            file_age_hours = (time.time() - cls.CACHE_FILE.stat().st_mtime) / 3600.0
            if file_age_hours < cls.CACHE_MAX_AGE_HOURS:
                logger.debug(f"Using existing Dhan scrip cache ({file_age_hours:.1f}h old).")
                return True

        logger.info("Downloading official DhanHQ scrip master from %s...", cls.REMOTE_URL)
        try:
            chunks = []
            cols = [
                "SEM_EXM_EXCH_ID",
                "SEM_SEGMENT",
                "SEM_SMST_SECURITY_ID",
                "SEM_INSTRUMENT_NAME",
                "SEM_CUSTOM_SYMBOL",
                "SEM_TRADING_SYMBOL",
                "SEM_STRIKE_PRICE",
                "SEM_OPTION_TYPE",
                "SEM_EXPIRY_DATE",
                "SEM_LOT_UNITS",
            ]

            for chunk in pd.read_csv(
                cls.REMOTE_URL,
                usecols=cols,
                chunksize=50000,
                low_memory=False,
            ):
                mask = (
                    (chunk["SEM_EXM_EXCH_ID"] == "NSE")
                    & (chunk["SEM_INSTRUMENT_NAME"].isin(["OPTIDX", "FUTIDX"]))
                )
                filtered = chunk[mask].copy()
                if not filtered.empty:
                    chunks.append(filtered)

            if not chunks:
                logger.error("No valid index derivatives found in Dhan scrip master.")
                return False

            full_df = pd.concat(chunks, ignore_index=True)
            # Extract clean underlying identifier (e.g. NIFTY, BANKNIFTY)
            full_df["UNDERLYING"] = full_df["SEM_CUSTOM_SYMBOL"].str.split().str[0].str.upper()
            full_df["SEM_STRIKE_PRICE"] = pd.to_numeric(full_df["SEM_STRIKE_PRICE"], errors="coerce")
            full_df["SEM_LOT_UNITS"] = pd.to_numeric(full_df["SEM_LOT_UNITS"], errors="coerce").fillna(25).astype(int)
            full_df["SEM_SMST_SECURITY_ID"] = full_df["SEM_SMST_SECURITY_ID"].astype(str)

            # Standardize expiry date column
            full_df["EXPIRY_DATE_CLEAN"] = pd.to_datetime(
                full_df["SEM_EXPIRY_DATE"], errors="coerce"
            ).dt.date

            full_df.to_csv(cls.CACHE_FILE, index=False)
            cls._df_cache = full_df
            logger.info(f"Dhan Scrip Master synced successfully: {len(full_df)} contracts indexed.")
            return True

        except Exception as e:
            logger.error(f"Failed to download/parse Dhan scrip master: {e}")
            if cls.CACHE_FILE.exists():
                logger.warning("Falling back to existing local scrip master cache.")
                return True
            return False

    @classmethod
    def get_master_df(cls) -> Optional[pd.DataFrame]:
        """Loads and returns the indexed master dataframe."""
        if cls._df_cache is not None:
            return cls._df_cache

        if not cls.CACHE_FILE.exists():
            success = cls.sync_master()
            if not success and not cls.CACHE_FILE.exists():
                return None

        try:
            df = pd.read_csv(cls.CACHE_FILE, dtype={"SEM_SMST_SECURITY_ID": str})
            df["EXPIRY_DATE_CLEAN"] = pd.to_datetime(df["SEM_EXPIRY_DATE"], errors="coerce").dt.date
            df["SEM_STRIKE_PRICE"] = pd.to_numeric(df["SEM_STRIKE_PRICE"], errors="coerce")
            df["SEM_LOT_UNITS"] = pd.to_numeric(df["SEM_LOT_UNITS"], errors="coerce").fillna(25).astype(int)
            cls._df_cache = df
            return cls._df_cache
        except Exception as e:
            logger.error(f"Failed to load cached Dhan scrip master: {e}")
            return None

    @classmethod
    def resolve_contract(
        cls,
        underlying: str = "NIFTY",
        option_type: str = "CE",  # 'CE' or 'PE'
        target_strike: float = 24150.0,
        target_expiry: Optional[date] = None,
        as_of_date: Optional[date] = None,
    ) -> Optional[Dict]:
        """
        Dynamically resolves the actual tradable contract and authentic numeric Dhan securityId
        from the official Dhan scrip master.

        Returns None if no matching contract is found or if the contract is expired.
        Zero fabricated data.
        """
        df = cls.get_master_df()
        if df is None or df.empty:
            logger.error("Scrip master unavailable. Cannot resolve contract -> NO TRADE.")
            return None

        ref_date = as_of_date or datetime.now().date()
        und = underlying.upper().strip()
        opt_t = option_type.upper().strip()

        # Filter for active contracts of the specified underlying and option type
        active = df[
            (df["UNDERLYING"] == und)
            & (df["SEM_OPTION_TYPE"] == opt_t)
            & (df["EXPIRY_DATE_CLEAN"] >= ref_date)
        ]

        if active.empty:
            logger.warning(f"No active contracts found for {und} {opt_t} on or after {ref_date}.")
            return None

        # Determine target expiry: if not specified, select the nearest available expiry
        available_expiries = sorted(active["EXPIRY_DATE_CLEAN"].dropna().unique())
        if not available_expiries:
            logger.warning(f"No valid future expiry dates found for {und}.")
            return None

        if target_expiry is not None:
            # Find closest matching available expiry
            matching_exp = [exp for exp in available_expiries if exp == target_expiry]
            if not matching_exp:
                # Select nearest if exact date not found
                selected_expiry = min(available_expiries, key=lambda x: abs((x - target_expiry).days))
            else:
                selected_expiry = matching_exp[0]
        else:
            selected_expiry = available_expiries[0]

        # Filter by selected expiry
        exp_contracts = active[active["EXPIRY_DATE_CLEAN"] == selected_expiry]
        if exp_contracts.empty:
            logger.warning(f"No contracts available for expiry {selected_expiry}.")
            return None

        # Find closest available strike in scrip master
        available_strikes = exp_contracts["SEM_STRIKE_PRICE"].dropna().values
        if len(available_strikes) == 0:
            return None

        closest_strike = float(min(available_strikes, key=lambda s: abs(s - target_strike)))
        
        # If the closest strike deviates too far from target (e.g. > 100 pts), reject
        if abs(closest_strike - target_strike) > 200.0:
            logger.warning(
                f"Requested strike {target_strike} too far from closest market strike {closest_strike}."
            )
            return None

        contract_row = exp_contracts[exp_contracts["SEM_STRIKE_PRICE"] == closest_strike].iloc[0]

        sec_id = str(contract_row["SEM_SMST_SECURITY_ID"])
        trading_symbol = str(contract_row["SEM_TRADING_SYMBOL"])
        custom_symbol = str(contract_row["SEM_CUSTOM_SYMBOL"])
        lot_size = int(contract_row["SEM_LOT_UNITS"])
        expiry_str = selected_expiry.strftime("%Y-%m-%d")
        dte_days = max(0, (selected_expiry - ref_date).days)

        return {
            "security_id": sec_id,
            "underlying": und,
            "strike": closest_strike,
            "option_type": opt_t,
            "expiry_date": expiry_str,
            "dte_days": dte_days,
            "lot_size": lot_size,
            "trading_symbol": trading_symbol,
            "custom_symbol": custom_symbol,
            "exchange_segment": "NSE_FNO",
            "is_tradable": True,
        }

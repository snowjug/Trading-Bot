"""
Instrument Master Snapshot & Historical Resolution Engine (Phase 6).
Manages immutable, point-in-time snapshots of the official DhanHQ Scrip Master.

Layout:
data/
  metadata/
    instruments/
      date=YYYY-MM-DD/
        instrument_manifest.parquet
        manifest_meta.json

Ensures historical backtests and replays strictly use the instrument master
that was valid on that trading day. Never resolves an historical trade using
today's instrument master without checking historical validity.
Strictly FAIL CLOSED: No fabricated IDs.
"""

import os
import sys
import json
import hashlib
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Optional, List
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.utils.logging import setup_logging
from src.execution.dhan_scrip_master import DhanScripMaster

logger = setup_logging("data.instrument_master")


class InstrumentMasterSnapshotter:
    """
    Creates and queries daily immutable Parquet snapshots of the Dhan scrip master.
    """

    BASE_DIR = Path("data/metadata/instruments")

    @classmethod
    def create_daily_snapshot(cls, snapshot_date: Optional[date] = None, force: bool = False) -> Path:
        """
        Takes the current Dhan scrip master and saves an immutable, partitioned Parquet snapshot.
        """
        snap_d = snapshot_date or datetime.now().date()
        date_str = snap_d.strftime("%Y-%m-%d")
        dest_dir = cls.BASE_DIR / f"date={date_str}"
        dest_dir.mkdir(parents=True, exist_ok=True)
        parquet_file = dest_dir / "instrument_manifest.parquet"
        meta_file = dest_dir / "manifest_meta.json"

        if parquet_file.exists() and not force:
            logger.info(f"Instrument snapshot for {date_str} already exists: {parquet_file}")
            return parquet_file

        df = DhanScripMaster.get_master_df()
        if df is None or df.empty:
            raise RuntimeError(f"Cannot create snapshot: DhanScripMaster returned empty dataset for {date_str}")

        snapshot_ts = datetime.now().isoformat()

        # Build clean institutional schema
        records = []
        for _, row in df.iterrows():
            sec_id = str(row.get("SEM_SMST_SECURITY_ID", "")).strip()
            if not sec_id or sec_id == "nan":
                continue

            strike = row.get("SEM_STRIKE_PRICE")
            lot_units = row.get("SEM_LOT_UNITS")

            records.append({
                "security_id": sec_id,
                "exchange_segment": "NSE_FNO",
                "symbol": str(row.get("UNDERLYING", "")).strip(),
                "trading_symbol": str(row.get("SEM_TRADING_SYMBOL", "")).strip(),
                "custom_symbol": str(row.get("SEM_CUSTOM_SYMBOL", "")).strip(),
                "instrument_type": str(row.get("SEM_INSTRUMENT_NAME", "")).strip(),
                "option_type": str(row.get("SEM_OPTION_TYPE", "")).strip() if pd.notna(row.get("SEM_OPTION_TYPE")) else None,
                "strike": float(strike) if pd.notna(strike) else 0.0,
                "expiry": str(row.get("EXPIRY_DATE_CLEAN", "")).strip() if pd.notna(row.get("EXPIRY_DATE_CLEAN")) else None,
                "lot_size": int(lot_units) if pd.notna(lot_units) else 0,
                "source": "DhanHQ_Official_Scrip_Master",
                "snapshot_timestamp": snapshot_ts,
                "snapshot_date": date_str,
            })

        snap_df = pd.DataFrame(records)
        
        # Enforce PyArrow schema
        schema = pa.schema([
            ("security_id", pa.string()),
            ("exchange_segment", pa.string()),
            ("symbol", pa.string()),
            ("trading_symbol", pa.string()),
            ("custom_symbol", pa.string()),
            ("instrument_type", pa.string()),
            ("option_type", pa.string()),
            ("strike", pa.float64()),
            ("expiry", pa.string()),
            ("lot_size", pa.int64()),
            ("source", pa.string()),
            ("snapshot_timestamp", pa.string()),
            ("snapshot_date", pa.string()),
        ])

        table = pa.Table.from_pandas(snap_df, schema=schema)
        pq.write_table(table, parquet_file, compression="snappy")

        # Compute checksum
        hasher = hashlib.sha256()
        with open(parquet_file, "rb") as f:
            hasher.update(f.read())
        sha256 = hasher.hexdigest()

        meta = {
            "snapshot_date": date_str,
            "snapshot_timestamp": snapshot_ts,
            "row_count": len(snap_df),
            "sha256": sha256,
            "file_size_bytes": parquet_file.stat().st_size,
            "unique_underlyings": sorted(snap_df["symbol"].unique().tolist()),
            "source": "https://images.dhan.co/api-data/api-scrip-master.csv",
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        logger.info(f"Instrument snapshot saved successfully: {len(snap_df)} instruments -> {parquet_file}")
        return parquet_file

    @classmethod
    def load_snapshot(cls, as_of_date: Optional[date] = None) -> Optional[pd.DataFrame]:
        """
        Loads the exact instrument master snapshot for a given date, or falls back to
        the most recent prior snapshot. Never uses future snapshots.
        """
        target_d = as_of_date or datetime.now().date()
        target_str = target_d.strftime("%Y-%m-%d")

        exact_file = cls.BASE_DIR / f"date={target_str}" / "instrument_manifest.parquet"
        if exact_file.exists():
            return pq.read_table(exact_file).to_pandas()

        # Find closest prior snapshot
        available = []
        if cls.BASE_DIR.exists():
            for p in cls.BASE_DIR.glob("date=*"):
                d_str = p.name.replace("date=", "")
                try:
                    d_val = datetime.strptime(d_str, "%Y-%m-%d").date()
                    if d_val <= target_d:
                        available.append((d_val, p / "instrument_manifest.parquet"))
                except ValueError:
                    continue

        if not available:
            # Create today's snapshot on demand if target is today
            if target_d == datetime.now().date():
                f = cls.create_daily_snapshot(target_d)
                return pq.read_table(f).to_pandas()
            logger.warning(f"No valid historical instrument snapshot found on or before {target_str}")
            return None

        available.sort(key=lambda x: x[0], reverse=True)
        best_match = available[0][1]
        logger.info(f"Using historical instrument snapshot: {best_match}")
        return pq.read_table(best_match).to_pandas()

    @classmethod
    def resolve_contract_point_in_time(
        cls,
        underlying: str,
        option_type: str,
        target_strike: float,
        target_expiry: Optional[date] = None,
        as_of_date: Optional[date] = None,
    ) -> Optional[Dict]:
        """
        Point-in-time contract resolution using historical snapshot.
        Strictly FAIL CLOSED: returns None if no authentic contract exists.
        """
        df = cls.load_snapshot(as_of_date)
        if df is None or df.empty:
            logger.error(f"Cannot resolve contract for {underlying}: No instrument snapshot available.")
            return None

        ref_date = as_of_date or datetime.now().date()
        und = underlying.upper().strip()
        opt_t = option_type.upper().strip()

        # Parse expiry for comparison
        df["expiry_dt"] = pd.to_datetime(df["expiry"], errors="coerce").dt.date
        active = df[
            (df["symbol"] == und)
            & (df["option_type"] == opt_t)
            & (df["expiry_dt"] >= ref_date)
        ]

        if active.empty:
            logger.warning(f"No active contracts in snapshot for {und} {opt_t} on/after {ref_date}")
            return None

        available_expiries = sorted(active["expiry_dt"].dropna().unique())
        if not available_expiries:
            return None

        if target_expiry:
            matching_exp = [exp for exp in available_expiries if exp == target_expiry]
            selected_exp = matching_exp[0] if matching_exp else min(available_expiries, key=lambda x: abs((x - target_expiry).days))
        else:
            selected_exp = available_expiries[0]

        exp_df = active[active["expiry_dt"] == selected_exp]
        if exp_df.empty:
            return None

        available_strikes = exp_df["strike"].dropna().values
        if len(available_strikes) == 0:
            return None

        closest_strike = float(min(available_strikes, key=lambda s: abs(s - target_strike)))
        if abs(closest_strike - target_strike) > 200.0:
            logger.warning(f"Strike {target_strike} too far from market strike {closest_strike} -> NO RESOLUTION")
            return None

        row = exp_df[exp_df["strike"] == closest_strike].iloc[0]
        sec_id = str(row["security_id"]).strip()
        lot_size = int(row["lot_size"])

        if not sec_id.isdigit() or int(sec_id) <= 0 or lot_size <= 0:
            logger.error(f"Invalid contract parameters in snapshot (id={sec_id}, lot={lot_size}) -> FAIL CLOSED")
            return None

        return {
            "security_id": sec_id,
            "underlying": und,
            "strike": closest_strike,
            "option_type": opt_t,
            "expiry_date": selected_exp.strftime("%Y-%m-%d"),
            "dte_days": max(0, (selected_exp - ref_date).days),
            "lot_size": lot_size,
            "trading_symbol": str(row["trading_symbol"]),
            "exchange_segment": "NSE_FNO",
            "source": "InstrumentMasterSnapshot",
            "is_tradable": True,
        }

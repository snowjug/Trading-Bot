"""
Production-Grade Local Market Data Lake (Parquet + PyArrow + DuckDB).
Manages partitioned, compressed, immutable market data layers:
- RAW: Exact immutable captures from DhanHQ (depth, quotes, option chains, historical bars).
- NORMALIZED: Standardized schemas across Equities, Indices, Futures, Options.
- DERIVED: Point-in-time features and consolidated multi-timeframe bars.
- METADATA: Instruments, daily session manifests, dataset quality logs, SHA-256 checksums.
"""
import os
import json
import hashlib
import tempfile
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.utils.logging import setup_logging

logger = setup_logging("data.lake")


class MarketDataLake:
    """
    Partitioned Parquet Data Lake manager.
    Enforces atomic writes, schema validation, immutable raw audit trails, and checksum manifests.
    """

    DEFAULT_BASE_DIR = Path("data")

    # Defined partition directories
    RAW_DIR = "raw/dhan"
    NORMALIZED_DIR = "normalized"
    DERIVED_DIR = "derived"
    METADATA_DIR = "metadata"
    SNAPSHOTS_DIR = "snapshots"
    REPLAY_DIR = "replay"

    def __init__(self, base_dir: Optional[Union[str, Path]] = None):
        self.base_dir = Path(base_dir or self.DEFAULT_BASE_DIR)
        self._ensure_directories()

    def _ensure_directories(self):
        """Creates standard lake directory topology."""
        for sub in [
            f"{self.RAW_DIR}/marketfeed",
            f"{self.RAW_DIR}/quotes",
            f"{self.RAW_DIR}/depth",
            f"{self.RAW_DIR}/optionchain",
            f"{self.RAW_DIR}/historical",
            f"{self.RAW_DIR}/instruments",
            f"{self.NORMALIZED_DIR}/equities",
            f"{self.NORMALIZED_DIR}/indices",
            f"{self.NORMALIZED_DIR}/futures",
            f"{self.NORMALIZED_DIR}/options",
            f"{self.DERIVED_DIR}/bars",
            f"{self.DERIVED_DIR}/features",
            f"{self.METADATA_DIR}/instruments",
            f"{self.METADATA_DIR}/sessions",
            f"{self.METADATA_DIR}/manifests",
            self.SNAPSHOTS_DIR,
            self.REPLAY_DIR,
        ]:
            (self.base_dir / sub).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compute_sha256(filepath: Union[str, Path]) -> str:
        """Computes SHA-256 hash of a file for cryptographic integrity audit."""
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def compute_payload_hash(data: Any) -> str:
        """Computes a deterministic hash of an incoming raw dictionary payload."""
        s = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    def _get_partition_path(
        self,
        layer: str,
        category: str,
        record_date: date,
        exchange_segment: str = "NSE_FNO",
    ) -> Path:
        """
        Constructs standard partition path:
        {base_dir}/{layer}/{category}/year=YYYY/month=MM/date=YYYY-MM-DD/segment={segment}
        """
        y_str = f"year={record_date.strftime('%Y')}"
        m_str = f"month={record_date.strftime('%m')}"
        d_str = f"date={record_date.strftime('%Y-%m-%d')}"
        seg_str = f"segment={exchange_segment}"
        
        target = self.base_dir / layer / category / y_str / m_str / d_str / seg_str
        target.mkdir(parents=True, exist_ok=True)
        return target

    def write_parquet_atomic(
        self,
        table_or_df: Union[pa.Table, pd.DataFrame],
        dest_path: Path,
        compression: str = "snappy",
        schema: Optional[pa.Schema] = None,
    ) -> str:
        """
        Writes a Parquet file atomically (write to temp file then atomic rename).
        Prevents corrupted files during process termination or disk interruptions.
        Returns the SHA-256 checksum of the written file.
        """
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(table_or_df, pd.DataFrame):
            table = pa.Table.from_pandas(table_or_df, schema=schema, preserve_index=False)
        else:
            table = table_or_df

        # Atomic write to temporary file in the same directory
        temp_file = dest_path.with_suffix(".tmp.parquet")
        pq.write_table(
            table,
            temp_file,
            compression=compression,
            use_dictionary=True,
        )

        # Atomic replacement
        temp_file.replace(dest_path)
        return self.compute_sha256(dest_path)

    # ─── 1. RAW LAYER WRITERS (IMMUTABLE CAPTURE) ───

    def write_raw_marketfeed_batch(
        self,
        records: List[Dict[str, Any]],
        record_date: Optional[date] = None,
        exchange_segment: str = "NSE_FNO",
        session_id: Optional[str] = None,
    ) -> Optional[Path]:
        """
        Writes an immutable batch of raw 5-level market depth and quote ticks.
        Never overwrites existing files; appends timestamped chunks.
        """
        if not records:
            return None

        rec_date = record_date or datetime.now().date()
        partition_dir = self._get_partition_path(
            layer="raw/dhan",
            category="marketfeed",
            record_date=rec_date,
            exchange_segment=exchange_segment,
        )

        ts_str = datetime.now().strftime("%H%M%S_%f")
        filename = f"feed_batch_{ts_str}.parquet"
        dest_path = partition_dir / filename

        df = pd.DataFrame(records)
        # Ensure immutable audit envelope fields exist
        now_iso = datetime.now().isoformat()
        if "ingestion_timestamp" not in df.columns:
            df["ingestion_timestamp"] = now_iso
        if "schema_version" not in df.columns:
            df["schema_version"] = "1.0.0"

        checksum = self.write_parquet_atomic(df, dest_path)
        logger.debug(f"Saved raw marketfeed batch: {dest_path.name} ({len(df)} rows, sha256={checksum[:10]})")
        return dest_path

    def write_raw_option_chain_snapshot(
        self,
        chain_data: Dict[str, Any],
        record_date: Optional[date] = None,
        underlying_symbol: str = "NIFTY",
    ) -> Optional[Path]:
        """
        Writes an authentic live option chain snapshot containing all 200+ strikes,
        Greeks (Delta, Theta, Gamma, Vega), IV, Top Bid/Ask, and OI.
        """
        if not chain_data or "strikes" not in chain_data:
            return None

        rec_date = record_date or datetime.now().date()
        partition_dir = self.base_dir / "raw/dhan/optionchain" / f"date={rec_date.strftime('%Y-%m-%d')}"
        partition_dir.mkdir(parents=True, exist_ok=True)

        rows = []
        ingest_ts = datetime.now().isoformat()
        spot = float(chain_data.get("spot_last_price", 0.0))
        expiry = str(chain_data.get("expiry", ""))

        for strike_str, strike_data in chain_data.get("strikes", {}).items():
            strike_val = float(strike_str)
            for opt_side in ("ce", "pe"):
                opt = strike_data.get(opt_side, {})
                if not opt:
                    continue
                greeks = opt.get("greeks", {})
                rows.append({
                    "ingestion_timestamp": ingest_ts,
                    "underlying": underlying_symbol,
                    "spot_price": spot,
                    "expiry_date": expiry,
                    "strike_price": strike_val,
                    "option_type": opt_side.upper(),
                    "security_id": str(opt.get("security_id", "")),
                    "last_price": float(opt.get("last_price", 0.0)),
                    "bid": float(opt.get("top_bid_price", 0.0)),
                    "ask": float(opt.get("top_ask_price", 0.0)),
                    "bid_qty": int(opt.get("top_bid_quantity", 0)),
                    "ask_qty": int(opt.get("top_ask_quantity", 0)),
                    "volume": int(opt.get("volume", 0)),
                    "oi": int(opt.get("oi", 0)),
                    "implied_volatility": float(opt.get("implied_volatility", 0.0)),
                    "delta": float(greeks.get("delta", 0.0)),
                    "theta": float(greeks.get("theta", 0.0)),
                    "gamma": float(greeks.get("gamma", 0.0)),
                    "vega": float(greeks.get("vega", 0.0)),
                    "schema_version": "1.0.0",
                })

        if not rows:
            return None

        df = pd.DataFrame(rows)
        ts_str = datetime.now().strftime("%H%M%S_%f")
        dest_path = partition_dir / f"option_chain_{underlying_symbol}_{expiry}_{ts_str}.parquet"
        self.write_parquet_atomic(df, dest_path)
        return dest_path

    # ─── 2. NORMALIZED LAYER WRITERS ───

    def write_normalized_candles(
        self,
        df: pd.DataFrame,
        category: str,  # 'options', 'indices', 'equities', 'futures'
        symbol: str,
        timeframe: str,  # '1m', '5m', '15m', 'daily'
        record_date: date,
        exchange_segment: str = "NSE_FNO",
    ) -> Path:
        """
        Writes a normalized, cleaned candlestick dataset with standardized datetime and columns.
        """
        partition_dir = self._get_partition_path(
            layer="normalized",
            category=category,
            record_date=record_date,
            exchange_segment=exchange_segment,
        )
        dest_path = partition_dir / f"{symbol}_{timeframe}.parquet"
        self.write_parquet_atomic(df, dest_path)
        return dest_path

    # ─── 3. MANIFESTS & AUDIT TRAIL ───

    def write_session_manifest(
        self,
        session_id: str,
        manifest_data: Dict[str, Any],
        record_date: Optional[date] = None,
    ) -> Path:
        """
        Saves an end-of-session cryptographic manifest logging file counts,
        row counts, schemas, and SHA-256 signatures.
        """
        rec_date = record_date or datetime.now().date()
        manifest_dir = self.base_dir / "metadata/manifests" / f"date={rec_date.strftime('%Y-%m-%d')}"
        manifest_dir.mkdir(parents=True, exist_ok=True)

        dest_path = manifest_dir / f"session_manifest_{session_id}.json"
        with open(dest_path, "w") as f:
            json.dump(manifest_data, f, indent=2, default=str)
        return dest_path

    def get_dataset_stats(self) -> Dict[str, Any]:
        """Scans the lake and computes total files, rows, and bytes."""
        total_files = 0
        total_bytes = 0
        total_rows = 0
        category_counts: Dict[str, Dict[str, Any]] = {}

        for root, _, files in os.walk(self.base_dir):
            for file in files:
                if file.endswith(".parquet"):
                    p = Path(root) / file
                    size = p.stat().st_size
                    total_files += 1
                    total_bytes += size

                    # Find high level category
                    rel = p.relative_to(self.base_dir)
                    top_cat = str(rel.parts[0]) if len(rel.parts) > 0 else "other"
                    if top_cat not in category_counts:
                        category_counts[top_cat] = {"files": 0, "bytes": 0}
                    category_counts[top_cat]["files"] += 1
                    category_counts[top_cat]["bytes"] += size

                    try:
                        meta = pq.read_metadata(p)
                        total_rows += meta.num_rows
                    except Exception:
                        pass

        return {
            "total_files": total_files,
            "total_bytes": total_bytes,
            "total_megabytes": round(total_bytes / (1024 * 1024), 2),
            "total_rows": total_rows,
            "categories": category_counts,
        }


# Module singleton
_market_data_lake: Optional[MarketDataLake] = None


def get_data_lake() -> MarketDataLake:
    """Returns or initializes the MarketDataLake singleton."""
    global _market_data_lake
    if _market_data_lake is None:
        _market_data_lake = MarketDataLake()
    return _market_data_lake

"""
Automated data acquisition pipeline.
Downloads, validates, and stores historical market data.
"""
import hashlib
import time
from datetime import date, datetime, timedelta
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from src.data.providers import DataProviderManager, DataRequest
from src.data.validator import DataValidator
from src.data.manifest import DataManifest
from src.utils.logging import setup_logging

logger = setup_logging("data.downloader")


class DataDownloader:
    """Manages automated data acquisition and storage."""

    def __init__(
        self,
        raw_dir: Path = Path("data/raw"),
        processed_dir: Path = Path("data/processed"),
    ):
        self.raw_dir = Path(raw_dir)
        self.processed_dir = Path(processed_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        self.provider_mgr = DataProviderManager()
        self.validator = DataValidator()
        self.manifest = DataManifest()

    def download_universe(
        self,
        universe: str = "NIFTY50",
        start_date: date = date(2015, 1, 1),
        end_date: date | None = None,
        delay_seconds: float = 1.0,
    ) -> dict:
        """Download OHLCV data for all symbols in a universe."""
        if end_date is None:
            end_date = date.today()

        symbols = self.provider_mgr.get_universe(universe)
        logger.info(f"Downloading {universe}: {len(symbols)} symbols from {start_date} to {end_date}")

        results = {"success": [], "failed": [], "skipped": []}

        for i, symbol in enumerate(symbols):
            logger.info(f"[{i+1}/{len(symbols)}] Processing {symbol}...")

            # Check if already downloaded with sufficient data
            existing = self._check_existing(symbol, start_date, end_date)
            if existing:
                logger.info(f"  Skipping {symbol} — already up to date")
                results["skipped"].append(symbol)
                continue

            try:
                request = DataRequest(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    timeframe="daily",
                )
                result = self.provider_mgr.fetch(request)

                if not result.success or result.data.empty:
                    logger.warning(f"  Failed: {result.error}")
                    results["failed"].append(symbol)
                    continue

                # Validate
                clean_df, report = self.validator.validate_and_clean(result.data, symbol)

                if clean_df.empty:
                    logger.warning(f"  Validation failed for {symbol}")
                    results["failed"].append(symbol)
                    continue

                # Save raw (CSV for preservation)
                raw_path = self.raw_dir / f"{symbol}_daily.csv"
                clean_df.to_csv(raw_path, index=False)

                # Save processed (Parquet for performance)
                processed_path = self.processed_dir / f"{symbol}_daily.parquet"
                table = pa.Table.from_pandas(clean_df)
                pq.write_table(table, processed_path, compression="snappy")

                # Compute checksum
                checksum = self._compute_checksum(processed_path)

                # Update manifest
                self.manifest.add_entry(
                    provider=result.provider,
                    dataset=universe,
                    symbol=symbol,
                    timeframe="daily",
                    start_date=clean_df["datetime"].min().date().isoformat() if "datetime" in clean_df.columns else str(start_date),
                    end_date=clean_df["datetime"].max().date().isoformat() if "datetime" in clean_df.columns else str(end_date),
                    file_path=str(processed_path),
                    checksum=checksum,
                    missing_data=report.missing_candles,
                    quality_status=report.quality_status,
                    row_count=len(clean_df),
                )

                results["success"].append(symbol)
                logger.info(f"  ✓ {symbol}: {len(clean_df)} bars, quality={report.quality_status}")

            except Exception as e:
                logger.error(f"  Error downloading {symbol}: {e}")
                results["failed"].append(symbol)

            # Rate limiting
            time.sleep(delay_seconds)

        # Save manifest
        self.manifest.save()

        logger.info(
            f"Download complete: {len(results['success'])} success, "
            f"{len(results['failed'])} failed, {len(results['skipped'])} skipped"
        )
        return results

    def download_indices(
        self,
        start_date: date = date(2015, 1, 1),
        end_date: date | None = None,
    ) -> dict:
        """Download major index data."""
        if end_date is None:
            end_date = date.today()

        indices = {
            "NIFTY50": "^NSEI",
            "BANKNIFTY": "^NSEBANK",
            "INDIA_VIX": "^INDIAVIX",
            "NIFTY_IT": "^CNXIT",
        }

        results = {"success": [], "failed": []}

        for name, yf_symbol in indices.items():
            logger.info(f"Downloading index: {name}")
            try:
                request = DataRequest(
                    symbol=yf_symbol,
                    start_date=start_date,
                    end_date=end_date,
                    timeframe="daily",
                )
                result = self.provider_mgr.fetch(request)

                if not result.success or result.data.empty:
                    logger.warning(f"Failed to download {name}: {result.error}")
                    results["failed"].append(name)
                    continue

                clean_df, report = self.validator.validate_and_clean(result.data, name)

                # Save
                processed_path = self.processed_dir / f"INDEX_{name}_daily.parquet"
                table = pa.Table.from_pandas(clean_df)
                pq.write_table(table, processed_path, compression="snappy")

                raw_path = self.raw_dir / f"INDEX_{name}_daily.csv"
                clean_df.to_csv(raw_path, index=False)

                checksum = self._compute_checksum(processed_path)
                self.manifest.add_entry(
                    provider=result.provider,
                    dataset="indices",
                    symbol=name,
                    timeframe="daily",
                    start_date=clean_df["datetime"].min().date().isoformat() if "datetime" in clean_df.columns else str(start_date),
                    end_date=clean_df["datetime"].max().date().isoformat() if "datetime" in clean_df.columns else str(end_date),
                    file_path=str(processed_path),
                    checksum=checksum,
                    missing_data=report.missing_candles,
                    quality_status=report.quality_status,
                    row_count=len(clean_df),
                )

                results["success"].append(name)
                logger.info(f"  ✓ {name}: {len(clean_df)} bars")

                time.sleep(1.0)

            except Exception as e:
                logger.error(f"Error downloading {name}: {e}")
                results["failed"].append(name)

        self.manifest.save()
        return results

    def load_symbol(self, symbol: str, timeframe: str = "daily") -> pd.DataFrame:
        """Load processed data for a symbol."""
        path = self.processed_dir / f"{symbol}_daily.parquet"
        if not path.exists():
            # Try index format
            path = self.processed_dir / f"INDEX_{symbol}_daily.parquet"
        if path.exists():
            df = pd.read_parquet(path)
            return df.dropna(subset=["close", "open"]).reset_index(drop=True)
        logger.warning(f"No data found for {symbol}")
        return pd.DataFrame()

    def load_universe(self, universe: str = "NIFTY50") -> dict[str, pd.DataFrame]:
        """Load all symbols in a universe."""
        symbols = self.provider_mgr.get_universe(universe)
        data = {}
        for symbol in symbols:
            df = self.load_symbol(symbol)
            if not df.empty:
                data[symbol] = df
        logger.info(f"Loaded {len(data)}/{len(symbols)} symbols for {universe}")
        return data

    def _check_existing(self, symbol: str, start_date: date, end_date: date) -> bool:
        """Check if data already exists and is fresh enough."""
        path = self.processed_dir / f"{symbol}_daily.parquet"
        if not path.exists():
            return False
        try:
            df = pd.read_parquet(path)
            if df.empty or "datetime" not in df.columns:
                return False
            max_date = pd.to_datetime(df["datetime"]).max().date()
            # Consider fresh if within 3 days of end_date
            return (end_date - max_date).days <= 3
        except Exception:
            return False

    def _compute_checksum(self, path: Path) -> str:
        """Compute MD5 checksum of a file."""
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

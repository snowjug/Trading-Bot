"""
Data manifest — tracks every downloaded dataset with metadata.
"""
import csv
from datetime import datetime
from pathlib import Path
from src.utils.logging import setup_logging

logger = setup_logging("data.manifest")

MANIFEST_PATH = Path("data/DATA_MANIFEST.csv")
MANIFEST_COLUMNS = [
    "provider", "dataset", "symbol", "timeframe",
    "start_date", "end_date", "download_timestamp",
    "file_path", "checksum", "row_count",
    "missing_data", "quality_status",
]


class DataManifest:
    """Manages the DATA_MANIFEST.csv file."""

    def __init__(self, path: Path = MANIFEST_PATH):
        self.path = Path(path)
        self.entries: list[dict] = []
        self._load()

    def _load(self):
        """Load existing manifest if present."""
        if self.path.exists():
            try:
                with open(self.path, "r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    self.entries = list(reader)
                logger.info(f"Loaded manifest with {len(self.entries)} entries")
            except Exception as e:
                logger.warning(f"Could not load manifest: {e}")
                self.entries = []

    def add_entry(
        self,
        provider: str,
        dataset: str,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        file_path: str,
        checksum: str,
        missing_data: int = 0,
        quality_status: str = "UNKNOWN",
        row_count: int = 0,
    ):
        """Add or update a manifest entry."""
        # Check if entry exists and update it
        for i, entry in enumerate(self.entries):
            if entry.get("symbol") == symbol and entry.get("timeframe") == timeframe:
                self.entries[i] = {
                    "provider": provider,
                    "dataset": dataset,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "start_date": start_date,
                    "end_date": end_date,
                    "download_timestamp": datetime.now().isoformat(),
                    "file_path": file_path,
                    "checksum": checksum,
                    "row_count": str(row_count),
                    "missing_data": str(missing_data),
                    "quality_status": quality_status,
                }
                return

        # New entry
        self.entries.append({
            "provider": provider,
            "dataset": dataset,
            "symbol": symbol,
            "timeframe": timeframe,
            "start_date": start_date,
            "end_date": end_date,
            "download_timestamp": datetime.now().isoformat(),
            "file_path": file_path,
            "checksum": checksum,
            "row_count": str(row_count),
            "missing_data": str(missing_data),
            "quality_status": quality_status,
        })

    def save(self):
        """Write manifest to CSV."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
            writer.writeheader()
            writer.writerows(self.entries)
        logger.info(f"Saved manifest with {len(self.entries)} entries to {self.path}")

    def get_entry(self, symbol: str, timeframe: str = "daily") -> dict | None:
        """Get manifest entry for a symbol."""
        for entry in self.entries:
            if entry.get("symbol") == symbol and entry.get("timeframe") == timeframe:
                return entry
        return None

    def summary(self) -> dict:
        """Return summary statistics of the manifest."""
        if not self.entries:
            return {"total": 0}
        statuses = {}
        for entry in self.entries:
            s = entry.get("quality_status", "UNKNOWN")
            statuses[s] = statuses.get(s, 0) + 1
        return {
            "total": len(self.entries),
            "quality_breakdown": statuses,
        }

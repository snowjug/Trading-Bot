"""
Deterministic Trade Journal and Audit Logger.
Persists complete immutable trade execution records, cash flows, and exit reasons.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import pandas as pd


@dataclass
class JournalRecord:
    trade_id: str
    strategy: str
    underlying: str
    expiry: str
    legs_description: str
    entry_timestamp: str
    entry_prices: str
    quantity: int
    initial_credit_debit: float
    tp_threshold: float
    sl_threshold: float
    exit_timestamp: str
    exit_prices: str
    gross_pnl: float
    fees: float
    net_pnl: float
    exit_reason: str
    capital_before: float = 0.0
    capital_after: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["metadata"] = json.dumps(self.metadata)
        return d


class TradeLogger:
    """
    Logs every executed and skipped trade to an append-only ledger.
    """

    def __init__(self, log_file: Optional[Path] = None):
        self.log_file = Path(log_file) if log_file else None
        self.records: List[JournalRecord] = []
        self.skipped_trades: List[Dict[str, Any]] = []

    def record_trade(self, record: JournalRecord):
        self.records.append(record)

    def record_skipped_trade(
        self,
        strategy: str,
        timestamp: datetime,
        reason: str,
        required_capital: float,
        available_capital: float,
        details: Optional[Dict[str, Any]] = None
    ):
        self.skipped_trades.append({
            "strategy": strategy,
            "timestamp": timestamp.isoformat(),
            "reason": reason,
            "required_capital": round(required_capital, 2),
            "available_capital": round(available_capital, 2),
            "details": details or {}
        })

    def to_dataframe(self) -> pd.DataFrame:
        if not self.records:
            return pd.DataFrame()
        return pd.DataFrame([r.to_dict() for r in self.records])

    def save_to_csv(self, file_path: Path):
        df = self.to_dataframe()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(file_path, index=False)

    def save_skipped_to_csv(self, file_path: Path):
        file_path.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(self.skipped_trades)
        df.to_csv(file_path, index=False)

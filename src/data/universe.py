"""
Historical Universe & Survivorship Bias Management Engine.
Tracks point-in-time index membership for NIFTY 50 and Indian equities from 2015 to 2026.
Prevents survivorship bias in historical cross-sectional and momentum screening.
"""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Set, List
import pandas as pd
from src.utils.logging import setup_logging

logger = setup_logging("data.universe")


@dataclass
class RebalanceEvent:
    date: datetime
    action: str
    added: str
    removed: str
    reason: str


class HistoricalUniverseManager:
    """
    Manages historical index constituents and filters trading universes
    strictly by point-in-time eligibility to eliminate survivorship bias.
    """

    def __init__(self, history_file: str = "data/universe_history/nifty50_membership_history.csv"):
        self.history_file = Path(history_file)
        self.rebalance_events: List[RebalanceEvent] = []
        self._load_events()

    def _load_events(self):
        if not self.history_file.exists():
            logger.warning(f"History file {self.history_file} not found.")
            return

        df = pd.read_csv(self.history_file)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        for _, row in df.iterrows():
            self.rebalance_events.append(RebalanceEvent(
                date=row["date"].to_pydatetime(),
                action=row["action"],
                added=str(row["symbol_added"]).strip(),
                removed=str(row["symbol_removed"]).strip(),
                reason=str(row["reason"]),
            ))

    def get_eligible_universe(
        self,
        target_date: datetime | str,
        current_constituents: Set[str] | None = None,
    ) -> Set[str]:
        """
        Reconstruct the exact constituent universe as it existed on target_date.
        Works backward from current constituents applying historical rebalance deltas.
        """
        if isinstance(target_date, str):
            target_date = pd.to_datetime(target_date).to_pydatetime()

        # If current constituents not provided, load default 2026 set
        if current_constituents is None:
            # Standard 2026 active NIFTY 50 universe
            universe = {
                "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
                "BAJAJ-AUTO", "BAJAJFINSV", "BAJFINANCE", "BHARTIARTL", "BPCL",
                "BRITANNIA", "CIPLA", "COALINDIA", "DIVISLAB", "DRREDDY",
                "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
                "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDUSINDBK",
                "INFY", "ITC", "JSWSTEEL", "KOTAKBANK", "LT", "M&M", "MARUTI",
                "NESTLEIND", "NTPC", "ONGC", "POWERGRID", "RELIANCE", "SBILIFE",
                "SBIN", "SHRIRAMFIN", "SUNPHARMA", "TATACONSUM", "TATASTEEL",
                "TCS", "TECHM", "TITAN", "ULTRACEMCO", "WIPRO", "TRENT", "BEL"
            }
        else:
            universe = set(current_constituents)

        # Apply reversions for all rebalance events that occurred strictly AFTER target_date
        # Moving backwards from present to past:
        # If a stock was ADDED after target_date, it was NOT present on target_date (remove it).
        # If a stock was REMOVED after target_date, it WAS present on target_date (add it back).
        for event in sorted(self.rebalance_events, key=lambda e: e.date, reverse=True):
            if event.date > target_date:
                if event.added in universe:
                    universe.remove(event.added)
                universe.add(event.removed)

        return universe

    def is_eligible(self, symbol: str, date: datetime | str) -> bool:
        """Check if a given stock was an eligible constituent on date."""
        eligible = self.get_eligible_universe(date)
        clean_sym = symbol.replace(".NS", "").replace("_daily", "").replace("INDEX_", "")
        return clean_sym in eligible

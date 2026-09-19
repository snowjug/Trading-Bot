"""
Broker-agnostic Execution Interface.
Defines standard primitives for market data query and order execution.
Strictly enforces LIVE_TRADING_ENABLED = False invariant.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, Any, Optional, List
import pandas as pd


@dataclass
class ExecutionOrder:
    order_id: str
    contract_id: str
    symbol: str
    side: str              # BUY / SELL
    quantity: int
    order_type: str        # MARKET / LIMIT
    price: float = 0.0
    status: str = "PENDING"  # PENDING, FILLED, REJECTED, CANCELLED
    fill_price: float = 0.0
    fill_time: Optional[datetime] = None
    slippage: float = 0.0
    fees: float = 0.0
    rejection_reason: str = ""


@dataclass
class OptionQuote:
    contract_id: str
    symbol: str
    bid: float
    ask: float
    ltp: float
    open: float
    high: float
    low: float
    close: float
    volume: int
    oi: int
    timestamp: datetime
    is_stale: bool = False


class BaseExecutor(ABC):
    """
    Standard interface for broker interaction.
    """

    @abstractmethod
    def get_option_chain(self, underlying: str, expiry: date) -> pd.DataFrame:
        """Retrieves point-in-time option chain."""
        pass

    @abstractmethod
    def get_quote(self, contract_id: str) -> Optional[OptionQuote]:
        """Retrieves quote for a specific contract."""
        pass

    @abstractmethod
    def get_position(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves active position details."""
        pass

    @abstractmethod
    def place_order(self, order: ExecutionOrder) -> ExecutionOrder:
        """Submits an order (simulated in paper/backtest)."""
        pass

    @abstractmethod
    def modify_order(self, order_id: str, new_price: float, new_qty: int) -> bool:
        """Modifies a pending order."""
        pass

    @abstractmethod
    def close_position(self, strategy_id: str, reason: str) -> Dict[str, Any]:
        """Closes all legs of an active position."""
        pass

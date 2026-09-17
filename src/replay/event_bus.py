"""
Market Event Bus (Phase 11).
Decouples market data ingestion from strategy logic.
The exact same strategy execution pipeline receives events whether fed by:
1. DhanHQ Live WebSocket / HTTP collector
2. Historical Market Replay Engine
3. Backtest runner
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Any, Optional
import threading

from src.utils.logging import setup_logging

logger = setup_logging("replay.event_bus")


@dataclass
class MarketEvent:
    event_type: str             # 'TICK', 'BAR', 'QUOTE', 'DEPTH', 'OPTION_CHAIN'
    timestamp: str              # Exchange or event ISO timestamp
    security_id: str
    symbol: str
    ltp: float
    bid: float = 0.0
    ask: float = 0.0
    bid_qty: int = 0
    ask_qty: int = 0
    volume: int = 0
    oi: int = 0
    iv: float = 0.0
    delta: float = 0.0
    theta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)


class MarketEventBus:
    """
    Publish-Subscribe Event Bus for market data streaming and deterministic replay.
    """

    def __init__(self):
        self._subscribers: List[Callable[[MarketEvent], None]] = []
        self._lock = threading.Lock()
        self.event_count = 0

    def subscribe(self, callback: Callable[[MarketEvent], None]):
        """Registers a strategy or system component to receive market events."""
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[MarketEvent], None]):
        """Unregisters a subscriber."""
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def publish(self, event: MarketEvent):
        """Dispatches an event to all subscribers sequentially to ensure determinism."""
        self.event_count += 1
        for sub in self._subscribers:
            try:
                sub(event)
            except Exception as e:
                logger.error(f"Error in event bus subscriber {sub}: {e}")

    def reset(self):
        """Resets the event bus state for clean replay sessions."""
        with self._lock:
            self.event_count = 0

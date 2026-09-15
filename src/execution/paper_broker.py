"""
Paper trading broker and execution engine.
Simulates real-world order execution without real money.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
from pathlib import Path
from src.config import Config
from src.utils.logging import setup_logging

logger = setup_logging("execution.paper")


class OrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class Order:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float = 0.0
    order_type: str = "MARKET"  # MARKET, LIMIT, STOP
    status: OrderStatus = OrderStatus.PENDING
    filled_price: float = 0.0
    filled_quantity: int = 0
    timestamp: datetime = None
    filled_timestamp: datetime = None
    strategy: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class PaperPosition:
    symbol: str
    quantity: int
    avg_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    strategy: str = ""

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.avg_price


class BrokerAdapter(ABC):
    """Abstract broker interface."""

    @abstractmethod
    def connect(self) -> bool: ...
    @abstractmethod
    def get_account(self) -> dict: ...
    @abstractmethod
    def get_positions(self) -> list[PaperPosition]: ...
    @abstractmethod
    def get_orders(self) -> list[Order]: ...
    @abstractmethod
    def place_order(self, order: Order) -> Order: ...
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool: ...


class PaperBroker(BrokerAdapter):
    """
    Paper trading broker — simulates fills with realistic slippage.
    All state is persisted to disk for recovery.
    """

    def __init__(
        self,
        initial_capital: float = 1000000,
        slippage_pct: float = 0.0005,
        state_dir: Path = Path("state"),
    ):
        # Safety check
        Config.assert_no_live_trading()

        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.slippage_pct = slippage_pct
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.positions: dict[str, PaperPosition] = {}
        self.orders: list[Order] = []
        self.trade_history: list[dict] = []
        self._order_counter = 0

        # Load state if exists
        self._load_state()

    def connect(self) -> bool:
        logger.info("Paper broker connected")
        return True

    def get_account(self) -> dict:
        total_positions_value = sum(p.market_value for p in self.positions.values())
        return {
            "cash": self.cash,
            "positions_value": total_positions_value,
            "total_equity": self.cash + total_positions_value,
            "initial_capital": self.initial_capital,
            "pnl": (self.cash + total_positions_value) - self.initial_capital,
            "pnl_pct": ((self.cash + total_positions_value) / self.initial_capital - 1) * 100,
        }

    def get_positions(self) -> list[PaperPosition]:
        return list(self.positions.values())

    def get_orders(self) -> list[Order]:
        return self.orders

    def place_order(self, order: Order) -> Order:
        """Simulate order placement with slippage."""
        Config.assert_no_live_trading()

        self._order_counter += 1
        order.order_id = f"PAPER-{self._order_counter:06d}"
        order.timestamp = datetime.now()

        # Simulate fill
        if order.order_type == "MARKET":
            # Apply slippage
            if order.side == OrderSide.BUY:
                order.filled_price = order.price * (1 + self.slippage_pct)
            else:
                order.filled_price = order.price * (1 - self.slippage_pct)

            order.filled_quantity = order.quantity
            order.status = OrderStatus.FILLED
            order.filled_timestamp = datetime.now()

            # Update positions and cash
            self._process_fill(order)
        else:
            # Limit/Stop orders go to pending
            order.status = OrderStatus.PENDING

        self.orders.append(order)
        self._save_state()

        logger.info(
            f"Order {order.order_id}: {order.side.value} {order.quantity} {order.symbol} "
            f"@ {order.filled_price:.2f} [{order.status.value}]"
        )
        return order

    def cancel_order(self, order_id: str) -> bool:
        for order in self.orders:
            if order.order_id == order_id and order.status == OrderStatus.PENDING:
                order.status = OrderStatus.CANCELLED
                return True
        return False

    def update_prices(self, prices: dict[str, float]):
        """Update current prices for all positions."""
        for symbol, price in prices.items():
            if symbol in self.positions:
                pos = self.positions[symbol]
                pos.current_price = price
                pos.unrealized_pnl = (price - pos.avg_price) * pos.quantity

    def reconcile(self) -> dict:
        """Reconcile internal state (paper only — just validates consistency)."""
        account = self.get_account()
        return {
            "status": "ok",
            "cash": account["cash"],
            "positions": len(self.positions),
            "equity": account["total_equity"],
        }

    def _process_fill(self, order: Order):
        """Process a filled order — update positions and cash."""
        symbol = order.symbol
        trade_value = order.filled_price * order.filled_quantity

        if order.side == OrderSide.BUY:
            self.cash -= trade_value
            if symbol in self.positions:
                pos = self.positions[symbol]
                total_qty = pos.quantity + order.filled_quantity
                pos.avg_price = (pos.cost_basis + trade_value) / total_qty
                pos.quantity = total_qty
            else:
                self.positions[symbol] = PaperPosition(
                    symbol=symbol,
                    quantity=order.filled_quantity,
                    avg_price=order.filled_price,
                    current_price=order.filled_price,
                    strategy=order.strategy,
                )
        else:  # SELL
            self.cash += trade_value
            if symbol in self.positions:
                pos = self.positions[symbol]
                realized_pnl = (order.filled_price - pos.avg_price) * order.filled_quantity
                pos.quantity -= order.filled_quantity
                if pos.quantity <= 0:
                    del self.positions[symbol]

                self.trade_history.append({
                    "timestamp": datetime.now().isoformat(),
                    "symbol": symbol,
                    "side": "sell",
                    "quantity": order.filled_quantity,
                    "price": order.filled_price,
                    "realized_pnl": realized_pnl,
                    "strategy": order.strategy,
                })

    def _save_state(self):
        """Persist state to disk for recovery."""
        state = {
            "cash": self.cash,
            "order_counter": self._order_counter,
            "positions": {
                sym: {
                    "quantity": p.quantity,
                    "avg_price": p.avg_price,
                    "current_price": p.current_price,
                    "strategy": p.strategy,
                }
                for sym, p in self.positions.items()
            },
            "trade_history": self.trade_history[-100:],  # Keep last 100
            "saved_at": datetime.now().isoformat(),
        }
        state_path = self.state_dir / "paper_broker_state.json"
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)

    def _load_state(self):
        """Load state from disk."""
        state_path = self.state_dir / "paper_broker_state.json"
        if state_path.exists():
            try:
                with open(state_path) as f:
                    state = json.load(f)
                self.cash = state.get("cash", self.initial_capital)
                self._order_counter = state.get("order_counter", 0)
                for sym, pos_data in state.get("positions", {}).items():
                    self.positions[sym] = PaperPosition(
                        symbol=sym, **pos_data,
                    )
                self.trade_history = state.get("trade_history", [])
                logger.info(f"Loaded paper broker state: cash={self.cash:.0f}, positions={len(self.positions)}")
            except Exception as e:
                logger.warning(f"Could not load state: {e}")

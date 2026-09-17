"""
Realistic Execution Engine (Phase 12).
Simulates authentic order fills using real market microstructure.
Strictly eliminates LTP execution:
- LONG entry: BUY at executable Ask + slippage.
- LONG exit: SELL at executable Bid - slippage.
- SHORT entry: SELL at executable Bid - slippage.
- SHORT exit: BUY at executable Ask + slippage.

If Bid/Ask is unavailable:
Status = NO_EXECUTION (Zero fallback to LTP).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any

from src.utils.logging import setup_logging

logger = setup_logging("execution.realistic")


class ExecutionError(Exception):
    """Raised when an order fails execution checks."""
    pass


@dataclass
class ExecutionFill:
    status: str              # 'FILLED', 'NO_EXECUTION', 'REJECTED'
    fill_price: float
    bid: float
    ask: float
    ltp: float
    spread: float
    slippage: float
    quantity: int
    lot_size: int
    security_id: str
    symbol: str
    action: str              # 'BUY', 'SELL'
    position_side: str       # 'LONG', 'SHORT'
    order_type: str          # 'ENTRY', 'EXIT'
    timestamp: str
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "fill_price": round(self.fill_price, 2),
            "bid": round(self.bid, 2),
            "ask": round(self.ask, 2),
            "ltp": round(self.ltp, 2),
            "spread": round(self.spread, 2),
            "slippage": round(self.slippage, 2),
            "quantity": self.quantity,
            "lot_size": self.lot_size,
            "security_id": self.security_id,
            "symbol": self.symbol,
            "action": self.action,
            "position_side": self.position_side,
            "order_type": self.order_type,
            "timestamp": self.timestamp,
            "reason": self.reason,
        }


class RealisticExecutionSimulator:
    """
    Evaluates realistic order fills against real Dhan Bid/Ask market depth.
    """

    @classmethod
    def execute_order(
        cls,
        action: str,               # 'BUY' or 'SELL'
        order_type: str,           # 'ENTRY' or 'EXIT'
        position_side: str,        # 'LONG' or 'SHORT'
        quantity: int,
        lot_size: int,
        bid: float,
        ask: float,
        ltp: float,
        security_id: str,
        symbol: str,
        slippage_points: float = 0.10,
        max_spread_pct: float = 0.50,
    ) -> ExecutionFill:
        now_ts = datetime.now().isoformat()
        act = action.upper().strip()
        side = position_side.upper().strip()
        otype = order_type.upper().strip()

        # Check 1: Quantity and lot size validation
        if quantity <= 0 or lot_size <= 0:
            return ExecutionFill(
                status="NO_EXECUTION", fill_price=0.0, bid=bid, ask=ask, ltp=ltp,
                spread=0.0, slippage=0.0, quantity=quantity, lot_size=lot_size,
                security_id=security_id, symbol=symbol, action=act,
                position_side=side, order_type=otype, timestamp=now_ts,
                reason="INVALID_QUANTITY_OR_LOT_SIZE"
            )

        # Check 2: Microstructure Bid/Ask availability (Fail Closed)
        if bid <= 0.0 or ask <= 0.0:
            logger.warning(f"Order rejected for {symbol}: Executable quotes unavailable (bid={bid}, ask={ask}) -> NO_EXECUTION")
            return ExecutionFill(
                status="NO_EXECUTION", fill_price=0.0, bid=bid, ask=ask, ltp=ltp,
                spread=0.0, slippage=0.0, quantity=quantity, lot_size=lot_size,
                security_id=security_id, symbol=symbol, action=act,
                position_side=side, order_type=otype, timestamp=now_ts,
                reason="BID_OR_ASK_UNAVAILABLE"
            )

        # Check 3: Spread sanity
        spread = ask - bid
        if spread < 0.0:
            logger.warning(f"Inverted book for {symbol}: bid ({bid}) > ask ({ask}) -> NO_EXECUTION")
            return ExecutionFill(
                status="NO_EXECUTION", fill_price=0.0, bid=bid, ask=ask, ltp=ltp,
                spread=spread, slippage=0.0, quantity=quantity, lot_size=lot_size,
                security_id=security_id, symbol=symbol, action=act,
                position_side=side, order_type=otype, timestamp=now_ts,
                reason="INVERTED_MARKET_SPREAD"
            )

        ref_price = ltp if ltp > 0 else ((ask + bid) / 2.0)
        if ref_price > 0 and (spread / ref_price) > max_spread_pct:
            logger.warning(f"Excessive spread for {symbol}: spread={spread:.2f} > {max_spread_pct*100}% -> NO_EXECUTION")
            return ExecutionFill(
                status="NO_EXECUTION", fill_price=0.0, bid=bid, ask=ask, ltp=ltp,
                spread=spread, slippage=0.0, quantity=quantity, lot_size=lot_size,
                security_id=security_id, symbol=symbol, action=act,
                position_side=side, order_type=otype, timestamp=now_ts,
                reason="EXCESSIVE_SPREAD_WIDTH"
            )

        # Execution pricing logic:
        # BUY (Long entry or Short exit) fills at executable Ask + slippage
        # SELL (Long exit or Short entry) fills at executable Bid - slippage
        if act == "BUY":
            fill = ask + slippage_points
        elif act == "SELL":
            fill = max(0.05, bid - slippage_points)
        else:
            return ExecutionFill(
                status="NO_EXECUTION", fill_price=0.0, bid=bid, ask=ask, ltp=ltp,
                spread=spread, slippage=0.0, quantity=quantity, lot_size=lot_size,
                security_id=security_id, symbol=symbol, action=act,
                position_side=side, order_type=otype, timestamp=now_ts,
                reason="INVALID_ORDER_ACTION"
            )

        return ExecutionFill(
            status="FILLED",
            fill_price=fill,
            bid=bid,
            ask=ask,
            ltp=ltp,
            spread=spread,
            slippage=slippage_points,
            quantity=quantity,
            lot_size=lot_size,
            security_id=security_id,
            symbol=symbol,
            action=act,
            position_side=side,
            order_type=otype,
            timestamp=now_ts,
            reason="AUTHENTIC_MICROSTRUCTURE_FILL"
        )

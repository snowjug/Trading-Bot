"""
Paper Execution Engine with Fail-Closed Safeguards.
Strictly paper/mock: LIVE_TRADING_ENABLED = False is immutable.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, date
import uuid
import pandas as pd
from src.execution.base_executor import BaseExecutor, ExecutionOrder, OptionQuote
from src.utils.logging import setup_logging

logger = setup_logging("execution.paper_executor")


class PaperExecutor(BaseExecutor):
    """
    Simulates order execution against authentic market data.
    Enforces fail-closed rules and hard-blocks live routing.
    """

    LIVE_TRADING_ENABLED: bool = False

    def __init__(self, slippage_points: float = 0.5, spread_penalty: float = 0.5):
        if self.LIVE_TRADING_ENABLED:
            raise RuntimeError("CRITICAL SAFETY BREACH: LIVE_TRADING_ENABLED is True in PaperExecutor!")
        self.slippage_points = slippage_points
        self.spread_penalty = spread_penalty
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.orders: Dict[str, ExecutionOrder] = {}
        self.market_chains: Dict[str, pd.DataFrame] = {}

    def set_current_chain(self, key: str, chain: pd.DataFrame):
        """Injects current market chain for lookup."""
        self.market_chains[key] = chain

    def get_option_chain(self, underlying: str, expiry: date) -> pd.DataFrame:
        key = f"{underlying}_{expiry}"
        return self.market_chains.get(key, pd.DataFrame())

    def get_quote(self, contract_id: str) -> Optional[OptionQuote]:
        for chain in self.market_chains.values():
            match = chain[chain["FinInstrmId"] == contract_id]
            if not match.empty:
                r = match.iloc[0]
                px = float(r.get("OpnPric", r.get("open", r.get("ClsPric", 0.0))))
                spread = max(0.2, px * 0.005)
                return OptionQuote(
                    contract_id=contract_id,
                    symbol=str(r.get("FinInstrmNm", "")),
                    bid=max(0.05, px - spread / 2.0),
                    ask=px + spread / 2.0,
                    ltp=px,
                    open=float(r.get("OpnPric", px)),
                    high=float(r.get("HghPric", px)),
                    low=float(r.get("LwPric", px)),
                    close=float(r.get("ClsPric", px)),
                    volume=int(r.get("TtlTradgVol", 0)),
                    oi=int(r.get("OpnIntrst", 0)),
                    timestamp=datetime.now(),
                    is_stale=False
                )
        return None

    def get_position(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        return self.positions.get(strategy_id)

    def place_order(self, order: ExecutionOrder) -> ExecutionOrder:
        if self.LIVE_TRADING_ENABLED:
            raise RuntimeError("FAIL CLOSED SAFETY VIOLATION: Attempted live order routing!")

        # Fail closed if contract is invalid
        quote = self.get_quote(order.contract_id)
        if quote is None:
            order.status = "REJECTED"
            order.rejection_reason = "QUOTE_UNAVAILABLE_FAIL_CLOSED"
            logger.warning(f"Order {order.order_id} rejected: quote unavailable for {order.contract_id}")
            self.orders[order.order_id] = order
            return order

        # Calculate realistic fill price
        if order.side == "BUY":
            # Buy at Ask + slippage
            fill_px = quote.ask + self.slippage_points
        else:
            # Sell at Bid - slippage
            fill_px = max(0.05, quote.bid - self.slippage_points)

        order.status = "FILLED"
        order.fill_price = round(fill_px, 2)
        order.fill_time = datetime.now()
        order.slippage = self.slippage_points + (self.spread_penalty / 2.0)
        self.orders[order.order_id] = order
        return order

    def modify_order(self, order_id: str, new_price: float, new_qty: int) -> bool:
        if order_id not in self.orders:
            return False
        o = self.orders[order_id]
        if o.status != "PENDING":
            return False
        o.price = new_price
        o.quantity = new_qty
        return True

    def close_position(self, strategy_id: str, reason: str) -> Dict[str, Any]:
        pos = self.positions.pop(strategy_id, None)
        if not pos:
            return {"status": "POSITION_NOT_FOUND"}
        pos["closed_at"] = datetime.now()
        pos["close_reason"] = reason
        pos["status"] = "CLOSED"
        return pos

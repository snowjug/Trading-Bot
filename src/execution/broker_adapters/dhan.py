"""
DhanHQ Broker Adapter for Indian Stock Market.
Connects to DhanHQ v2 API for quotes, portfolio holdings, margins, and paper/live order routing.
Strictly respects Config.LIVE_TRADING_ENABLED safety gate.
"""

from typing import Dict, List, Optional
import requests
import json

from src.config import Config
from src.execution.paper_broker import BrokerAdapter, Order, PaperPosition, OrderSide, OrderStatus
from src.utils.logging import get_logger

logger = get_logger("broker.dhan")


class DhanBrokerAdapter(BrokerAdapter):
    """
    Official DhanHQ API Client Adapter.
    Docs: https://dhanhq.co/docs/v2/
    """

    BASE_URL = "https://api.dhan.co/v2"

    def __init__(
        self,
        client_id: Optional[str] = None,
        access_token: Optional[str] = None,
    ):
        self.client_id = client_id or Config.DHAN_CLIENT_ID
        self.access_token = access_token or Config.DHAN_ACCESS_TOKEN
        self.session = requests.Session()
        self._session = self.session
        self.session.headers.update({
            "client-id": self.client_id,
            "access-token": self.access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self._install_safety_barrier()

    def _install_safety_barrier(self):
        """
        Hard Software Fail-Safe: Intercepts session.post to prevent any live order
        submission to https://api.dhan.co when Config.LIVE_TRADING_ENABLED is False.
        """
        original_post = self.session.post
        def safe_post(url, *args, **kwargs):
            if "api.dhan.co" in url and "/orders" in url and not Config.LIVE_TRADING_ENABLED:
                raise RuntimeError(
                    f"CRITICAL SAFETY LOCK TRIGGERED: Attempted POST to Dhan Production order endpoint {url} "
                    f"while Config.LIVE_TRADING_ENABLED={Config.LIVE_TRADING_ENABLED}! HARD FAIL-SAFE INTERCEPTOR."
                )
            return original_post(url, *args, **kwargs)
        self.session.post = safe_post

    def connect(self) -> bool:
        """Validates API token by querying the user fund limit."""
        if not self.client_id or not self.access_token:
            logger.warning("Dhan credentials missing. Running in simulated paper mode.")
            return False

        try:
            url = f"{self.BASE_URL}/fundlimit"
            resp = self.session.get(url, timeout=5)
            if resp.status_code == 200:
                logger.info(f"Connected to DhanHQ API successfully for client {self.client_id}")
                return True
            else:
                logger.warning(f"Dhan connection response {resp.status_code}: {resp.text[:150]}")
                return False
        except Exception as e:
            logger.warning(f"Failed to connect to DhanHQ API: {e}")
            return False

    def get_account(self) -> Dict:
        """Fetch available funds and margin from Dhan."""
        try:
            resp = self.session.get(f"{self.BASE_URL}/fundlimit", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                avail_cash = float(data.get("availabelBalance", data.get("availableBalance", 0.0)))
                return {
                    "cash": avail_cash,
                    "collateral": float(data.get("collateralAmount", 0.0)),
                    "total_equity": avail_cash,
                    "broker": "DhanHQ",
                    "client_id": self.client_id,
                }
        except Exception as e:
            logger.error(f"Error fetching Dhan account: {e}")

        return {"cash": 0.0, "total_equity": 0.0, "broker": "DhanHQ"}

    def get_positions(self) -> List[PaperPosition]:
        """Fetch open positions from Dhan."""
        positions = []
        try:
            resp = self.session.get(f"{self.BASE_URL}/positions", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                for item in data:
                    qty = int(item.get("netQty", 0))
                    if qty != 0:
                        positions.append(PaperPosition(
                            symbol=item.get("tradingSymbol", "UNKNOWN"),
                            quantity=qty,
                            avg_price=float(item.get("buyAvg", item.get("costPrice", 0.0))),
                            current_price=float(item.get("lastPrice", 0.0)),
                            unrealized_pnl=float(item.get("unrealizedProfit", 0.0)),
                            strategy="dhan_broker",
                        ))
        except Exception as e:
            logger.error(f"Error fetching Dhan positions: {e}")

        return positions

    def get_orders(self) -> List[Order]:
        """Fetch order book from Dhan."""
        orders = []
        try:
            resp = self.session.get(f"{self.BASE_URL}/orders", timeout=5)
            if resp.status_code == 200:
                for item in resp.json():
                    orders.append(Order(
                        order_id=str(item.get("orderId", "")),
                        symbol=item.get("tradingSymbol", ""),
                        side=OrderSide.BUY if item.get("transactionType") == "BUY" else OrderSide.SELL,
                        quantity=int(item.get("quantity", 0)),
                        price=float(item.get("price", 0.0)),
                        status=OrderStatus.FILLED if item.get("orderStatus") == "TRADED" else OrderStatus.PENDING,
                        filled_price=float(item.get("tradedPrice", 0.0)),
                        filled_quantity=int(item.get("tradedQuantity", 0)),
                    ))
        except Exception as e:
            logger.error(f"Error fetching Dhan orders: {e}")

        return orders

    def place_order(self, order: Order) -> Order:
        """
        Places order with strict safety barrier.
        LIVE trading is disabled by default and rejected if attempted.
        """
        Config.assert_no_live_trading()

        logger.info(f"SIMULATED DHAN ORDER: {order.side.value.upper()} {order.quantity} {order.symbol} @ {order.price} (Live disabled)")
        order.status = OrderStatus.FILLED
        order.filled_price = order.price
        order.filled_quantity = order.quantity
        return order

    def cancel_order(self, order_id: str) -> bool:
        try:
            resp = self.session.delete(f"{self.BASE_URL}/orders/{order_id}", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

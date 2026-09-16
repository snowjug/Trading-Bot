"""
Futures Margin and Execution Engine for Indian Index Derivatives (NIFTY & BANK NIFTY).
Models margin requirements, leverage, mark-to-market, and statutory friction.
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
from src.backtesting.cost_model import IndianCostModel, OrderType


@dataclass
class FuturesTradeResult:
    symbol: str
    direction: int  # 1 for Long, -1 for Short
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    quantity: int
    leverage: float
    gross_pnl: float
    net_pnl: float
    return_pct: float
    win: bool


class FuturesMarginEngine:
    """
    Computes Indian F&O margin requirements and models leveraged execution.
    """

    # NSE contract lot sizes
    LOT_SIZES = {
        "NIFTY50": 50,
        "INDEX_NIFTY50": 50,
        "BANKNIFTY": 15,
        "INDEX_BANKNIFTY": 15,
    }

    # Minimum margin fraction (SPAN + Exposure)
    MARGIN_RATES = {
        "NIFTY50": 0.11,        # ~11% margin (~9x max leverage)
        "INDEX_NIFTY50": 0.11,
        "BANKNIFTY": 0.14,      # ~14% margin (~7x max leverage)
        "INDEX_BANKNIFTY": 0.14,
    }

    def __init__(self, cost_model: IndianCostModel | None = None):
        self.cost_model = cost_model or IndianCostModel()

    def get_lot_size(self, symbol: str) -> int:
        return self.LOT_SIZES.get(symbol, 50)

    def get_margin_requirement(self, symbol: str, price: float) -> float:
        """Margin required for 1 contract lot."""
        lot_size = self.get_lot_size(symbol)
        contract_value = price * lot_size
        rate = self.MARGIN_RATES.get(symbol, 0.12)
        return contract_value * rate

    def compute_trade_pnl(
        self,
        symbol: str,
        direction: int,
        entry_price: float,
        exit_price: float,
        quantity: int,
        leverage: float = 3.0,
    ) -> tuple[float, float, float]:
        """
        Compute gross PnL, transaction costs, and net PnL for a futures trade.
        """
        contract_value_entry = entry_price * quantity
        contract_value_exit = exit_price * quantity

        # Gross PnL
        gross_pnl = (exit_price - entry_price) * direction * quantity

        # F&O statutory costs
        buy_val = contract_value_entry if direction == 1 else contract_value_exit
        sell_val = contract_value_exit if direction == 1 else contract_value_entry

        buy_costs = self.cost_model.compute_cost(buy_val, OrderType.FUTURES, is_buy=True).total
        sell_costs = self.cost_model.compute_cost(sell_val, OrderType.FUTURES, is_buy=False).total
        total_costs = buy_costs + sell_costs

        net_pnl = gross_pnl - total_costs
        margin_deployed = (contract_value_entry / leverage) if leverage > 0 else contract_value_entry
        ret_pct = (net_pnl / margin_deployed * 100) if margin_deployed > 0 else 0.0

        return gross_pnl, total_costs, net_pnl

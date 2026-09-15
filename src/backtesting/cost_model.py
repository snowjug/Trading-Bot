"""
Indian market transaction cost model.
Models brokerage, STT, exchange charges, GST, SEBI, stamp duty, slippage.
"""
from dataclasses import dataclass
from enum import Enum
import numpy as np
from src.utils.logging import setup_logging

logger = setup_logging("backtesting.cost_model")


class CostScenario(Enum):
    OPTIMISTIC = "optimistic"
    BASE = "base"
    PESSIMISTIC = "pessimistic"
    STRESS = "stress"


class OrderType(Enum):
    DELIVERY = "delivery"       # Cash & carry (CNC)
    INTRADAY = "intraday"       # MIS
    FUTURES = "futures"
    OPTIONS = "options"


@dataclass
class CostComponents:
    """Breakdown of transaction costs for a single trade."""
    brokerage: float = 0.0
    stt: float = 0.0
    exchange_charges: float = 0.0
    gst: float = 0.0
    sebi_charges: float = 0.0
    stamp_duty: float = 0.0
    slippage: float = 0.0
    spread_cost: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.brokerage + self.stt + self.exchange_charges +
            self.gst + self.sebi_charges + self.stamp_duty +
            self.slippage + self.spread_cost
        )

    def as_pct_of(self, trade_value: float) -> float:
        """Total cost as percentage of trade value."""
        if trade_value == 0:
            return 0.0
        return (self.total / trade_value) * 100

    def to_dict(self) -> dict:
        return {
            "brokerage": self.brokerage,
            "stt": self.stt,
            "exchange_charges": self.exchange_charges,
            "gst": self.gst,
            "sebi_charges": self.sebi_charges,
            "stamp_duty": self.stamp_duty,
            "slippage": self.slippage,
            "spread_cost": self.spread_cost,
            "total": self.total,
        }


class IndianCostModel:
    """
    Realistic transaction cost model for Indian markets (NSE/BSE).
    
    Supports multiple cost scenarios (optimistic → stress) to test
    strategy robustness under different friction assumptions.
    """

    # Cost parameters by scenario
    SCENARIOS = {
        CostScenario.OPTIMISTIC: {
            "brokerage_per_order": 0,        # Discount broker, zero brokerage
            "brokerage_pct": 0.0,
            "stt_delivery_buy": 0.001,       # 0.1% on buy side
            "stt_delivery_sell": 0.001,      # 0.1% on sell side
            "stt_intraday_sell": 0.00025,    # 0.025% sell side only
            "stt_futures_sell": 0.000125,    # 0.0125% sell side
            "exchange_txn_pct": 0.0000345,   # 0.00345%
            "gst_pct": 0.18,                # 18% on brokerage + exchange charges
            "sebi_pct": 0.000001,            # ₹10 per crore
            "stamp_duty_pct": 0.00015,       # 0.015% (buy side only)
            "slippage_pct": 0.0001,          # 0.01%
            "spread_pct": 0.0002,            # 0.02%
        },
        CostScenario.BASE: {
            "brokerage_per_order": 20,       # ₹20 per order (Zerodha-like)
            "brokerage_pct": 0.0003,         # or 0.03%, whichever is lower
            "stt_delivery_buy": 0.001,
            "stt_delivery_sell": 0.001,
            "stt_intraday_sell": 0.00025,
            "stt_futures_sell": 0.000125,
            "exchange_txn_pct": 0.0000345,
            "gst_pct": 0.18,
            "sebi_pct": 0.000001,
            "stamp_duty_pct": 0.00015,
            "slippage_pct": 0.0005,          # 0.05%
            "spread_pct": 0.0005,            # 0.05%
        },
        CostScenario.PESSIMISTIC: {
            "brokerage_per_order": 20,
            "brokerage_pct": 0.0003,
            "stt_delivery_buy": 0.001,
            "stt_delivery_sell": 0.001,
            "stt_intraday_sell": 0.00025,
            "stt_futures_sell": 0.000125,
            "exchange_txn_pct": 0.0000345,
            "gst_pct": 0.18,
            "sebi_pct": 0.000001,
            "stamp_duty_pct": 0.00015,
            "slippage_pct": 0.001,           # 0.10%
            "spread_pct": 0.001,             # 0.10%
        },
        CostScenario.STRESS: {
            "brokerage_per_order": 20,
            "brokerage_pct": 0.0003,
            "stt_delivery_buy": 0.001,
            "stt_delivery_sell": 0.001,
            "stt_intraday_sell": 0.00025,
            "stt_futures_sell": 0.000125,
            "exchange_txn_pct": 0.0000345,
            "gst_pct": 0.18,
            "sebi_pct": 0.000001,
            "stamp_duty_pct": 0.00015,
            "slippage_pct": 0.002,           # 0.20%
            "spread_pct": 0.002,             # 0.20%
        },
    }

    def __init__(self, scenario: CostScenario = CostScenario.BASE):
        self.scenario = scenario
        self.params = self.SCENARIOS[scenario]

    def compute_cost(
        self,
        trade_value: float,
        order_type: OrderType = OrderType.DELIVERY,
        is_buy: bool = True,
        quantity: int = 1,
    ) -> CostComponents:
        """
        Compute full transaction costs for a single trade.
        
        Args:
            trade_value: Total value of the trade (price × quantity)
            order_type: Type of order
            is_buy: True for buy, False for sell
            quantity: Number of shares/lots
        """
        p = self.params
        costs = CostComponents()

        # 1. Brokerage
        brokerage_pct = trade_value * p["brokerage_pct"]
        costs.brokerage = min(p["brokerage_per_order"], brokerage_pct) if p["brokerage_per_order"] > 0 else brokerage_pct

        # 2. STT (Securities Transaction Tax)
        if order_type == OrderType.DELIVERY:
            costs.stt = trade_value * (p["stt_delivery_buy"] if is_buy else p["stt_delivery_sell"])
        elif order_type == OrderType.INTRADAY:
            costs.stt = trade_value * p["stt_intraday_sell"] if not is_buy else 0
        elif order_type == OrderType.FUTURES:
            costs.stt = trade_value * p["stt_futures_sell"] if not is_buy else 0

        # 3. Exchange transaction charges
        costs.exchange_charges = trade_value * p["exchange_txn_pct"]

        # 4. GST (on brokerage + exchange charges)
        costs.gst = (costs.brokerage + costs.exchange_charges) * p["gst_pct"]

        # 5. SEBI charges
        costs.sebi_charges = trade_value * p["sebi_pct"]

        # 6. Stamp duty (buy side only)
        if is_buy:
            costs.stamp_duty = trade_value * p["stamp_duty_pct"]

        # 7. Slippage (estimated)
        costs.slippage = trade_value * p["slippage_pct"]

        # 8. Spread cost (half-spread, as it's one side)
        costs.spread_cost = trade_value * p["spread_pct"] / 2

        return costs

    def round_trip_cost(
        self,
        trade_value: float,
        order_type: OrderType = OrderType.DELIVERY,
    ) -> float:
        """Compute total round-trip cost (buy + sell) as a fraction of trade value."""
        buy_cost = self.compute_cost(trade_value, order_type, is_buy=True)
        sell_cost = self.compute_cost(trade_value, order_type, is_buy=False)
        return (buy_cost.total + sell_cost.total) / trade_value if trade_value > 0 else 0

    def round_trip_cost_pct(
        self,
        order_type: OrderType = OrderType.DELIVERY,
        trade_value: float = 100000,
    ) -> float:
        """Get round-trip cost as percentage for a representative trade."""
        return self.round_trip_cost(trade_value, order_type) * 100

    @classmethod
    def compare_scenarios(cls, trade_value: float = 100000, order_type: OrderType = OrderType.INTRADAY) -> dict:
        """Compare costs across all scenarios."""
        results = {}
        for scenario in CostScenario:
            model = cls(scenario)
            rt_cost = model.round_trip_cost(trade_value, order_type)
            buy_costs = model.compute_cost(trade_value, order_type, is_buy=True)
            sell_costs = model.compute_cost(trade_value, order_type, is_buy=False)
            results[scenario.value] = {
                "round_trip_pct": rt_cost * 100,
                "round_trip_abs": rt_cost * trade_value,
                "buy_breakdown": buy_costs.to_dict(),
                "sell_breakdown": sell_costs.to_dict(),
            }
        return results

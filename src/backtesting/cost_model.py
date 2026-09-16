"""
Comprehensive Indian Market Transaction Cost & Multi-Tier Slippage Engine.
Complies with official SEBI circulars and Union Budget statutory tax revisions.
Features versioned regulatory tax schedules (Pre-Oct 2024 vs Post-Oct 2024),
dynamic turnover calculations, and multi-tier slippage modeling.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Dict
import numpy as np
from src.utils.logging import setup_logging

logger = setup_logging("backtesting.cost_model")


class CostScenario(Enum):
    OPTIMISTIC = "optimistic"
    BASE = "base"
    PESSIMISTIC = "pessimistic"
    STRESS = "stress"


class OrderType(Enum):
    DELIVERY = "delivery"   # Cash & carry (CNC)
    INTRADAY = "intraday"   # Equity MIS
    FUTURES = "futures"     # Index & Stock Futures
    OPTIONS = "options"     # Index & Stock Options


class SlippageModelType(Enum):
    FIXED_BPS = "fixed_bps"
    VOLATILITY_ADJUSTED = "volatility_adjusted"
    SPREAD_BASED = "spread_based"
    STRESS = "stress"


@dataclass
class CostComponents:
    """Itemized breakdown of transaction costs for a single trade leg."""
    brokerage: float = 0.0
    stt: float = 0.0
    exchange_charges: float = 0.0
    gst: float = 0.0
    sebi_charges: float = 0.0
    stamp_duty: float = 0.0
    slippage: float = 0.0
    spread_cost: float = 0.0

    @property
    def total_statutory(self) -> float:
        """Total official taxes, levies, and brokerage."""
        return self.brokerage + self.stt + self.exchange_charges + self.gst + self.sebi_charges + self.stamp_duty

    @property
    def total(self) -> float:
        """Total costs including statutory fees + execution slippage."""
        return self.total_statutory + self.slippage + self.spread_cost

    def to_dict(self) -> dict:
        return {
            "brokerage": round(self.brokerage, 2),
            "stt": round(self.stt, 2),
            "exchange_charges": round(self.exchange_charges, 2),
            "gst": round(self.gst, 2),
            "sebi_charges": round(self.sebi_charges, 2),
            "stamp_duty": round(self.stamp_duty, 2),
            "slippage": round(self.slippage, 2),
            "spread_cost": round(self.spread_cost, 2),
            "total_statutory": round(self.total_statutory, 2),
            "total": round(self.total, 2),
        }


@dataclass
class RegulatorySchedule:
    """Versioned statutory fee parameters defined by Indian regulatory bodies."""
    name: str
    effective_from: datetime
    effective_to: datetime
    stt_delivery_buy: float
    stt_delivery_sell: float
    stt_intraday_sell: float
    stt_futures_sell: float
    stt_options_sell: float  # on premium
    exchange_equity_pct: float
    exchange_futures_pct: float
    exchange_options_pct: float
    sebi_turnover_pct: float  # ₹10 per crore
    stamp_duty_delivery: float
    stamp_duty_futures: float
    stamp_duty_options: float
    gst_rate: float = 0.18
    brokerage_per_order: float = 20.0
    brokerage_rate_cap: float = 0.0003  # 0.03% or ₹20 whichever is lower


class IndianCostModel:
    """
    Versioned Indian Transaction Cost & Slippage Engine.
    Dynamically applies accurate statutory rates based on the trade execution date.
    """

    # 1. Pre-October 1, 2024 Schedule
    SCHEDULE_PRE_OCT_2024 = RegulatorySchedule(
        name="PRE_OCT_2024",
        effective_from=datetime(2015, 1, 1),
        effective_to=datetime(2024, 9, 30, 23, 59, 59),
        stt_delivery_buy=0.001,       # 0.1%
        stt_delivery_sell=0.001,      # 0.1%
        stt_intraday_sell=0.00025,    # 0.025%
        stt_futures_sell=0.000125,    # 0.0125%
        stt_options_sell=0.000625,    # 0.0625% on premium
        exchange_equity_pct=0.0000345,
        exchange_futures_pct=0.000019,
        exchange_options_pct=0.00050,  # 0.05% on premium
        sebi_turnover_pct=0.000001,   # ₹10 per crore
        stamp_duty_delivery=0.00015,  # 0.015% buy
        stamp_duty_futures=0.00002,   # 0.002% buy
        stamp_duty_options=0.00003,   # 0.003% buy
    )

    # 2. Post-October 1, 2024 Schedule (Budget 2024 hikes on F&O)
    SCHEDULE_POST_OCT_2024 = RegulatorySchedule(
        name="POST_OCT_2024",
        effective_from=datetime(2024, 10, 1),
        effective_to=datetime(2099, 12, 31),
        stt_delivery_buy=0.001,
        stt_delivery_sell=0.001,
        stt_intraday_sell=0.00025,
        stt_futures_sell=0.00020,     # HIKED to 0.020%
        stt_options_sell=0.00100,     # HIKED to 0.100% on premium
        exchange_equity_pct=0.0000345,
        exchange_futures_pct=0.000019,
        exchange_options_pct=0.00050,
        sebi_turnover_pct=0.000001,
        stamp_duty_delivery=0.00015,
        stamp_duty_futures=0.00002,
        stamp_duty_options=0.00003,
    )

    def __init__(
        self,
        scenario: CostScenario = CostScenario.BASE,
        slippage_model: SlippageModelType = SlippageModelType.FIXED_BPS,
        slippage_bps: float = 5.0,  # 5 bps = 0.05%
        slippage_multiplier: float = 1.0,
    ):
        self.scenario = scenario
        self.slippage_model = slippage_model
        self.slippage_bps = slippage_bps
        self.slippage_multiplier = slippage_multiplier

        # Multiplier adjustments by scenario
        if scenario == CostScenario.OPTIMISTIC:
            self.slippage_multiplier *= 0.5
        elif scenario == CostScenario.PESSIMISTIC:
            self.slippage_multiplier *= 2.0
        elif scenario == CostScenario.STRESS:
            self.slippage_multiplier *= 5.0

    def get_schedule(self, trade_date: Optional[datetime] = None) -> RegulatorySchedule:
        """Select versioned regulatory tax schedule by trade date."""
        if trade_date is None:
            return self.SCHEDULE_POST_OCT_2024
        if isinstance(trade_date, str):
            trade_date = datetime.fromisoformat(trade_date.replace("Z", ""))

        if trade_date >= self.SCHEDULE_POST_OCT_2024.effective_from:
            return self.SCHEDULE_POST_OCT_2024
        return self.SCHEDULE_PRE_OCT_2024

    def compute_cost(
        self,
        trade_value: float,
        order_type: OrderType = OrderType.OPTIONS,
        is_buy: bool = True,
        trade_date: Optional[datetime] = None,
        price: float = 100.0,
        atr: Optional[float] = None,
    ) -> CostComponents:
        """
        Compute full transaction fees and realistic slippage for a single order leg.
        """
        sched = self.get_schedule(trade_date)
        costs = CostComponents()

        if trade_value <= 0:
            return costs

        # 1. Brokerage (₹20 per executed order or 0.03%, whichever is lower)
        brokerage_pct = trade_value * sched.brokerage_rate_cap
        costs.brokerage = min(sched.brokerage_per_order, brokerage_pct)

        # 2. STT (Securities Transaction Tax)
        if order_type == OrderType.DELIVERY:
            costs.stt = trade_value * (sched.stt_delivery_buy if is_buy else sched.stt_delivery_sell)
        elif order_type == OrderType.INTRADAY:
            costs.stt = trade_value * sched.stt_intraday_sell if not is_buy else 0.0
        elif order_type == OrderType.FUTURES:
            costs.stt = trade_value * sched.stt_futures_sell if not is_buy else 0.0
        elif order_type == OrderType.OPTIONS:
            # Options STT is strictly charged on SELL side (premium value)
            costs.stt = trade_value * sched.stt_options_sell if not is_buy else 0.0

        # 3. Exchange Transaction Charges
        if order_type == OrderType.OPTIONS:
            costs.exchange_charges = trade_value * sched.exchange_options_pct
        elif order_type == OrderType.FUTURES:
            costs.exchange_charges = trade_value * sched.exchange_futures_pct
        else:
            costs.exchange_charges = trade_value * sched.exchange_equity_pct

        # 4. GST (18% on Brokerage + Exchange Transaction Charges)
        costs.gst = (costs.brokerage + costs.exchange_charges) * sched.gst_rate

        # 5. SEBI Turnover Charges (₹10 per crore)
        costs.sebi_charges = trade_value * sched.sebi_turnover_pct

        # 6. Stamp Duty (Buy side only)
        if is_buy:
            if order_type == OrderType.OPTIONS:
                costs.stamp_duty = trade_value * sched.stamp_duty_options
            elif order_type == OrderType.FUTURES:
                costs.stamp_duty = trade_value * sched.stamp_duty_futures
            else:
                costs.stamp_duty = trade_value * sched.stamp_duty_delivery

        # 7. Slippage Calculation
        base_slippage_pct = (self.slippage_bps / 10000.0) * self.slippage_multiplier
        if self.slippage_model == SlippageModelType.VOLATILITY_ADJUSTED and atr and price > 0:
            vol_ratio = (atr / price) / 0.015
            effective_slip = base_slippage_pct * max(0.5, min(4.0, vol_ratio))
        else:
            effective_slip = base_slippage_pct

        costs.slippage = trade_value * effective_slip

        return costs

    def compute_round_trip(
        self,
        entry_price: float,
        exit_price: float,
        qty: int,
        order_type: OrderType = OrderType.OPTIONS,
        trade_date: Optional[datetime] = None,
        atr: Optional[float] = None,
    ) -> CostComponents:
        """
        Compute total costs for a complete round-trip trade (entry buy/sell + exit).
        """
        buy_val = entry_price * qty
        sell_val = exit_price * qty

        entry_costs = self.compute_cost(
            trade_value=buy_val,
            order_type=order_type,
            is_buy=True,
            trade_date=trade_date,
            price=entry_price,
            atr=atr,
        )
        exit_costs = self.compute_cost(
            trade_value=sell_val,
            order_type=order_type,
            is_buy=False,
            trade_date=trade_date,
            price=exit_price,
            atr=atr,
        )

        return CostComponents(
            brokerage=entry_costs.brokerage + exit_costs.brokerage,
            stt=entry_costs.stt + exit_costs.stt,
            exchange_charges=entry_costs.exchange_charges + exit_costs.exchange_charges,
            gst=entry_costs.gst + exit_costs.gst,
            sebi_charges=entry_costs.sebi_charges + exit_costs.sebi_charges,
            stamp_duty=entry_costs.stamp_duty + exit_costs.stamp_duty,
            slippage=entry_costs.slippage + exit_costs.slippage,
            spread_cost=entry_costs.spread_cost + exit_costs.spread_cost,
        )

    def round_trip_cost_pct(
        self,
        order_type: OrderType = OrderType.INTRADAY,
        trade_value: float = 100000.0,
    ) -> float:
        """Backwards compatibility helper for round-trip cost as a percentage."""
        entry_c = self.compute_cost(trade_value, order_type=order_type, is_buy=True)
        exit_c = self.compute_cost(trade_value, order_type=order_type, is_buy=False)
        total = entry_c.total + exit_c.total
        return (total / (trade_value * 2)) * 100.0

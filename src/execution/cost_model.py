"""
Indian Statutory & Transaction Cost Model (Phase 13).
Versioned institutional cost calculation conforming to SEBI and NSE regulations:
- Brokerage (Flat ₹20/order or configured broker tier)
- STT (Securities Transaction Tax: 0.125% on sell turnover for option exercise/sale)
- Exchange Turnover Charges (NSE: 0.050% on premium turnover)
- GST (18% on Brokerage + Exchange charges + SEBI charges)
- SEBI Charges (₹10 per crore of turnover: 0.0001%)
- Stamp Duty (0.003% on buy turnover for options)
- Microstructure Slippage & Spread Costs
"""

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class CostBreakdown:
    brokerage: float
    stt: float
    exchange_charges: float
    gst: float
    sebi_charges: float
    stamp_duty: float
    slippage: float
    spread_cost: float
    total_costs: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "brokerage": round(self.brokerage, 2),
            "stt": round(self.stt, 2),
            "exchange_charges": round(self.exchange_charges, 2),
            "gst": round(self.gst, 2),
            "sebi_charges": round(self.sebi_charges, 2),
            "stamp_duty": round(self.stamp_duty, 2),
            "slippage": round(self.slippage, 2),
            "spread_cost": round(self.spread_cost, 2),
            "total_costs": round(self.total_costs, 2),
        }


class IndianCostModel:
    """
    NSE Index Options Cost Model (Version 2026.1).
    All calculation rules are fully auditable and versioned.
    """
    VERSION = "2026.1"

    # Regulatory Rates for Equity Index Options (NSE)
    BROKERAGE_PER_ORDER = 20.0        # ₹20 flat per executed order
    STT_RATE_SELL = 0.00100           # 0.100% on sell side premium turnover (Budget 2024 Post-Oct 1)
    EXCHANGE_TURNOVER_RATE = 0.00050  # 0.050% on premium turnover
    SEBI_RATE = 0.000001              # ₹10 per crore
    STAMP_DUTY_RATE_BUY = 0.00003     # 0.003% on buy side premium turnover
    GST_RATE = 0.18                   # 18% on (Brokerage + Exchange + SEBI)

    @classmethod
    def calculate_roundtrip_costs(
        cls,
        entry_price: float,
        exit_price: float,
        quantity: int,
        entry_bid: float = 0.0,
        entry_ask: float = 0.0,
        exit_bid: float = 0.0,
        exit_ask: float = 0.0,
        slippage_points: float = 0.10,
    ) -> CostBreakdown:
        """
        Calculates complete roundtrip transaction friction.
        """
        buy_turnover = entry_price * quantity
        sell_turnover = exit_price * quantity
        total_turnover = buy_turnover + sell_turnover

        # 1. Brokerage: Entry + Exit orders
        brokerage = cls.BROKERAGE_PER_ORDER * 2.0

        # 2. STT: Levied on sell turnover
        stt = sell_turnover * cls.STT_RATE_SELL

        # 3. Exchange transaction charges
        exchange_charges = total_turnover * cls.EXCHANGE_TURNOVER_RATE

        # 4. SEBI turnover charges
        sebi_charges = total_turnover * cls.SEBI_RATE

        # 5. Stamp Duty: Levied on buy turnover
        stamp_duty = buy_turnover * cls.STAMP_DUTY_RATE_BUY

        # 6. GST: 18% on (Brokerage + Exchange Charges + SEBI Charges)
        taxable_services = brokerage + exchange_charges + sebi_charges
        gst = taxable_services * cls.GST_RATE

        # 7. Slippage & Microstructure Spread Costs
        slippage = slippage_points * quantity * 2.0
        spread_cost = 0.0
        if entry_ask > entry_bid > 0:
            spread_cost += ((entry_ask - entry_bid) / 2.0) * quantity
        if exit_ask > exit_bid > 0:
            spread_cost += ((exit_ask - exit_bid) / 2.0) * quantity

        total_costs = brokerage + stt + exchange_charges + gst + sebi_charges + stamp_duty + slippage

        return CostBreakdown(
            brokerage=brokerage,
            stt=stt,
            exchange_charges=exchange_charges,
            gst=gst,
            sebi_charges=sebi_charges,
            stamp_duty=stamp_duty,
            slippage=slippage,
            spread_cost=spread_cost,
            total_costs=total_costs,
        )

"""
Indian Statutory & Transaction Cost Engine for Equity Index Options.
SEBI, NSE, STT, GST, Stamp Duty, Brokerage, and Slippage modeling.
"""

from dataclasses import dataclass
from datetime import date
from typing import Dict, Any, List


@dataclass
class CostBreakdown:
    brokerage: float
    stt: float
    exchange_charges: float
    gst: float
    sebi_charges: float
    stamp_duty: float
    slippage: float
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
            "total_costs": round(self.total_costs, 2),
        }


class OptionsCostModel:
    """
    NSE Index Options Cost Model conforming to SEBI regulations.
    """
    BROKERAGE_PER_ORDER = 20.0        # Rs 20 flat per executed order
    STT_RATE_SELL_PRE_OCT2024 = 0.000625
    STT_RATE_SELL_POST_OCT2024 = 0.001000 # Budget 2024 revised rate
    STT_RATE_EXERCISE = 0.001250      # 0.125% on intrinsic value of exercised options
    EXCHANGE_TURNOVER_RATE = 0.00050  # 0.050% on premium turnover
    SEBI_RATE = 0.000001              # Rs 10 per crore (0.0001%)
    STAMP_DUTY_RATE_BUY = 0.00003     # 0.003% on buy side turnover
    GST_RATE = 0.18                   # 18% on (Brokerage + Exchange + SEBI)

    @classmethod
    def calculate_trade_costs(
        cls,
        trade_date: date,
        legs_execution: List[Dict[str, Any]],
        cost_multiplier: float = 1.0,
        slippage_points: float = 0.5,
    ) -> CostBreakdown:
        """
        Calculates all statutory fees and slippage across all legs.
        legs_execution: list of dicts with keys:
          - side: 'BUY' or 'SELL'
          - entry_price: float
          - exit_price: float
          - quantity: int
          - is_exercise: bool (optional)
        """
        num_orders = len(legs_execution) * 2  # entry and exit order per leg
        brokerage = cls.BROKERAGE_PER_ORDER * num_orders

        stt_rate = cls.STT_RATE_SELL_POST_OCT2024 if trade_date >= date(2024, 10, 1) else cls.STT_RATE_SELL_PRE_OCT2024

        stt = 0.0
        stamp_duty = 0.0
        total_turnover = 0.0
        total_slippage = 0.0

        for leg in legs_execution:
            qty = leg["quantity"]
            side = leg["side"]
            entry_px = leg["entry_price"]
            exit_px = leg["exit_price"]
            is_exercise = leg.get("is_exercise", False)

            # Turnover
            entry_turnover = entry_px * qty
            exit_turnover = exit_px * qty
            total_turnover += (entry_turnover + exit_turnover)

            # STT
            if side == "SELL":
                # Sell on entry
                stt += entry_turnover * stt_rate
            else:
                # Sell on exit (if not cash settled at 0)
                if is_exercise and exit_px > 0:
                    stt += exit_turnover * cls.STT_RATE_EXERCISE
                elif exit_px > 0:
                    stt += exit_turnover * stt_rate

            # Stamp duty (on BUY only)
            if side == "BUY":
                stamp_duty += entry_turnover * cls.STAMP_DUTY_RATE_BUY
            else:
                stamp_duty += exit_turnover * cls.STAMP_DUTY_RATE_BUY

            # Slippage: 2 executions (entry + exit)
            total_slippage += (slippage_points * 2.0 * qty)

        exchange_charges = total_turnover * cls.EXCHANGE_TURNOVER_RATE
        sebi_charges = total_turnover * cls.SEBI_RATE
        gst = (brokerage + exchange_charges + sebi_charges) * cls.GST_RATE

        statutory = (brokerage + stt + exchange_charges + gst + sebi_charges + stamp_duty) * cost_multiplier
        total = statutory + total_slippage

        return CostBreakdown(
            brokerage=brokerage * cost_multiplier,
            stt=stt * cost_multiplier,
            exchange_charges=exchange_charges * cost_multiplier,
            gst=gst * cost_multiplier,
            sebi_charges=sebi_charges * cost_multiplier,
            stamp_duty=stamp_duty * cost_multiplier,
            slippage=total_slippage,
            total_costs=total
        )

"""
Deterministic P&L Accounting Engine for Options Structures.
Computes leg-level and position-level gross and net P&L, points, and payoff metrics.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from src.strategies.base_strategy import PositionStructure, OptionLeg, OrderSide, OptionType


@dataclass
class LegPnL:
    contract_id: str
    strike: float
    option_type: str
    side: str
    quantity: int
    entry_price: float
    exit_price: float
    points_pnl: float
    gross_pnl: float


@dataclass
class TradePnL:
    trade_id: str
    strategy_name: str
    underlying: str
    gross_pnl: float
    total_costs: float
    net_pnl: float
    net_points: float
    max_drawdown_points: float = 0.0
    legs: List[LegPnL] = field(default_factory=list)
    is_winner: bool = False


class OptionPnLCalculator:
    """
    Calculates exact realized and unrealized P&L across all option legs.
    """

    @staticmethod
    def calculate_leg_pnl(leg: OptionLeg, exit_price: float) -> LegPnL:
        """
        Long (BUY): (Exit - Entry) * Qty
        Short (SELL): (Entry - Exit) * Qty
        """
        if leg.side == OrderSide.BUY or leg.side == "BUY":
            pts = exit_price - leg.entry_price
        else:
            pts = leg.entry_price - exit_price

        gross = pts * leg.quantity
        return LegPnL(
            contract_id=leg.contract_id,
            strike=leg.strike,
            option_type=leg.option_type.value if hasattr(leg.option_type, "value") else str(leg.option_type),
            side=leg.side.value if hasattr(leg.side, "value") else str(leg.side),
            quantity=leg.quantity,
            entry_price=leg.entry_price,
            exit_price=exit_price,
            points_pnl=pts,
            gross_pnl=gross
        )

    @classmethod
    def calculate_position_realized_pnl(
        cls,
        trade_id: str,
        position: PositionStructure,
        exit_prices: Dict[str, float],
        total_costs: float = 0.0
    ) -> TradePnL:
        """
        Evaluates position gross and net P&L against exit prices.
        """
        leg_pnls = []
        total_gross = 0.0
        total_pts = 0.0

        for leg in position.legs:
            exit_px = exit_prices.get(leg.contract_id, leg.entry_price)
            lp = cls.calculate_leg_pnl(leg, exit_px)
            leg_pnls.append(lp)
            total_gross += lp.gross_pnl
            total_pts += lp.points_pnl

        net = total_gross - total_costs
        return TradePnL(
            trade_id=trade_id,
            strategy_name=position.strategy_name,
            underlying=position.underlying,
            gross_pnl=round(total_gross, 2),
            total_costs=round(total_costs, 2),
            net_pnl=round(net, 2),
            net_points=round(total_pts, 2),
            legs=leg_pnls,
            is_winner=(net > 0)
        )

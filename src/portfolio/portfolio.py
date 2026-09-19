"""
Deterministic Portfolio Management Engine.
Tracks cash, margin allocation, open positions, realized P&L, peak equity, and drawdowns.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from src.strategies.base_strategy import PositionStructure


@dataclass
class PortfolioState:
    initial_capital: float
    current_cash: float
    allocated_margin: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    peak_equity: float = 0.0
    max_drawdown_pct: float = 0.0
    total_trades_count: int = 0
    winning_trades_count: int = 0
    losing_trades_count: int = 0

    @property
    def total_equity(self) -> float:
        return self.current_cash + self.unrealized_pnl

    @property
    def free_margin(self) -> float:
        return max(0.0, self.current_cash - self.allocated_margin)


class Portfolio:
    """
    Tracks portfolio equity and margin invariants.
    """

    def __init__(self, initial_capital: float = 100000.0):
        self.initial_capital = float(initial_capital)
        self.state = PortfolioState(
            initial_capital=self.initial_capital,
            current_cash=self.initial_capital,
            peak_equity=self.initial_capital
        )
        self.open_positions: Dict[str, PositionStructure] = {}
        self.closed_positions: List[Dict[str, Any]] = []

    def can_open(self, position: PositionStructure) -> bool:
        """Verifies free margin is sufficient for position margin requirement."""
        return self.state.free_margin >= position.margin_required

    def open_position(self, pos_id: str, position: PositionStructure) -> bool:
        if not self.can_open(position):
            return False
        self.open_positions[pos_id] = position
        self.state.allocated_margin += position.margin_required
        return True

    def close_position(self, pos_id: str, net_pnl: float, costs: float) -> Optional[PositionStructure]:
        if pos_id not in self.open_positions:
            return None
        pos = self.open_positions.pop(pos_id)
        self.state.allocated_margin = max(0.0, self.state.allocated_margin - pos.margin_required)
        self.state.current_cash += net_pnl
        self.state.realized_pnl += net_pnl
        self.state.total_trades_count += 1
        if net_pnl > 0:
            self.state.winning_trades_count += 1
        elif net_pnl < 0:
            self.state.losing_trades_count += 1

        # Update peak equity and drawdown
        equity = self.state.total_equity
        if equity > self.state.peak_equity:
            self.state.peak_equity = equity
        dd = (self.state.peak_equity - equity) / self.state.peak_equity if self.state.peak_equity > 0 else 0.0
        if dd > self.state.max_drawdown_pct:
            self.state.max_drawdown_pct = dd

        self.closed_positions.append({
            "pos_id": pos_id,
            "strategy": pos.strategy_name,
            "net_pnl": net_pnl,
            "costs": costs,
            "closed_at": datetime.now()
        })
        return pos

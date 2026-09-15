"""
Risk engine — independent risk management layer.
Enforces position sizing, loss limits, drawdown limits, and kill switches.
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from src.config import Config
from src.utils.logging import setup_logging

logger = setup_logging("risk.engine")


@dataclass
class RiskState:
    """Current risk state of the portfolio."""
    equity: float = 0.0
    peak_equity: float = 0.0
    current_drawdown_pct: float = 0.0
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    open_positions: int = 0
    sector_exposure: dict = field(default_factory=dict)
    is_kill_switch_active: bool = False
    kill_switch_reason: str = ""
    last_updated: datetime = None


@dataclass
class RiskDecision:
    """Risk engine's verdict on a proposed trade."""
    approved: bool
    adjusted_quantity: int = 0
    max_position_value: float = 0.0
    suggested_stop_loss: float = 0.0
    rejection_reason: str = ""
    risk_notes: list = field(default_factory=list)


class RiskEngine:
    """
    Independent risk management layer.
    Can override alpha signals. Enforces hard limits on:
    - Per-trade risk
    - Position sizing (ATR-based or fixed fractional)
    - Daily/weekly loss limits
    - Portfolio drawdown limits
    - Sector concentration
    - Kill switch
    """

    def __init__(
        self,
        initial_capital: float = 1000000,
        max_position_pct: float = 0.10,
        max_sector_pct: float = 0.30,
        max_portfolio_drawdown: float = 0.15,
        daily_loss_limit: float = 0.03,
        weekly_loss_limit: float = 0.05,
        max_simultaneous_positions: int = 10,
        risk_per_trade_pct: float = 0.01,
    ):
        self.initial_capital = initial_capital
        self.max_position_pct = max_position_pct
        self.max_sector_pct = max_sector_pct
        self.max_portfolio_drawdown = max_portfolio_drawdown
        self.daily_loss_limit = daily_loss_limit
        self.weekly_loss_limit = weekly_loss_limit
        self.max_simultaneous_positions = max_simultaneous_positions
        self.risk_per_trade_pct = risk_per_trade_pct

        # State tracking
        self.state = RiskState(equity=initial_capital, peak_equity=initial_capital)
        self.daily_trades: list[dict] = []
        self.weekly_trades: list[dict] = []
        self._trade_log: list[dict] = []

    def evaluate_trade(
        self,
        symbol: str,
        direction: int,
        entry_price: float,
        atr: float = 0.0,
        confidence: float = 0.5,
        sector: str = "unknown",
    ) -> RiskDecision:
        """
        Evaluate whether a proposed trade is acceptable.
        Returns approved/rejected decision with adjusted sizing.
        """
        decision = RiskDecision(approved=True)

        # Check kill switch
        if self.state.is_kill_switch_active:
            decision.approved = False
            decision.rejection_reason = f"Kill switch active: {self.state.kill_switch_reason}"
            return decision

        # Check drawdown limit
        if self.state.current_drawdown_pct >= self.max_portfolio_drawdown:
            decision.approved = False
            decision.rejection_reason = f"Portfolio drawdown {self.state.current_drawdown_pct:.1%} exceeds limit {self.max_portfolio_drawdown:.1%}"
            self._activate_kill_switch("Max drawdown exceeded")
            return decision

        # Check daily loss limit
        daily_loss_pct = abs(self.state.daily_pnl) / max(self.state.equity, 1) if self.state.daily_pnl < 0 else 0
        if daily_loss_pct >= self.daily_loss_limit:
            decision.approved = False
            decision.rejection_reason = f"Daily loss limit {self.daily_loss_limit:.1%} reached"
            return decision

        # Check weekly loss limit
        weekly_loss_pct = abs(self.state.weekly_pnl) / max(self.state.equity, 1) if self.state.weekly_pnl < 0 else 0
        if weekly_loss_pct >= self.weekly_loss_limit:
            decision.approved = False
            decision.rejection_reason = f"Weekly loss limit {self.weekly_loss_limit:.1%} reached"
            return decision

        # Check max positions
        if self.state.open_positions >= self.max_simultaneous_positions:
            decision.approved = False
            decision.rejection_reason = f"Max positions ({self.max_simultaneous_positions}) reached"
            return decision

        # Check sector exposure
        sector_exp = self.state.sector_exposure.get(sector, 0) / max(self.state.equity, 1)
        if sector_exp >= self.max_sector_pct:
            decision.approved = False
            decision.rejection_reason = f"Sector {sector} exposure {sector_exp:.1%} exceeds {self.max_sector_pct:.1%}"
            return decision

        # Position sizing
        max_position_value = self.state.equity * self.max_position_pct

        if atr > 0 and entry_price > 0:
            # ATR-based sizing: risk X% of equity per trade
            risk_amount = self.state.equity * self.risk_per_trade_pct
            stop_distance = 2 * atr  # 2 ATR stop
            quantity = int(risk_amount / stop_distance) if stop_distance > 0 else 0
            position_value = quantity * entry_price

            # Cap at max position size
            if position_value > max_position_value:
                quantity = int(max_position_value / entry_price)
                position_value = quantity * entry_price

            decision.suggested_stop_loss = entry_price - (direction * stop_distance)
            decision.risk_notes.append(f"ATR-based sizing: {quantity} shares, risk ₹{risk_amount:.0f}")
        else:
            # Fixed fractional sizing
            quantity = int(max_position_value / entry_price) if entry_price > 0 else 0
            decision.risk_notes.append(f"Fixed fractional sizing: {quantity} shares")

        # Scale by confidence
        if confidence < 0.7:
            quantity = int(quantity * confidence)
            decision.risk_notes.append(f"Scaled by confidence {confidence:.2f}")

        decision.adjusted_quantity = max(0, quantity)
        decision.max_position_value = max_position_value

        if decision.adjusted_quantity == 0:
            decision.approved = False
            decision.rejection_reason = "Position size too small after adjustments"

        return decision

    def update_state(
        self,
        equity: float,
        daily_pnl: float = 0,
        weekly_pnl: float = 0,
        open_positions: int = 0,
        sector_exposure: dict = None,
    ):
        """Update risk state with current portfolio information."""
        self.state.equity = equity
        self.state.peak_equity = max(self.state.peak_equity, equity)
        self.state.current_drawdown_pct = (
            (self.state.peak_equity - equity) / self.state.peak_equity
            if self.state.peak_equity > 0 else 0
        )
        self.state.daily_pnl = daily_pnl
        self.state.weekly_pnl = weekly_pnl
        self.state.open_positions = open_positions
        if sector_exposure:
            self.state.sector_exposure = sector_exposure
        self.state.last_updated = datetime.now()

        # Check if drawdown-triggered kill switch should be deactivated
        if self.state.is_kill_switch_active and self.state.kill_switch_reason == "Max drawdown exceeded":
            if self.state.current_drawdown_pct < self.max_portfolio_drawdown * 0.5:
                self._deactivate_kill_switch()


    def _activate_kill_switch(self, reason: str):
        """Activate kill switch — stop all trading."""
        self.state.is_kill_switch_active = True
        self.state.kill_switch_reason = reason
        logger.critical(f"KILL SWITCH ACTIVATED: {reason}")

    def _deactivate_kill_switch(self):
        """Deactivate kill switch."""
        self.state.is_kill_switch_active = False
        self.state.kill_switch_reason = ""
        logger.info("Kill switch deactivated — risk levels normalized")

    def get_state_summary(self) -> dict:
        """Return current risk state as dict."""
        return {
            "equity": self.state.equity,
            "peak_equity": self.state.peak_equity,
            "drawdown_pct": self.state.current_drawdown_pct * 100,
            "daily_pnl": self.state.daily_pnl,
            "weekly_pnl": self.state.weekly_pnl,
            "open_positions": self.state.open_positions,
            "kill_switch": self.state.is_kill_switch_active,
            "kill_switch_reason": self.state.kill_switch_reason,
        }

    def can_trade(self, current_equity: float) -> bool:
        """Quick boolean check if trading is allowed under risk limits."""
        self.update_state(current_equity)
        if self.state.is_kill_switch_active:
            return False
        if self.state.current_drawdown_pct >= self.max_portfolio_drawdown:
            self._activate_kill_switch("Max drawdown exceeded")
            return False
        return True

    def calculate_position_size(self, capital: float, price: float, atr: float, confidence: float = 0.5) -> int:
        """Computes quantity using ATR and confidence scaling."""
        decision = self.evaluate_trade("GENERIC", direction=1, entry_price=price, atr=atr, confidence=confidence)
        return decision.adjusted_quantity if decision.approved else 0

    def trip_kill_switch(self, reason: str = "Manual kill switch triggered"):
        self._activate_kill_switch(reason)

    def reset_kill_switch(self):
        self._deactivate_kill_switch()


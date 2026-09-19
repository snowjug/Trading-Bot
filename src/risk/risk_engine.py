"""
Risk engine — independent risk management layer.
Enforces position sizing, loss limits, drawdown limits, and kill switches.
"""
import os
import json
import tempfile
from pathlib import Path
from typing import Optional, Union, Dict, List
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, timedelta, time
from typing import Optional, Union, Dict, List, Any
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
        kill_switch_file: Optional[Path] = None,
    ):
        self.initial_capital = initial_capital
        self.max_position_pct = max_position_pct
        self.max_sector_pct = max_sector_pct
        self.max_portfolio_drawdown = max_portfolio_drawdown
        self.daily_loss_limit = daily_loss_limit
        self.weekly_loss_limit = weekly_loss_limit
        self.max_simultaneous_positions = max_simultaneous_positions
        self.risk_per_trade_pct = risk_per_trade_pct
        self.kill_switch_file = Path(kill_switch_file) if kill_switch_file else (Config.STATE_DIR / "kill_switch.json")
        self.kill_switch_file.parent.mkdir(parents=True, exist_ok=True)

        # State tracking
        self.state = RiskState(equity=initial_capital, peak_equity=initial_capital)
        self.daily_trades: list[dict] = []
        self.weekly_trades: list[dict] = []
        self._trade_log: list[dict] = []
        self._load_kill_switch_state()

    def _load_kill_switch_state(self):
        """Restore kill switch state across process restarts (Fail-Closed)."""
        if self.kill_switch_file and self.kill_switch_file.exists():
            try:
                with open(self.kill_switch_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not isinstance(data, dict) or "is_kill_switch_active" not in data:
                        raise ValueError("kill switch state is malformed or missing its flag")
                    if data.get("is_kill_switch_active", False):
                        self.state.is_kill_switch_active = True
                        self.state.kill_switch_reason = data.get("reason", "Persisted kill switch from previous session")
                        logger.critical(
                            f"RESTORED PERSISTED KILL SWITCH: {self.state.kill_switch_reason}. "
                            "Trading halted until explicitly reset."
                        )
            except Exception as e:
                # HIGH #11: an unreadable kill-switch file is an UNKNOWN halt
                # state, not an "inactive" one. Treating corruption as inactive
                # would silently re-enable trading after a halt.
                self.state.is_kill_switch_active = True
                self.state.kill_switch_reason = (
                    f"CORRUPT_KILL_SWITCH_STATE: {self.kill_switch_file} unreadable ({e}). "
                    "Failing closed — trading halted until explicitly reset."
                )
                logger.critical(self.state.kill_switch_reason)

    def _save_kill_switch_state(self, is_active: bool, reason: str):
        """Atomically persist kill switch state to disk."""
        if not self.kill_switch_file:
            return
        data = {
            "is_kill_switch_active": bool(is_active),
            "reason": str(reason),
            "timestamp": datetime.now().isoformat(),
        }
        try:
            parent_dir = self.kill_switch_file.parent
            parent_dir.mkdir(parents=True, exist_ok=True)
            tmp_file = parent_dir / f".tmp_{self.kill_switch_file.name}_{os.getpid()}"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, self.kill_switch_file)
        except Exception as e:
            logger.error(f"Failed to persist kill switch state atomically: {e}")

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
        """Activate kill switch — stop all trading and persist to disk."""
        self.state.is_kill_switch_active = True
        self.state.kill_switch_reason = reason
        self._save_kill_switch_state(True, reason)
        logger.critical(f"KILL SWITCH ACTIVATED: {reason}")

    def _deactivate_kill_switch(self):
        """Deactivate kill switch and clear persisted state."""
        self.state.is_kill_switch_active = False
        self.state.kill_switch_reason = ""
        self._save_kill_switch_state(False, "")
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

    def validate_options_position(
        self,
        position: Any,
        capital: float,
        current_positions: List[Any],
        market_data: Any,
        max_capital_risk_pct: float = 0.15,
        max_positions: int = 2,
    ) -> RiskDecision:
        """
        Deterministic pre-trade risk validation for options structures.
        Enforces fail-closed behavior across margin, capital risk, duplicates, and timing.
        """
        decision = RiskDecision(approved=True)

        # 1. Kill switch check
        if self.state.is_kill_switch_active:
            decision.approved = False
            decision.rejection_reason = f"KILL_SWITCH_ACTIVE: {self.state.kill_switch_reason}"
            return decision

        # 2. Portfolio drawdown check
        if self.state.current_drawdown_pct >= self.max_portfolio_drawdown:
            decision.approved = False
            decision.rejection_reason = f"MAX_PORTFOLIO_DRAWDOWN_EXCEEDED: {self.state.current_drawdown_pct:.1%}"
            return decision

        # 3. Valid position structure check
        if position is None or position.status.startswith("REJECTED"):
            decision.approved = False
            decision.rejection_reason = position.status if position else "INVALID_STRUCTURE"
            return decision

        # 4. Sufficient Margin check (Crucial for Low Capital)
        if capital < position.margin_required:
            decision.approved = False
            decision.rejection_reason = f"INSUFFICIENT_MARGIN: Required Rs {position.margin_required:,.2f} > Available Rs {capital:,.2f}"
            return decision

        # 5. Max Loss Budget check
        total_max_loss = position.max_loss_points * position.lot_size
        if total_max_loss > (capital * max_capital_risk_pct) and total_max_loss > 0:
            decision.approved = False
            decision.rejection_reason = f"MAX_LOSS_EXCEEDS_BUDGET: Loss Rs {total_max_loss:,.2f} > Budget Rs {(capital * max_capital_risk_pct):,.2f}"
            return decision

        # 6. Max Concurrent Positions check
        if len(current_positions) >= max_positions:
            decision.approved = False
            decision.rejection_reason = f"MAX_POSITIONS_REACHED: {len(current_positions)} >= {max_positions}"
            return decision

        # 7. Duplicate Position check
        for existing in current_positions:
            if existing.strategy_name == position.strategy_name and existing.expiry == position.expiry:
                decision.approved = False
                decision.rejection_reason = f"DUPLICATE_POSITION: Strategy {position.strategy_name} already open for expiry {position.expiry}"
                return decision

        # 8. Trading Session bounds check (09:15 to 15:25)
        if market_data and hasattr(market_data, "timestamp") and market_data.timestamp:
            cur_time = market_data.timestamp.time()
            if cur_time < time(9, 15) or cur_time > time(15, 25):
                decision.approved = False
                decision.rejection_reason = f"OUTSIDE_TRADING_SESSION: Current time {cur_time} not in [09:15, 15:25]"
                return decision

            # Expiry safety: Do not open new positions on expiry day after 14:30
            if getattr(market_data, "is_expiry_day", False) and cur_time >= time(14, 30):
                decision.approved = False
                decision.rejection_reason = "EXPIRY_SAFETY_VIOLATION: No new positions allowed after 14:30 on expiry day"
                return decision

        # 9. Leg quote integrity & spread check
        for leg in position.legs:
            if leg.entry_price <= 0:
                decision.approved = False
                decision.rejection_reason = f"INVALID_LEG_PRICE: Leg {leg.contract_name} has invalid price {leg.entry_price}"
                return decision

        return decision



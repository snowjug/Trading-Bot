"""
Base Strategy Interface for Simple Deterministic Options Trading Bot.
Strictly causal, no AI/ML, deterministic inputs and outputs.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, time, datetime
from enum import Enum
from typing import List, Dict, Optional, Any
import pandas as pd


class OptionType(str, Enum):
    CE = "CE"
    PE = "PE"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class ExitReason(str, Enum):
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    TIME_EXIT = "TIME_EXIT"
    EXPIRY = "EXPIRY"
    MANUAL_CLOSE = "MANUAL_CLOSE"
    RISK_BREACH = "RISK_BREACH"
    DATA_FAILURE = "DATA_FAILURE"
    SYSTEM_FAILURE = "SYSTEM_FAILURE"


@dataclass
class OptionLeg:
    contract_id: str
    contract_name: str
    option_type: OptionType
    side: OrderSide
    strike: float
    expiry: date
    quantity: int
    entry_price: float = 0.0
    exit_price: float = 0.0
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    pnl: float = 0.0


@dataclass
class PositionStructure:
    strategy_name: str
    underlying: str
    expiry: date
    legs: List[OptionLeg] = field(default_factory=list)
    entry_time: Optional[datetime] = None
    net_premium_points: float = 0.0     # positive for credit, negative for debit
    max_loss_points: float = 0.0        # maximum theoretical loss in index points
    max_profit_points: float = 0.0      # maximum theoretical gain in index points
    margin_required: float = 0.0        # estimated margin requirement per lot
    lot_size: int = 50
    take_profit_points: float = 0.0     # profit target threshold
    stop_loss_points: float = 0.0       # stop loss threshold (points lost)
    status: str = "OPEN"               # OPEN, CLOSED, REJECTED
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_quantity(self) -> int:
        return self.lot_size

    @property
    def is_credit(self) -> bool:
        return self.net_premium_points > 0


@dataclass
class EntrySignal:
    strategy_name: str
    underlying: str
    timestamp: datetime
    parameters: Dict[str, Any] = field(default_factory=dict)
    reason: str = "RULE_TRIGGERED"


@dataclass
class ExitSignal:
    timestamp: datetime
    reason: ExitReason
    exit_prices: Dict[str, float] = field(default_factory=dict)  # contract_id -> exit_price
    notes: str = ""


@dataclass
class MarketData:
    timestamp: datetime
    spot_price: float
    vix: float = 15.0
    chain: Optional[pd.DataFrame] = None
    historical_bars: Optional[pd.DataFrame] = None
    day_high: float = 0.0
    day_low: float = 0.0
    is_expiry_day: bool = False
    expiry_date: Optional[date] = None


class BaseStrategy(ABC):
    """
    Standard deterministic interface for option strategies.
    All logic is pure and deterministic: same MarketData -> same decision.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.name = config.get("strategy_name", self.__class__.__name__)
        self.underlying = config.get("underlying", "NIFTY")
        self.take_profit_pct = float(config.get("take_profit_pct", 0.30))  # e.g. 30% of credit
        self.stop_loss_pct = float(config.get("stop_loss_pct", 0.50))      # e.g. 50% of credit
        self.vix_filter_max = float(config.get("vix_filter_max", 0.0))    # 0 = no filter
        self.strike_step = float(config.get("strike_step", 50.0))

    @abstractmethod
    def check_entry(self, market_data: MarketData) -> Optional[EntrySignal]:
        """Evaluates whether deterministic entry conditions are met."""
        pass

    @abstractmethod
    def build_position(self, market_data: MarketData, signal: EntrySignal) -> PositionStructure:
        """Constructs the specific option legs (strikes, expiries, quantities)."""
        pass

    def calculate_take_profit(self, position: PositionStructure) -> float:
        """Calculates take profit threshold in index points."""
        if position.is_credit:
            return position.net_premium_points * self.take_profit_pct
        return position.net_premium_points * (1.0 + self.take_profit_pct)

    def calculate_stop_loss(self, position: PositionStructure) -> float:
        """Calculates stop loss threshold in index points lost."""
        if position.is_credit:
            return position.net_premium_points * self.stop_loss_pct
        return position.net_premium_points * self.stop_loss_pct

    def should_force_exit(self, position: PositionStructure, market_data: MarketData) -> bool:
        """Checks if fixed clock exit or expiry time is reached."""
        exit_time_str = self.config.get("exit_time", "15:20")
        target_hour, target_min = map(int, exit_time_str.split(":"))
        if market_data.timestamp.time() >= time(target_hour, target_min):
            return True
        if market_data.is_expiry_day and market_data.timestamp.time() >= time(15, 15):
            return True
        return False

    def should_exit(self, position: PositionStructure, market_data: MarketData) -> Optional[ExitSignal]:
        """
        Evaluates TP, SL, time exit, or expiry conditions deterministically.
        """
        # 1. Force / Time exit check
        if self.should_force_exit(position, market_data):
            reason = ExitReason.EXPIRY if market_data.is_expiry_day else ExitReason.TIME_EXIT
            return ExitSignal(timestamp=market_data.timestamp, reason=reason)

        # 2. Mark-to-market P&L calculation
        if market_data.chain is not None and not market_data.chain.empty:
            current_pnl_points = self._compute_unrealized_points(position, market_data.chain)
            if current_pnl_points >= position.take_profit_points and position.take_profit_points > 0:
                return ExitSignal(timestamp=market_data.timestamp, reason=ExitReason.TAKE_PROFIT)
            if current_pnl_points <= -position.stop_loss_points and position.stop_loss_points > 0:
                return ExitSignal(timestamp=market_data.timestamp, reason=ExitReason.STOP_LOSS)

        return None

    def _compute_unrealized_points(self, position: PositionStructure, chain: pd.DataFrame) -> float:
        """Computes current mark-to-market profit in index points across legs."""
        points = 0.0
        for leg in position.legs:
            match = chain[(chain["StrkPric"] == leg.strike) & (chain["OptnTp"] == leg.option_type.value)]
            if match.empty:
                continue
            curr_px = float(match.iloc[0]["ClsPric"] if "ClsPric" in match.columns else match.iloc[0]["close"])
            if leg.side == OrderSide.SELL:
                points += (leg.entry_price - curr_px)
            else:
                points += (curr_px - leg.entry_price)
        return points

    def round_strike(self, price: float) -> float:
        """Rounds underlying price to the nearest standard strike using half-up convention."""
        import math
        return float(math.floor((price + self.strike_step / 2.0) / self.strike_step) * self.strike_step)

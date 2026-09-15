"""
Paper Trading Execution Engine for Indian Markets.
Orchestrates:
Data Feeds -> Regime Detection -> Strategy Signals -> Risk Engine Sizing -> Paper Broker Execution -> State Tracking
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd

from src.config import Config
from src.execution.paper_broker import PaperBroker, Order, OrderSide, OrderStatus
from src.risk.risk_engine import RiskEngine
from src.regime.detector import RuleBasedRegimeDetector, RegimeState
from src.strategies.base import Strategy
from src.utils.logging import get_logger

logger = get_logger("execution.paper_engine")


@dataclass
class ExecutionLogEntry:
    timestamp: str
    symbol: str
    action: str
    quantity: int
    price: float
    slippage_cost: float
    strategy: str
    regime: str
    portfolio_equity: float


class PaperExecutionEngine:
    """Manages paper trading operations for validated quantitative strategies."""

    def __init__(
        self,
        broker: Optional[PaperBroker] = None,
        risk_engine: Optional[RiskEngine] = None,
        regime_detector: Optional[RuleBasedRegimeDetector] = None,
    ):
        Config.assert_no_live_trading()
        self.broker = broker or PaperBroker(initial_capital=Config.INITIAL_CAPITAL)
        self.risk_engine = risk_engine or RiskEngine()
        self.regime_detector = regime_detector or RuleBasedRegimeDetector()

        self.active_strategies: Dict[str, Strategy] = {}
        self.execution_log: List[ExecutionLogEntry] = []

    def register_strategy(self, symbol: str, strategy: Strategy):
        """Deploy an approved strategy to paper mode for a target symbol."""
        key = f"{strategy.name}_{symbol}"
        self.active_strategies[key] = (symbol, strategy)
        logger.info(f"Deployed strategy to paper engine: {key}")

    def execute_bar(self, symbol: str, strategy: Strategy, current_bar: pd.Series, full_history: pd.DataFrame):
        """Processes one market bar through regime, strategy, risk, and execution."""
        Config.assert_no_live_trading()

        dt = current_bar["datetime"] if "datetime" in current_bar else datetime.now()
        close_price = float(current_bar["close"])

        # 1. Update Broker mark-to-market prices
        if symbol in self.broker.positions:
            self.broker.positions[symbol].current_price = close_price
            pos = self.broker.positions[symbol]
            pos.unrealized_pnl = (close_price - pos.avg_price) * pos.quantity

        # 2. Check Portfolio Risk Limits
        account = self.broker.get_account()
        current_equity = account["total_equity"]

        if not self.risk_engine.can_trade(current_equity):
            logger.warning(f"Risk engine kill switch active or max loss reached. Trading halted.")
            return

        # 3. Detect Market Regime
        regime = None
        if len(full_history) >= 200:
            regime = self.regime_detector.current_regime(full_history)

        regime_str = regime.vol_regime.value if regime else "NORMAL"

        # 4. Generate Signal
        signals_df = strategy.generate_signals(full_history, regime)
        if signals_df.empty or "signal" not in signals_df.columns:
            return

        latest_signal = int(signals_df["signal"].iloc[-1])
        confidence = float(signals_df["confidence"].iloc[-1]) if "confidence" in signals_df.columns else 0.5

        # 5. Position Reconciliation & Sizing
        current_pos = self.broker.positions.get(symbol, None)
        current_qty = current_pos.quantity if current_pos else 0

        atr = float(full_history["atr_14"].iloc[-1]) if "atr_14" in full_history.columns else (close_price * 0.02)

        # 6. Execute transitions
        if latest_signal > 0 and current_qty == 0:
            # Sizing calculation
            target_qty = self.risk_engine.calculate_position_size(
                capital=current_equity,
                price=close_price,
                atr=atr,
                confidence=confidence,
            )

            # Cap max allocation at 15% of equity
            max_qty = int((current_equity * 0.15) / close_price)
            target_qty = min(target_qty, max_qty)

            if target_qty > 0 and (target_qty * close_price <= self.broker.cash):
                order = Order(
                    order_id="",
                    symbol=symbol,
                    side=OrderSide.BUY,
                    quantity=target_qty,
                    price=close_price,
                    order_type="MARKET",
                    strategy=strategy.name,
                )
                filled = self.broker.place_order(order)
                if filled.status == OrderStatus.FILLED:
                    slippage = abs(filled.filled_price - close_price) * filled.filled_quantity
                    self.execution_log.append(ExecutionLogEntry(
                        timestamp=str(dt),
                        symbol=symbol,
                        action="BUY",
                        quantity=filled.filled_quantity,
                        price=filled.filled_price,
                        slippage_cost=round(slippage, 2),
                        strategy=strategy.name,
                        regime=regime_str,
                        portfolio_equity=round(self.broker.get_account()["total_equity"], 2),
                    ))
                    logger.info(f"PAPER BUY: {symbol} x {target_qty} @ Rs.{filled.filled_price:.2f}")

        elif latest_signal <= 0 and current_qty > 0:
            # Exit long position
            order = Order(
                order_id="",
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=current_qty,
                price=close_price,
                order_type="MARKET",
                strategy=strategy.name,
            )
            filled = self.broker.place_order(order)
            if filled.status == OrderStatus.FILLED:
                slippage = abs(filled.filled_price - close_price) * filled.filled_quantity
                self.execution_log.append(ExecutionLogEntry(
                    timestamp=str(dt),
                    symbol=symbol,
                    action="SELL",
                    quantity=filled.filled_quantity,
                    price=filled.filled_price,
                    slippage_cost=round(slippage, 2),
                    strategy=strategy.name,
                    regime=regime_str,
                    portfolio_equity=round(self.broker.get_account()["total_equity"], 2),
                ))
                logger.info(f"PAPER SELL: {symbol} x {current_qty} @ Rs.{filled.filled_price:.2f}")

    def simulate_forward_period(self, data_dict: Dict[str, pd.DataFrame], num_bars: int = 60):
        """Simulates recent forward paper trading across all registered strategies."""
        logger.info(f"Starting paper simulation for past {num_bars} bars...")
        for key, (symbol, strategy) in self.active_strategies.items():
            if symbol not in data_dict:
                continue
            df = data_dict[symbol]
            if len(df) <= num_bars + 200:
                continue

            # Step through the simulated forward window
            start_idx = len(df) - num_bars
            for i in range(start_idx, len(df)):
                history_subset = df.iloc[:i+1]
                current_bar = df.iloc[i]
                self.execute_bar(symbol, strategy, current_bar, history_subset)

        summary = self.get_summary()
        tot_eq = summary['account']['total_equity']
        tot_str = f"Rs.{tot_eq:,.2f}" if not pd.isna(tot_eq) else "N/A"
        logger.info(f"Paper simulation completed: Equity={tot_str}, Total Trades={len(self.execution_log)}")
        return summary


    def get_summary(self) -> Dict:
        acct = self.broker.get_account()
        positions = [asdict(p) for p in self.broker.get_positions()]
        return {
            "account": acct,
            "positions": positions,
            "total_trades": len(self.execution_log),
            "recent_executions": [asdict(e) for e in self.execution_log[-10:]],
            "live_trading_enabled": Config.LIVE_TRADING_ENABLED,
        }

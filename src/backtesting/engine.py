"""
Event-driven backtesting engine.
Processes bars chronologically with realistic execution modeling.
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from src.backtesting.cost_model import IndianCostModel, CostScenario, OrderType, CostComponents
from src.utils.logging import setup_logging

logger = setup_logging("backtesting.engine")


@dataclass
class Trade:
    """Record of a completed trade."""
    trade_id: int
    symbol: str
    direction: int  # 1=long, -1=short
    entry_date: datetime
    exit_date: datetime
    entry_price: float
    exit_price: float
    quantity: int
    gross_pnl: float
    costs: float
    net_pnl: float
    holding_bars: int
    strategy: str = ""
    entry_signal_confidence: float = 0.0
    exit_reason: str = ""

    @property
    def return_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return (self.exit_price / self.entry_price - 1) * self.direction * 100

    @property
    def net_return_pct(self) -> float:
        trade_value = self.entry_price * self.quantity
        return (self.net_pnl / trade_value * 100) if trade_value > 0 else 0.0


@dataclass
class Position:
    """Active position."""
    symbol: str
    direction: int
    entry_date: datetime
    entry_price: float
    quantity: int
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    strategy: str = ""
    signal_confidence: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0


@dataclass
class BacktestResult:
    """Complete backtest result."""
    strategy_name: str
    trades: list[Trade]
    equity_curve: pd.DataFrame
    daily_returns: pd.Series
    total_return_pct: float
    cagr: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    max_drawdown_duration: int
    profit_factor: float
    win_rate: float
    avg_win: float
    avg_loss: float
    expectancy: float
    total_trades: int
    total_costs: float
    cost_scenario: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    calmar_ratio: float = 0.0
    avg_holding_bars: float = 0.0
    metadata: dict = field(default_factory=dict)


class BacktestEngine:
    """
    Event-driven backtesting engine for single-instrument strategies.
    
    Key principles:
    - No look-ahead bias: uses next-bar execution
    - Realistic costs via IndianCostModel
    - Slippage modeling
    - Position tracking
    """

    def __init__(
        self,
        initial_capital: float = 1000000,
        cost_scenario: CostScenario = CostScenario.BASE,
        order_type: OrderType = OrderType.INTRADAY,
        position_size_pct: float = 1.0,  # Fraction of capital per trade
        max_positions: int = 1,
    ):
        self.initial_capital = initial_capital
        self.cost_model = IndianCostModel(cost_scenario)
        self.order_type = order_type
        self.position_size_pct = min(position_size_pct, 1.0)
        self.max_positions = max_positions
        self.cost_scenario_name = cost_scenario.value

    def run(
        self,
        signals_df: pd.DataFrame,
        price_df: pd.DataFrame,
        strategy_name: str = "unknown",
    ) -> BacktestResult:
        """
        Run backtest on signals.
        
        signals_df must have: datetime, signal (-1/0/1), confidence
        price_df must have: datetime, open, high, low, close, volume
        
        Execution model: signal on bar T → execute on open of bar T+1
        """
        # Defensive check: swap if arguments were passed in reverse order
        if "close" in signals_df.columns and "signal" in price_df.columns:
            signals_df, price_df = price_df, signals_df

        # Merge signals with prices
        df = price_df[["datetime", "open", "high", "low", "close", "volume"]].copy()
        df = df.dropna(subset=["close", "open"])
        df = df.merge(
            signals_df[["datetime", "signal", "confidence"]],
            on="datetime", how="left",
        )
        df["signal"] = df["signal"].fillna(0).astype(int)
        df["confidence"] = df["confidence"].fillna(0)
        df = df.sort_values("datetime").reset_index(drop=True)

        # State
        capital = self.initial_capital
        position: Optional[Position] = None
        trades: list[Trade] = []
        equity_history = []
        trade_id = 0

        for i in range(1, len(df)):
            prev = df.iloc[i - 1]
            curr = df.iloc[i]

            # Execution price: open of current bar (signal was on previous bar)
            exec_price = curr["open"]
            signal = int(prev["signal"])
            confidence = float(prev["confidence"])

            # Close existing position if signal reverses or goes flat
            if position is not None:
                should_close = (
                    (signal != position.direction) or
                    (signal == 0) or
                    self._check_stop_loss(position, curr) or
                    self._check_take_profit(position, curr)
                )

                if should_close:
                    exit_reason = "signal_change"
                    if self._check_stop_loss(position, curr):
                        exec_price_exit = position.stop_loss if position.stop_loss > 0 else exec_price
                        exit_reason = "stop_loss"
                    elif self._check_take_profit(position, curr):
                        exec_price_exit = position.take_profit if position.take_profit > 0 else exec_price
                        exit_reason = "take_profit"
                    else:
                        exec_price_exit = exec_price

                    # Compute trade P&L
                    trade_value = position.entry_price * position.quantity
                    gross_pnl = (exec_price_exit - position.entry_price) * position.direction * position.quantity
                    exit_costs = self.cost_model.compute_cost(
                        abs(exec_price_exit * position.quantity),
                        self.order_type, is_buy=False
                    )
                    net_pnl = gross_pnl - exit_costs.total

                    trade_id += 1
                    trades.append(Trade(
                        trade_id=trade_id,
                        symbol=position.symbol,
                        direction=position.direction,
                        entry_date=position.entry_date,
                        exit_date=curr["datetime"],
                        entry_price=position.entry_price,
                        exit_price=exec_price_exit,
                        quantity=position.quantity,
                        gross_pnl=gross_pnl,
                        costs=exit_costs.total + position.unrealized_pnl,  # entry costs stored in unrealized_pnl
                        net_pnl=net_pnl - position.unrealized_pnl,  # subtract entry costs
                        holding_bars=i - getattr(position, '_entry_bar', 0),
                        strategy=strategy_name,
                        entry_signal_confidence=position.signal_confidence,
                        exit_reason=exit_reason,
                    ))

                    capital += net_pnl - position.unrealized_pnl  # Realize the trade
                    position = None

            # Open new position
            if signal != 0 and position is None and capital > 0:
                trade_capital = capital * self.position_size_pct
                quantity = max(1, int(trade_capital / exec_price)) if exec_price > 0 else 0

                if quantity > 0:
                    entry_value = exec_price * quantity
                    entry_costs = self.cost_model.compute_cost(
                        entry_value, self.order_type, is_buy=True
                    )

                    position = Position(
                        symbol=prev.get("symbol", "UNKNOWN") if isinstance(prev.get("symbol"), str) else "UNKNOWN",
                        direction=signal,
                        entry_date=curr["datetime"],
                        entry_price=exec_price,
                        quantity=quantity,
                        strategy=strategy_name,
                        signal_confidence=confidence,
                    )
                    position.unrealized_pnl = entry_costs.total  # Store entry costs
                    position._entry_bar = i
                    capital -= entry_costs.total

            # Track equity
            mark_to_market = capital
            if position is not None:
                unrealized = (curr["close"] - position.entry_price) * position.direction * position.quantity
                mark_to_market += unrealized
            equity_history.append({
                "datetime": curr["datetime"],
                "equity": mark_to_market,
                "capital": capital,
                "in_position": position is not None,
            })

        # Close any remaining position at last bar
        if position is not None and len(df) > 0:
            last = df.iloc[-1]
            gross_pnl = (last["close"] - position.entry_price) * position.direction * position.quantity
            exit_costs = self.cost_model.compute_cost(
                abs(last["close"] * position.quantity), self.order_type, is_buy=False
            )
            trade_id += 1
            trades.append(Trade(
                trade_id=trade_id,
                symbol=position.symbol,
                direction=position.direction,
                entry_date=position.entry_date,
                exit_date=last["datetime"],
                entry_price=position.entry_price,
                exit_price=last["close"],
                quantity=position.quantity,
                gross_pnl=gross_pnl,
                costs=exit_costs.total + position.unrealized_pnl,
                net_pnl=gross_pnl - exit_costs.total - position.unrealized_pnl,
                holding_bars=len(df) - getattr(position, '_entry_bar', 0),
                strategy=strategy_name,
                exit_reason="end_of_data",
            ))
            capital += gross_pnl - exit_costs.total - position.unrealized_pnl

        # Build equity curve
        equity_df = pd.DataFrame(equity_history) if equity_history else pd.DataFrame(columns=["datetime", "equity"])

        # Compute metrics
        return self._compute_metrics(trades, equity_df, strategy_name, df)

    def _check_stop_loss(self, position: Position, bar: pd.Series) -> bool:
        if position.stop_loss <= 0:
            return False
        if position.direction == 1:
            return bar["low"] <= position.stop_loss
        else:
            return bar["high"] >= position.stop_loss

    def _check_take_profit(self, position: Position, bar: pd.Series) -> bool:
        if position.take_profit <= 0:
            return False
        if position.direction == 1:
            return bar["high"] >= position.take_profit
        else:
            return bar["low"] <= position.take_profit

    def _compute_metrics(
        self, trades: list[Trade], equity_df: pd.DataFrame,
        strategy_name: str, price_df: pd.DataFrame
    ) -> BacktestResult:
        """Compute comprehensive performance metrics."""

        if not trades or equity_df.empty:
            return BacktestResult(
                strategy_name=strategy_name, trades=trades, equity_curve=equity_df,
                daily_returns=pd.Series(dtype=float),
                total_return_pct=0, cagr=0, sharpe_ratio=0, sortino_ratio=0,
                max_drawdown_pct=0, max_drawdown_duration=0, profit_factor=0,
                win_rate=0, avg_win=0, avg_loss=0, expectancy=0,
                total_trades=0, total_costs=0, cost_scenario=self.cost_scenario_name,
                start_date=price_df["datetime"].iloc[0] if len(price_df) > 0 else None,
                end_date=price_df["datetime"].iloc[-1] if len(price_df) > 0 else None,
                initial_capital=self.initial_capital, final_capital=self.initial_capital,
            )

        # Equity curve returns
        equity_df["returns"] = equity_df["equity"].pct_change()
        daily_returns = equity_df["returns"].dropna()

        final_equity = equity_df["equity"].iloc[-1]
        total_return = (final_equity / self.initial_capital) - 1

        # CAGR
        start = pd.to_datetime(equity_df["datetime"].iloc[0])
        end = pd.to_datetime(equity_df["datetime"].iloc[-1])
        years = (end - start).days / 365.25
        cagr = (final_equity / self.initial_capital) ** (1 / max(years, 0.01)) - 1 if years > 0 else 0

        # Sharpe (annualized, using 252 trading days)
        mean_ret = daily_returns.mean()
        std_ret = daily_returns.std()
        sharpe = (mean_ret / std_ret) * np.sqrt(252) if std_ret > 0 else 0

        # Sortino
        downside = daily_returns[daily_returns < 0].std()
        sortino = (mean_ret / downside) * np.sqrt(252) if downside > 0 else 0

        # Max drawdown
        rolling_max = equity_df["equity"].expanding().max()
        drawdown = (equity_df["equity"] - rolling_max) / rolling_max
        max_dd = abs(drawdown.min()) if len(drawdown) > 0 else 0

        # Drawdown duration
        in_dd = drawdown < 0
        dd_groups = (~in_dd).cumsum()
        dd_durations = in_dd.groupby(dd_groups).sum()
        max_dd_duration = int(dd_durations.max()) if len(dd_durations) > 0 else 0

        # Trade metrics
        pnls = [t.net_pnl for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        win_rate = len(wins) / len(pnls) if pnls else 0
        avg_win = np.mean(wins) if wins else 0
        avg_loss = abs(np.mean(losses)) if losses else 0
        profit_factor = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else float('inf')
        expectancy = np.mean(pnls) if pnls else 0

        total_costs = sum(t.costs for t in trades)
        avg_holding = np.mean([t.holding_bars for t in trades]) if trades else 0

        # Calmar
        calmar = cagr / max_dd if max_dd > 0 else 0

        return BacktestResult(
            strategy_name=strategy_name,
            trades=trades,
            equity_curve=equity_df,
            daily_returns=daily_returns,
            total_return_pct=total_return * 100,
            cagr=cagr * 100,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown_pct=max_dd * 100,
            max_drawdown_duration=max_dd_duration,
            profit_factor=profit_factor,
            win_rate=win_rate * 100,
            avg_win=avg_win,
            avg_loss=avg_loss,
            expectancy=expectancy,
            total_trades=len(trades),
            total_costs=total_costs,
            cost_scenario=self.cost_scenario_name,
            start_date=start,
            end_date=end,
            initial_capital=self.initial_capital,
            final_capital=final_equity,
            calmar_ratio=calmar,
            avg_holding_bars=avg_holding,
        )

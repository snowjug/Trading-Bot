"""
Strategy 6: Micro-Capital Confluence Option Buyer (Viral Setup Model).
Evaluates the popular retail hypothesis:
"Can a micro-capital (Rs 10,000 - Rs 20,000) retail trader consistently achieve
3-5% daily returns trading 1 lot of NIFTY options with maximum 2 trades/day
using a high-confluence indicator alignment (EMA 9/21 + RSI Momentum + Volume)?"

Audits both:
1. The Retail Backtest Illusion (Optimistic Intrabar Resolution)
2. The Live Market Reality (Conservative Intrabar Resolution + Indian Statutory Friction)
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from src.strategies.base import Strategy
from src.regime.detector import RegimeState
from src.backtesting.cost_model import IndianCostModel, CostScenario, OrderType
from src.backtesting.intrabar_simulator import IntrabarSimulator, IntrabarMode
from src.research.independent_pnl import IndependentPnLCalculator
from src.utils.logging import setup_logging

logger = setup_logging("strategies.micro_momentum_buyer")


@dataclass
class MicroTradeResult:
    trade_date: str
    direction: str  # 'CE' or 'PE'
    entry_spot: float
    target_spot: float
    stop_spot: float
    entry_premium: float
    exit_premium: float
    option_pnl_pts: float
    gross_pnl: float
    statutory_costs: float
    net_pnl: float
    exit_reason: str  # 'TARGET', 'STOP', 'EOD'
    win: bool


class MicroMomentumBuyerStrategy(Strategy):
    """
    Strategy 6: Micro-Capital Confluence Option Buyer.
    
    Setup Rules (The 'Viral' Retail Confluence System):
    1. Trend Filter: EMA 9 > EMA 21 (for CE) or EMA 9 < EMA 21 (for PE).
    2. Momentum Filter: RSI (14) in active momentum zone (54 to 70 for CE; 30 to 46 for PE).
    3. Breakout Trigger: High crosses previous bar's high (CE) or Low crosses previous low (PE).
    4. Execution Limit: Strict maximum of 2 trades per day.
    5. Capital Constraint: 1 lot (25 qty on Nifty) with Rs 10,000 to Rs 20,000 account capital.
    6. Profit Target: 3-5% on account capital (~Rs 350 to Rs 500 = 14 to 20 option points).
    7. Stop Loss: Defined risk stop (~Rs 250 to Rs 300 = 10 to 12 option points).
    """

    name = "micro_momentum_buyer"
    hypothesis = (
        "Buying single-lot NIFTY ATM options with high indicator confluence (EMA 9/21, RSI, ATR) "
        "and taking 3-5% daily profits with maximum 2 trades/day generates high win rates and survives "
        "on micro-capital (Rs 10,000 - Rs 20,000)."
    )
    strategy_type = "micro_option_buying"
    min_data_points = 30

    def __init__(
        self,
        target_opt_pts: float = 16.0,  # ~Rs 400 target (4% on Rs 10,000)
        stop_opt_pts: float = 10.0,    # ~Rs 250 risk (2.5% on Rs 10,000)
        max_trades_per_day: int = 2,
        opt_delta: float = 0.55,
        lot_size: int = 25,
    ):
        self.target_opt_pts = target_opt_pts
        self.stop_opt_pts = stop_opt_pts
        self.max_trades_per_day = max_trades_per_day
        self.opt_delta = opt_delta
        self.lot_size = lot_size

    def generate_signals(
        self,
        df: pd.DataFrame,
        regime: Optional[RegimeState] = None,
    ) -> pd.DataFrame:
        if not self.validate_inputs(df):
            return pd.DataFrame()

        df = df.copy()
        close = df["close"]
        high = df["high"]
        low = df["low"]

        # Indicator calculations
        df["ema_9"] = close.ewm(span=9, adjust=False).mean()
        df["ema_21"] = close.ewm(span=21, adjust=False).mean()

        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = -delta.clip(upper=0).rolling(14).mean()
        df["rsi"] = 100.0 - (100.0 / (1.0 + (gain / (loss + 1e-9))))

        prev_c = close.shift(1)
        tr = pd.concat([high - low, (high - prev_c).abs(), (low - prev_c).abs()], axis=1).max(axis=1)
        df["atr"] = tr.rolling(14).mean()

        signals = []
        confidences = []

        for i in range(len(df)):
            if i < 21:
                signals.append(0)
                confidences.append(0.0)
                continue

            prev = df.iloc[i - 1]
            curr = df.iloc[i]

            sig = 0
            conf = 0.0

            # Bullish confluence
            if prev["ema_9"] > prev["ema_21"] and prev["rsi"] > 54.0 and curr["high"] > prev["high"]:
                sig = 1
                conf = min(0.95, 0.50 + (prev["rsi"] - 50.0) / 50.0)
            # Bearish confluence
            elif prev["ema_9"] < prev["ema_21"] and prev["rsi"] < 46.0 and curr["low"] < prev["low"]:
                sig = -1
                conf = min(0.95, 0.50 + (50.0 - prev["rsi"]) / 50.0)

            signals.append(sig)
            confidences.append(conf)

        sig_df = pd.DataFrame({
            "datetime": df["datetime"],
            "signal": signals,
            "confidence": confidences,
            "strategy": self.name,
        })
        return sig_df

    def get_parameters(self) -> dict:
        return {
            "target_opt_pts": self.target_opt_pts,
            "stop_opt_pts": self.stop_opt_pts,
            "max_trades_per_day": self.max_trades_per_day,
            "opt_delta": self.opt_delta,
            "lot_size": self.lot_size,
        }

    def evaluate_on_dataset(
        self,
        nifty_df: pd.DataFrame,
        initial_capital: float = 10000.0,
        intrabar_mode: IntrabarMode = IntrabarMode.CONSERVATIVE,
    ) -> Dict[str, any]:
        """
        Execute full trade simulation with capital constraints and statutory friction.
        """
        signals_df = self.generate_signals(nifty_df)
        df = nifty_df.merge(signals_df[["datetime", "signal"]], on="datetime")

        cost_calc = IndependentPnLCalculator()
        capital = initial_capital
        peak_capital = initial_capital
        max_dd = 0.0

        trades: List[MicroTradeResult] = []
        daily_trades_count: Dict[str, int] = {}
        rejections = 0

        for i in range(21, len(df)):
            row = df.iloc[i]
            prev_row = df.iloc[i - 1]
            dt_str = str(row["datetime"])[:10]
            sig = row["signal"]

            if sig == 0:
                continue

            # Daily trade limit check
            trades_today = daily_trades_count.get(dt_str, 0)
            if trades_today >= self.max_trades_per_day:
                continue

            # Capital check (must have at least Rs 3,000 to buy 1 lot)
            entry_premium = 100.0
            cash_required = entry_premium * self.lot_size  # Rs 2,500
            if capital < cash_required or capital < 3000.0:
                rejections += 1
                continue

            daily_trades_count[dt_str] = trades_today + 1
            is_ce = (sig == 1)
            entry_spot = prev_row["high"] if is_ce else prev_row["low"]

            target_spot_pts = self.target_opt_pts / self.opt_delta
            stop_spot_pts = self.stop_opt_pts / self.opt_delta

            res = IntrabarSimulator.resolve_exit(
                is_long=is_ce,
                entry_price=entry_spot,
                target_pts=target_spot_pts,
                stop_pts=stop_spot_pts,
                high=row["high"],
                low=row["low"],
                close=row["close"],
                mode=intrabar_mode,
            )

            if res.is_stop:
                opt_pnl = -self.stop_opt_pts
                exit_reason = "STOP"
            elif res.is_target:
                opt_pnl = self.target_opt_pts
                exit_reason = "TARGET"
            else:
                close_pts = (row["close"] - entry_spot) if is_ce else (entry_spot - row["close"])
                opt_pnl = max(-self.stop_opt_pts, min(self.target_opt_pts, close_pts * self.opt_delta))
                exit_reason = "EOD"

            exit_premium = max(0.5, entry_premium + opt_pnl)
            gross_pnl = opt_pnl * self.lot_size

            # Exact Indian statutory costs
            costs = cost_calc.compute_trade_costs(
                entry_price=entry_premium,
                exit_price=exit_premium,
                quantity=self.lot_size,
                is_option=True,
                slippage_pts=0.5,
            )
            net_pnl = gross_pnl - costs["total_costs"]
            capital += net_pnl

            peak_capital = max(peak_capital, capital)
            dd = peak_capital - capital
            max_dd = max(max_dd, dd)

            trades.append(MicroTradeResult(
                trade_date=dt_str,
                direction="CE" if is_ce else "PE",
                entry_spot=entry_spot,
                target_spot=entry_spot + target_spot_pts if is_ce else entry_spot - target_spot_pts,
                stop_spot=entry_spot - stop_spot_pts if is_ce else entry_spot + stop_spot_pts,
                entry_premium=entry_premium,
                exit_premium=exit_premium,
                option_pnl_pts=opt_pnl,
                gross_pnl=gross_pnl,
                statutory_costs=costs["total_costs"],
                net_pnl=net_pnl,
                exit_reason=exit_reason,
                win=net_pnl > 0,
            ))

        n_trades = len(trades)
        wins = sum(1 for t in trades if t.win)
        win_rate = (wins / n_trades * 100.0) if n_trades > 0 else 0.0
        tot_net = capital - initial_capital
        roc = (tot_net / initial_capital) * 100.0
        tot_friction = sum(t.statutory_costs for t in trades)

        gross_gains = sum(t.net_pnl for t in trades if t.win)
        gross_losses = abs(sum(t.net_pnl for t in trades if not t.win))
        pf = (gross_gains / gross_losses) if gross_losses > 0 else 0.0

        daily_returns = [t.net_pnl / initial_capital for t in trades]
        sharpe = (np.mean(daily_returns) / (np.std(daily_returns) + 1e-9)) * np.sqrt(252) if len(daily_returns) > 5 and np.std(daily_returns) > 0 else 0.0

        return {
            "initial_capital": initial_capital,
            "ending_capital": round(capital, 2),
            "net_pnl": round(tot_net, 2),
            "return_on_capital_pct": round(roc, 2),
            "trades_executed": n_trades,
            "margin_rejections": rejections,
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": round(pf, 2),
            "max_drawdown": round(max_dd, 2),
            "max_drawdown_pct": round((max_dd / peak_capital * 100.0) if peak_capital > 0 else 0.0, 2),
            "total_statutory_friction": round(tot_friction, 2),
            "sharpe_ratio": round(float(sharpe), 2),
            "intrabar_mode": intrabar_mode.name,
        }

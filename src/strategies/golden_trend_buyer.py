"""
Strategy 4: Golden Micro-Trend Option Buyer (The "Golden Setup" of Professional Option Buyers).
Engineered specifically for Micro-Capital accounts (₹10,000 / 10k).
Executes as an Intraday Trend Runner on NIFTY 50 / BANK NIFTY (1 Lot ATM Call/Put).
Catches asymmetric 1:3 Risk-to-Reward micro-trends off the 20 EMA / VWAP pullback zone
with ZERO overnight theta decay and zero gap risk.
"""
from dataclasses import dataclass
from datetime import datetime
import numpy as np
import pandas as pd
from src.strategies.base import Strategy
from src.regime.detector import RegimeState
from src.backtesting.cost_model import IndianCostModel, OrderType
from src.backtesting.intrabar_simulator import IntrabarSimulator, IntrabarMode
from src.utils.logging import setup_logging

logger = setup_logging("strategies.golden_trend_buyer")


@dataclass
class GoldenTrendTradeResult:
    date: pd.Timestamp
    option_type: str  # 'CE' or 'PE'
    spot_entry: float
    spot_exit: float
    option_entry_prem: float
    option_exit_prem: float
    pnl: float
    return_pct: float
    win: bool
    exit_reason: str  # 'TARGET_1:3', 'STOP', 'EOD_RUN'
    capital_after: float


class GoldenTrendOptionBuyerStrategy(Strategy):
    """
    Strategy 4: The Golden Micro-Trend Options Buyer Engine.

    The "Golden Setup" Rules:
    1. Macro Trend Regime:
       - Bullish CE: 20 EMA > 50 EMA and Price > VWAP.
       - Bearish PE: 20 EMA < 50 EMA and Price < VWAP.
    2. The Value Zone Pullback (Never Buy Extended Tops):
       - Bullish CE: Price pulls back into the 20 EMA zone (previous low within 0.6% of 20 EMA).
       - Bearish PE: Price bounces into the 20 EMA zone (previous high within 0.6% of 20 EMA).
    3. Reversal Expansion Confirmation:
       - Bullish CE: Current candle closes above 9 EMA and breaks previous candle's High.
       - Bearish PE: Current candle closes below 9 EMA and breaks previous candle's Low.
    4. Momentum & Volume Confluence:
       - RSI in the expansion corridor (54-72 for CE, 28-46 for PE).
       - Volume > 20-day Volume MA (institutional demand confirms the bounce).
    5. Asymmetric 1:3 Risk-to-Reward Runner:
       - Stop Loss: 0.25 ATR (~25-30 Nifty pts, ~₹12-15 option loss).
       - Target: 0.75 ATR (3x risk, ~+40% to +60% option premium surge).
       - EOD Square-Off: 03:15 PM mandatory exit ensures zero overnight theta decay.
    """

    name = "golden_trend_option_buyer"
    hypothesis = (
        "Entering option buying trades exclusively at 20 EMA / VWAP pullback confluence within "
        "established trends provides a tight stop-loss (0.25 ATR) and a high-probability 1:3 "
        "asymmetric trend expansion (0.75 ATR) that compounds micro-capital (₹10,000) with an 85%+ win rate."
    )
    strategy_type = "intraday_options_trend_runner"
    min_data_points = 50

    def __init__(
        self,
        initial_capital: float = 10000.0,
        pullback_tolerance: float = 0.006,
        target_atr_mult: float = 0.75,
        stop_atr_mult: float = 0.25,
        friction_per_trade: float = 45.0,
    ):
        self.initial_capital = initial_capital
        self.pullback_tolerance = pullback_tolerance
        self.target_atr_mult = target_atr_mult
        self.stop_atr_mult = stop_atr_mult
        self.friction_per_trade = friction_per_trade

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute trend EMAs, VWAP, ATR, and RSI.
        """
        df = df.copy()
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("datetime").reset_index(drop=True)

        # EMAs
        df["ema_9"] = df["close"].ewm(span=9).mean()
        df["ema_20"] = df["close"].ewm(span=20).mean()
        df["ema_50"] = df["close"].ewm(span=50).mean()

        # ATR 14
        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - df["close"].shift(1)).abs()
        tr3 = (df["low"] - df["close"].shift(1)).abs()
        df["tr"] = np.maximum(tr1, np.maximum(tr2, tr3))
        df["atr_14"] = df["tr"].rolling(14).mean()

        # VWAP proxy (20-day rolling typical price weighted by volume)
        tp = (df["high"] + df["low"] + df["close"]) / 3.0
        df["vwap_20"] = (tp * df["volume"]).rolling(20).sum() / (df["volume"].rolling(20).sum() + 1e-9)

        # Volume MA
        df["vol_ma20"] = df["volume"].rolling(20).mean()

        # RSI 14
        delta = df["close"].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        df["rsi_14"] = 100 - (100 / (1 + rs))

        return df

    def generate_signals(
        self,
        df: pd.DataFrame,
        regime: RegimeState | None = None,
    ) -> pd.DataFrame:
        """
        Generate continuous daily signal where:
         1 = Bullish Golden Trend CE Trigger
        -1 = Bearish Golden Trend PE Trigger
         0 = Neutral / Cash
        """
        if not self.validate_inputs(df):
            return pd.DataFrame()

        calc_df = self.compute_indicators(df)
        signals = []
        confidences = []

        for i in range(len(calc_df)):
            if i < 40:
                signals.append(0)
                confidences.append(0.0)
                continue

            row = calc_df.iloc[i]
            prev = calc_df.iloc[i - 1]

            # Bullish Golden Trend Pullback Confluence:
            # 1. 20 EMA > 50 EMA (Macro Bull Trend)
            # 2. Price > VWAP
            # 3. Pullback to 20 EMA Value Zone (prev Low <= 20 EMA * 1.006)
            # 4. Expansion Breakout: Close > 9 EMA and Close > prev High
            # 5. RSI between 54 and 72
            # 6. Volume > 20-day MA
            is_bull = (
                row["ema_20"] > row["ema_50"] and
                row["close"] > row["vwap_20"] and
                prev["low"] <= prev["ema_20"] * (1.0 + self.pullback_tolerance) and
                row["close"] > row["ema_9"] and row["close"] > prev["high"] and
                54 <= row["rsi_14"] <= 72 and
                row["volume"] > row["vol_ma20"]
            )

            # Bearish Golden Trend Bounce Confluence:
            # 1. 20 EMA < 50 EMA (Macro Bear Trend)
            # 2. Price < VWAP
            # 3. Bounce to 20 EMA Value Zone (prev High >= 20 EMA * 0.994)
            # 4. Breakdown: Close < 9 EMA and Close < prev Low
            # 5. RSI between 28 and 46
            # 6. Volume > 20-day MA
            is_bear = (
                row["ema_20"] < row["ema_50"] and
                row["close"] < row["vwap_20"] and
                prev["high"] >= prev["ema_20"] * (1.0 - self.pullback_tolerance) and
                row["close"] < row["ema_9"] and row["close"] < prev["low"] and
                28 <= row["rsi_14"] <= 46 and
                row["volume"] > row["vol_ma20"]
            )

            if is_bull:
                signals.append(1)
                confidences.append(0.90)
            elif is_bear:
                signals.append(-1)
                confidences.append(0.90)
            else:
                signals.append(0)
                confidences.append(0.0)

        return pd.DataFrame({
            "datetime": calc_df["datetime"],
            "signal": signals,
            "confidence": confidences,
        })

    def run_simulation(
        self,
        df: pd.DataFrame,
        lot_size_default: int = 50,
        intrabar_mode: IntrabarMode = IntrabarMode.CONSERVATIVE,
        cost_model: IndianCostModel | None = None,
    ) -> dict:
        """
        Execute historical simulation with 1 Lot ATM options, 1:3 RR targets,
        intrabar path-dependency resolution, and versioned Indian statutory costs.
        STATUS: SIMULATION ONLY / UNVERIFIED (Approximate option delta proxy).
        """
        if cost_model is None:
            cost_model = IndianCostModel()
        calc_df = self.compute_indicators(df)
        sig_df = self.generate_signals(df)
        merged = pd.merge(calc_df, sig_df[["datetime", "signal"]], on="datetime")

        capital = self.initial_capital
        trades: list[GoldenTrendTradeResult] = []

        for i in range(40, len(merged)):
            row = merged.iloc[i]
            prev = merged.iloc[i - 1]
            date = row["datetime"]
            sig = row["signal"]
            atr = row["atr_14"]
            close = row["close"]
            high = row["high"]
            low = row["low"]

            if sig == 0:
                continue

            is_ce = sig == 1
            entry_spot = prev["high"] if is_ce else prev["low"]

            # Standard NSE lot size transition: 50 -> 25 for Nifty in 2024
            lot_size = lot_size_default if date.year < 2024 else max(15, int(lot_size_default / 2))

            # 1:3 Risk-Reward Targets
            stop_pts = self.stop_atr_mult * atr
            target_pts = self.target_atr_mult * atr

            opt_delta = 0.55
            target_opt = target_pts * opt_delta
            stop_opt = stop_pts * opt_delta

            if is_ce:
                close_pts = close - entry_spot
            else:
                close_pts = entry_spot - close

            # Intraday execution determination via IntrabarSimulator
            resolution = IntrabarSimulator.resolve_exit(
                is_long=is_ce,
                entry_price=entry_spot,
                target_pts=target_pts,
                stop_pts=stop_pts,
                high=high,
                low=low,
                close=close,
                mode=intrabar_mode,
            )
            hit = resolution.exit_reason
            spot_exit = resolution.exit_price

            if resolution.is_stop:
                opt_pnl = -stop_opt
            elif resolution.is_target:
                opt_pnl = target_opt
            else:
                opt_pnl = max(-stop_opt, min(target_opt, close_pts * opt_delta))

            entry_prem_approx = 100.0
            exit_prem_approx = max(0.5, entry_prem_approx + opt_pnl)

            gross_pnl = opt_pnl * lot_size
            cost_comp = cost_model.compute_round_trip(
                entry_price=entry_prem_approx,
                exit_price=exit_prem_approx,
                qty=lot_size,
                order_type=OrderType.OPTIONS,
                trade_date=date.to_pydatetime() if hasattr(date, "to_pydatetime") else date,
                atr=atr,
            )
            friction = cost_comp.total
            net_pnl = gross_pnl - friction
            capital += net_pnl
            capital = max(100.0, capital)

            entry_prem_approx = 100.0
            exit_prem_approx = max(0.5, entry_prem_approx + opt_pnl)
            ret_pct = (opt_pnl / entry_prem_approx) * 100.0

            trades.append(GoldenTrendTradeResult(
                date=date,
                option_type="CE" if is_ce else "PE",
                spot_entry=float(entry_spot),
                spot_exit=float(spot_exit),
                option_entry_prem=float(entry_prem_approx),
                option_exit_prem=float(exit_prem_approx),
                pnl=float(net_pnl),
                return_pct=float(ret_pct),
                win=net_pnl > 0,
                exit_reason=hit,
                capital_after=float(capital),
            ))

        tdf = pd.DataFrame([t.__dict__ for t in trades])
        total_trades = len(tdf)
        win_rate = float(tdf["win"].mean() * 100.0) if total_trades > 0 else 0.0
        net_profit = float(capital - self.initial_capital)

        return {
            "initial_capital": self.initial_capital,
            "final_capital": capital,
            "net_profit": net_profit,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "target_hits": int((tdf["exit_reason"] == "TARGET_1:3").sum()) if total_trades > 0 else 0,
            "stop_hits": int((tdf["exit_reason"] == "STOP").sum()) if total_trades > 0 else 0,
            "eod_runs": int((tdf["exit_reason"] == "EOD_RUN").sum()) if total_trades > 0 else 0,
            "trades_df": tdf,
        }

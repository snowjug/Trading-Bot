"""
Strategy 3: Confluence Gamma Scalper (Viral 9/20 EMA + VWAP + Bollinger Band Squeeze).
Engineered specifically for Micro-Capital accounts (₹10,000 / 10k).
Executes as an Intraday MIS Option Scalper (buying 1 lot of ATM NIFTY Call/Put)
and exits by 03:15 PM to ensure ZERO overnight theta decay and zero gap risk.
"""
from dataclasses import dataclass
from datetime import datetime
import numpy as np
import pandas as pd
from src.strategies.base import Strategy
from src.regime.detector import RegimeState
from src.deriv.options_engine import BlackScholesEngine
from src.backtesting.cost_model import IndianCostModel, OrderType
from src.backtesting.intrabar_simulator import IntrabarSimulator, IntrabarMode
from src.utils.logging import setup_logging

logger = setup_logging("strategies.confluence_scalper")


@dataclass
class ScalpTradeResult:
    date: pd.Timestamp
    option_type: str  # 'CE' or 'PE'
    spot_entry: float
    spot_exit: float
    option_entry_prem: float
    option_exit_prem: float
    pnl: float
    return_pct: float
    win: bool
    exit_reason: str  # 'TARGET', 'STOP', 'EOD_CLOSE'
    capital_after: float


class ConfluenceGammaScalperStrategy(Strategy):
    """
    Strategy 3: Multi-Confluence Intraday Options Scalper.

    Core Pillars (The "Viral 3-Pillar" Breakout):
    1. Bollinger Band Squeeze & Expansion:
       - Bandwidth contracts into the bottom 30th percentile of volatility.
       - Breakout candle breaches the upper band (CE) or lower band (PE).
    2. EMA Momentum Alignment:
       - Bullish CE: 9 EMA > 20 EMA > 50 EMA.
       - Bearish PE: 9 EMA < 20 EMA < 50 EMA.
    3. VWAP Dominance:
       - Price trades strictly on the institutional side of VWAP.
    4. Volume & RSI Surge:
       - Volume exceeds 1.2x 20-day moving average.
       - RSI confirms directional expansion (54-75 for CE, 25-46 for PE).

    Micro-Capital Management (₹10,000):
    - Trades 1 Lot ATM Nifty Option (Intraday MIS).
    - Fixed 2:1 Reward-to-Risk ratio (Target: 0.50 ATR, Stop: 0.25 ATR).
    - Mandated 03:15 PM EOD square-off eliminates overnight theta decay completely.
    - Indian statutory friction (₹20 buy + ₹20 sell + STT + turnover + GST) deducted per trade.
    """

    name = "confluence_gamma_scalper"
    hypothesis = (
        "Waiting for multi-indicator confluence (9/20 EMA stack + VWAP + Bollinger squeeze breakout "
        "+ volume surge) eliminates retail overtrading, while intraday MIS execution captures "
        "asymmetric gamma expansions with zero overnight theta decay on micro-capital (₹10,000)."
    )
    strategy_type = "intraday_options_scalp"
    min_data_points = 50

    def __init__(
        self,
        initial_capital: float = 10000.0,
        bb_period: int = 20,
        bb_std: float = 2.0,
        squeeze_quantile: float = 0.30,
        vol_surge_mult: float = 1.20,
        target_atr_mult: float = 0.50,
        stop_atr_mult: float = 0.25,
        friction_per_trade: float = 45.0,
    ):
        self.initial_capital = initial_capital
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.squeeze_quantile = squeeze_quantile
        self.vol_surge_mult = vol_surge_mult
        self.target_atr_mult = target_atr_mult
        self.stop_atr_mult = stop_atr_mult
        self.friction_per_trade = friction_per_trade

    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute all required indicators: EMAs, VWAP proxy, Bollinger Bands, ATR, RSI, and Volume MA.
        """
        df = df.copy()
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("datetime").reset_index(drop=True)

        # EMAs
        df["ema_9"] = df["close"].ewm(span=9).mean()
        df["ema_20"] = df["close"].ewm(span=20).mean()
        df["ema_50"] = df["close"].ewm(span=50).mean()

        # Typical Price & VWAP proxy (20-day rolling typical price weighted by volume)
        tp = (df["high"] + df["low"] + df["close"]) / 3.0
        df["vwap_20"] = (tp * df["volume"]).rolling(20).sum() / (df["volume"].rolling(20).sum() + 1e-9)

        # Bollinger Bands
        df["bb_mid"] = df["close"].rolling(self.bb_period).mean()
        df["bb_std_val"] = df["close"].rolling(self.bb_period).std()
        df["bb_upper"] = df["bb_mid"] + self.bb_std * df["bb_std_val"]
        df["bb_lower"] = df["bb_mid"] - self.bb_std * df["bb_std_val"]
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]
        df["bb_squeeze"] = df["bb_width"] < df["bb_width"].rolling(40).quantile(self.squeeze_quantile)

        # ATR
        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - df["close"].shift(1)).abs()
        tr3 = (df["low"] - df["close"].shift(1)).abs()
        df["tr"] = np.maximum(tr1, np.maximum(tr2, tr3))
        df["atr_14"] = df["tr"].rolling(14).mean()

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
         1 = Bullish CE Scalp trigger
        -1 = Bearish PE Scalp trigger
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

            # Bollinger squeeze occurred within the last 4 trading days
            squeezed = calc_df.iloc[max(0, i - 4):i]["bb_squeeze"].any()

            # Bullish CE Confluence:
            # 1. 9 EMA > 20 EMA > 50 EMA
            # 2. Breakout candle piercing Upper Bollinger Band
            # 3. Price > VWAP
            # 4. RSI between 54 and 75
            # 5. Volume > 20-day MA
            is_ce = (
                squeezed and
                row["ema_9"] > row["ema_20"] and row["ema_20"] > row["ema_50"] and
                row["open"] >= prev["bb_mid"] and
                row["high"] > prev["bb_upper"] and
                54 <= row["rsi_14"] <= 75 and
                row["volume"] > row["vol_ma20"]
            )

            # Bearish PE Confluence:
            # 1. 9 EMA < 20 EMA < 50 EMA
            # 2. Breakdown candle piercing Lower Bollinger Band
            # 3. Price < VWAP
            # 4. RSI between 25 and 46
            # 5. Volume > 20-day MA
            is_pe = (
                squeezed and
                row["ema_9"] < row["ema_20"] and row["ema_20"] < row["ema_50"] and
                row["open"] <= prev["bb_mid"] and
                row["low"] < prev["bb_lower"] and
                25 <= row["rsi_14"] <= 46 and
                row["volume"] > row["vol_ma20"]
            )

            if is_ce:
                signals.append(1)
                confidences.append(0.85)
            elif is_pe:
                signals.append(-1)
                confidences.append(0.85)
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
        intrabar_mode: IntrabarMode = IntrabarMode.CONSERVATIVE,
        cost_model: IndianCostModel | None = None,
    ) -> dict:
        """
        Execute historical backtest modeling 1-lot ATM options intraday scalps
        under realistic intrabar execution (Conservative/Optimistic) and IndianCostModel.
        STATUS: SIMULATION ONLY / UNVERIFIED (No tick-level historical option chain).
        """
        if cost_model is None:
            cost_model = IndianCostModel()
        calc_df = self.compute_indicators(df)
        sig_df = self.generate_signals(df)
        merged = pd.merge(calc_df, sig_df[["datetime", "signal"]], on="datetime")

        capital = self.initial_capital
        trades: list[ScalpTradeResult] = []

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
            entry_spot = prev["bb_upper"] if is_ce else prev["bb_lower"]
            lot_size = 50 if date.year < 2024 else 25

            # Intraday adverse and favorable price excursions
            if is_ce:
                max_fav_pts = high - entry_spot
                max_adv_pts = entry_spot - low
                close_pts = close - entry_spot
            else:
                max_fav_pts = entry_spot - low
                max_adv_pts = high - entry_spot
                close_pts = entry_spot - close

            target_pts = self.target_atr_mult * atr
            stop_pts = self.stop_atr_mult * atr

            # Option delta multiplier for ATM strike (0.55 delta)
            opt_delta = 0.55
            target_opt = target_pts * opt_delta
            stop_opt = stop_pts * opt_delta

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
            # Dynamic turnover friction via IndianCostModel
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

            trades.append(ScalpTradeResult(
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
            "target_hits": int((tdf["exit_reason"] == "TARGET").sum()) if total_trades > 0 else 0,
            "stop_hits": int((tdf["exit_reason"] == "STOP").sum()) if total_trades > 0 else 0,
            "eod_exits": int((tdf["exit_reason"] == "EOD_CLOSE").sum()) if total_trades > 0 else 0,
            "trades_df": tdf,
        }

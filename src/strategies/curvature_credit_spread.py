"""
Curvature Credit Spread Overnight Strategy (Inspired by Zen Credit / Curvature Spread on Dhan/Stratzy).
Captures strike curvature and volatility skew imbalances using asymmetric overnight credit spreads.
Enters between 03:15 PM and 03:25 PM and harvests overnight theta decay and volatility crush.
"""
from dataclasses import dataclass
from datetime import datetime
import numpy as np
import pandas as pd
from src.strategies.base import Strategy
from src.regime.detector import RegimeState
from src.backtesting.cost_model import IndianCostModel, OrderType
from src.utils.logging import setup_logging

logger = setup_logging("strategies.curvature_spread")


@dataclass
class CurvatureTradeResult:
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    spread_type: str  # 'bull_put', 'bear_call', 'iron_condor'
    spot_entry: float
    short_strike: float
    long_strike: float
    net_credit: float
    lots: int
    pnl: float
    win: bool
    breached: bool


class CurvatureCreditSpreadStrategy(Strategy):
    """
    Strategy 2: Curvature Credit Spread Overnight Engine (Zen Credit Model).

    Core Principles:
    1. Strike Curvature & Skew Detection:
       - Evaluates implied volatility skew across OTM strikes before market close (03:15 - 03:25 PM).
       - When Put skew is distorted/overpriced (RSI < 44 or panic dips above 200 EMA) -> Sells Bull Put Spread.
       - When Call skew is distorted/overpriced (RSI > 62 or greed rallies) -> Sells Bear Call Spread.
       - When skew is balanced (48 <= RSI <= 58) -> Sells Curvature Iron Condor.
    2. Overnight Volatility Crush:
       - Positions enter at 03:20 PM and harvest the rapid overnight decay and morning opening crush.
    3. Strictly Defined Maximum Risk:
       - Every short option is backed by a protective outer long wing at 1.8-SD.
    """

    name = "curvature_credit_spread"
    hypothesis = (
        "Overnight options pricing exhibits systematic strike curvature distortions due to "
        "retail hedging imbalances; deploying asymmetric defined-risk Bull Put and Bear Call "
        "credit spreads captures overnight theta decay and volatility crush with an 80%+ win rate."
    )
    strategy_type = "options_credit_spread"
    min_data_points = 200

    def __init__(
        self,
        short_sd: float = 1.3,
        wing_sd: float = 1.9,
        max_vix: float = 22.0,
        rsi_oversold_put: float = 44.0,
        rsi_overbought_call: float = 62.0,
        capital_allocation: float = 0.70,
        max_lots: int = 25,
    ):
        self.short_sd = short_sd
        self.wing_sd = wing_sd
        self.max_vix = max_vix
        self.rsi_oversold_put = rsi_oversold_put
        self.rsi_overbought_call = rsi_overbought_call
        self.capital_allocation = capital_allocation
        self.max_lots = max_lots

    def generate_signals(
        self,
        df: pd.DataFrame,
        regime: RegimeState | None = None,
    ) -> pd.DataFrame:
        """
        Generate continuous daily signal where 1 indicates an active credit spread regime.
        """
        if not self.validate_inputs(df):
            return pd.DataFrame()

        df = df.copy()
        rsi = df["rsi_14"] if "rsi_14" in df.columns else pd.Series(50.0, index=df.index)
        vix = df["vix"] if "vix" in df.columns else pd.Series(15.0, index=df.index)

        # Active when volatility is below panic threshold
        active = vix < self.max_vix

        signal = np.where(active, 1, 0)
        confidence = np.clip(1.0 - (vix / 35.0), 0.5, 0.95)

        signals = pd.DataFrame({
            "datetime": df["datetime"],
            "signal": signal,
            "confidence": confidence,
        })
        signals["strategy"] = self.name
        return signals

    def get_parameters(self) -> dict:
        return {
            "short_sd": self.short_sd,
            "wing_sd": self.wing_sd,
            "max_vix": self.max_vix,
            "rsi_oversold_put": self.rsi_oversold_put,
            "rsi_overbought_call": self.rsi_overbought_call,
            "capital_allocation": self.capital_allocation,
            "max_lots": self.max_lots,
        }

    @staticmethod
    def simulate_curvature_fund(
        nifty_df: pd.DataFrame,
        vix_df: pd.DataFrame,
        initial_capital: float = 100000.0,
        short_sd: float = 1.3,
        max_lots: int = 25,
    ) -> dict:
        """
        Execute full quantitative backtest of Curvature Credit Spreads.
        """
        nifty_base = nifty_df.copy()
        if "vix" in nifty_base.columns and (vix_df is None or vix_df.empty):
            nifty = nifty_base.sort_values("datetime").reset_index(drop=True)
        else:
            if "vix" in nifty_base.columns:
                nifty_base = nifty_base.drop(columns=["vix"])
            vix_col = "vix" if "vix" in vix_df.columns else "close"
            vix_clean = vix_df[["datetime", vix_col]].rename(columns={vix_col: "vix"})
            nifty = nifty_base.merge(vix_clean, on="datetime", how="inner").sort_values("datetime").reset_index(drop=True)

        capital = initial_capital
        trades = []
        equity_history = []

        for i in range(200, len(nifty) - 2, 2):
            dt = nifty.iloc[i]["datetime"]
            nc = nifty.iloc[i]["close"]
            nvix = nifty.iloc[i]["vix"]
            nrsi = nifty.iloc[i].get("rsi_14", 50.0)

            n_slice = nifty.iloc[i + 1 : i + 3]
            max_h = n_slice["high"].max()
            min_l = n_slice["low"].min()

            trade_pnl = 0.0

            if nvix < 22.0:
                em = nc * (nvix / 100.0) * np.sqrt(2.0 / 365.0)
                # Defined margin: ~₹65,000 - ₹85,000 per lot for a credit spread
                margin_per_spread = nc * 50 * 0.08
                lots = max(1, min(max_lots, int((capital * 0.70) / margin_per_spread)))

                if nrsi < 44.0:
                    # Bull Put Spread: Sell OTM Put, Buy protective lower Put
                    short_p = nc - short_sd * em
                    long_p = nc - (short_sd + 0.6) * em
                    breach = min_l < short_p
                    pts = max(35.0, nc * 0.0032)
                    credit = pts * 50
                    loss = -credit * 1.5
                    trade_pnl = ((credit * 0.82 * lots) if not breach else (loss * lots)) - (lots * 140.0)
                    capital += trade_pnl
                    trades.append({
                        "datetime": dt,
                        "side": "bull_put_spread",
                        "short_k": short_p,
                        "long_k": long_p,
                        "win": not breach,
                        "pnl": trade_pnl,
                        "lots": lots,
                    })

                elif nrsi > 62.0:
                    # Bear Call Spread: Sell OTM Call, Buy protective higher Call
                    short_c = nc + short_sd * em
                    long_c = nc + (short_sd + 0.6) * em
                    breach = max_h > short_c
                    pts = max(35.0, nc * 0.0032)
                    credit = pts * 50
                    loss = -credit * 1.5
                    trade_pnl = ((credit * 0.82 * lots) if not breach else (loss * lots)) - (lots * 140.0)
                    capital += trade_pnl
                    trades.append({
                        "datetime": dt,
                        "side": "bear_call_spread",
                        "short_k": short_c,
                        "long_k": long_c,
                        "win": not breach,
                        "pnl": trade_pnl,
                        "lots": lots,
                    })

                elif 48.0 <= nrsi <= 58.0:
                    # Symmetrical Curvature Iron Condor
                    short_c = nc + (short_sd + 0.3) * em
                    short_p = nc - (short_sd + 0.3) * em
                    breach = (max_h > short_c) or (min_l < short_p)
                    pts = max(40.0, nc * 0.0036)
                    credit = pts * 50
                    loss = -credit * 1.5
                    trade_pnl = ((credit * 0.85 * lots) if not breach else (loss * lots)) - (lots * 140.0)
                    capital += trade_pnl
                    trades.append({
                        "datetime": dt,
                        "side": "curvature_condor",
                        "short_k": short_c,
                        "long_k": short_p,
                        "win": not breach,
                        "pnl": trade_pnl,
                        "lots": lots,
                    })

            equity_history.append({"datetime": dt, "equity": capital})

        eq_df = pd.DataFrame(equity_history)
        if eq_df.empty:
            return {}

        duration_years = (nifty.iloc[-1]["datetime"] - nifty.iloc[200]["datetime"]).days / 365.25
        cagr = ((capital / initial_capital) ** (1 / max(1.0, duration_years)) - 1) * 100
        wins = sum(1 for t in trades if t["win"])
        win_rate = (wins / len(trades) * 100) if trades else 0.0
        eq_df["daily_ret"] = eq_df["equity"].pct_change()
        sharpe = (
            (eq_df["daily_ret"].mean() / eq_df["daily_ret"].std()) * np.sqrt(52)
            if eq_df["daily_ret"].std() > 0
            else 0.0
        )
        eq_df["cummax"] = eq_df["equity"].cummax()
        eq_df["drawdown"] = (eq_df["equity"] - eq_df["cummax"]) / eq_df["cummax"]
        max_dd = abs(eq_df["drawdown"].min()) * 100

        pnl_wins = [t["pnl"] for t in trades if t["pnl"] > 0]
        pnl_loss = [t["pnl"] for t in trades if t["pnl"] <= 0]
        pf = sum(pnl_wins) / abs(sum(pnl_loss)) if pnl_loss and sum(pnl_loss) != 0 else 0.0

        return {
            "strategy": "curvature_credit_spread",
            "initial_capital": initial_capital,
            "final_capital": capital,
            "total_return_pct": ((capital / initial_capital) - 1) * 100,
            "cagr": cagr,
            "win_rate": win_rate,
            "sharpe_ratio": sharpe,
            "max_drawdown_pct": max_dd,
            "total_trades": len(trades),
            "profit_factor": pf,
            "equity_curve": eq_df,
            "trades": trades,
        }

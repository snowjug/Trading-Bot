"""
High-Alpha Leader Breakout & Trend-Riding Strategy.

Designed for high return / maximum profit on Indian equities:
- Infrequent, high-conviction trades only (filters out chop and false breakouts)
- Selects Stage-2 market leaders near 52-week highs
- Enforces institutional volume expansion and strong intermediate momentum
- Rides asymmetric trend runners using an adaptive trailing Chandelier ATR stop
- Clips losses quickly via tight initial ATR stop
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional
from src.strategies.base import Strategy, SignalDirection
from src.regime.detector import RegimeState, RegimeType
from src.backtesting.cost_model import IndianCostModel, OrderType
from src.utils.logging import setup_logging

logger = setup_logging("strategies.leader_breakout")


class LeaderBreakoutStrategy(Strategy):
    """
    Strategy: High-Alpha Leader Breakout & Trailing Trend Ride

    Hypothesis:
    Equities exhibiting Stage-2 price structure (Price > 50 EMA > 200 EMA) near
    52-week / all-time highs with institutional volume confirmation and superior
    intermediate momentum generate powerful, persistent trend runners. Holding
    winners with an adaptive Chandelier trailing stop while cutting failed breakouts
    at ~1.8 ATR yields extreme profit asymmetry (Profit Factor > 2.0).
    """

    name = "leader_breakout"
    hypothesis = (
        "Market leaders in Stage-2 uptrends near 52-week highs with relative momentum "
        "and volume expansion generate persistent trend runners; adaptive trailing stops "
        "maximize profit capture while minimizing drawdown."
    )
    strategy_type = "high_alpha_momentum"
    min_data_points = 200

    def __init__(
        self,
        mom_period: int = 60,
        trail_atr: float = 2.5,
        initial_stop_atr: float = 1.8,
        breakout_period: int = 20,
        min_rsi: float = 52.0,
        max_rsi: float = 78.0,
        min_rvol: float = 1.10,
    ):
        self.mom_period = mom_period
        self.trail_atr = trail_atr
        self.initial_stop_atr = initial_stop_atr
        self.breakout_period = breakout_period
        self.min_rsi = min_rsi
        self.max_rsi = max_rsi
        self.min_rvol = min_rvol

    def generate_signals(
        self,
        df: pd.DataFrame,
        regime: RegimeState | None = None,
    ) -> pd.DataFrame:
        """
        Generate continuous signals for BacktestEngine execution.
        Holds signal=1 while the position is active until the trailing or initial stop triggers.
        """
        if not self.validate_inputs(df):
            return pd.DataFrame()

        df = df.copy().reset_index(drop=True)

        # Core indicators
        rolling_high = df["high"].rolling(self.breakout_period).max().shift(1)
        mom = df["close"].pct_change(self.mom_period)
        
        atr = (
            df["atr_14"]
            if "atr_14" in df.columns
            else (df["high"] - df["low"]).rolling(14).mean()
        )
        ema50 = (
            df["ema_50"]
            if "ema_50" in df.columns
            else df["close"].ewm(span=50, adjust=False).mean()
        )
        ema200 = (
            df["ema_200"]
            if "ema_200" in df.columns
            else df["close"].ewm(span=200, adjust=False).mean()
        )
        ath_dist = (
            df["dist_from_ath"]
            if "dist_from_ath" in df.columns
            else (df["close"] - df["close"].cummax()) / df["close"].cummax().replace(0, np.nan)
        )
        rvol = (
            df["relative_volume_20"]
            if "relative_volume_20" in df.columns
            else pd.Series(1.2, index=df.index)
        )
        rsi = (
            df["rsi_14"]
            if "rsi_14" in df.columns
            else pd.Series(60.0, index=df.index)
        )

        # Confluence filters
        cond_stage2 = (df["close"] > ema50) & (ema50 > ema200)
        cond_near_ath = ath_dist > -0.15
        cond_mom = mom > 0.08
        cond_rsi = (rsi >= self.min_rsi) & (rsi <= self.max_rsi)
        cond_vol = rvol >= self.min_rvol
        cond_bo = df["close"] > rolling_high

        # Regime gating: do not enter if regime is STRONG_BEAR
        if regime and regime.trend_regime == RegimeType.STRONG_BEAR:
            entry_trigger = pd.Series(False, index=df.index)
        else:
            entry_trigger = cond_stage2 & cond_near_ath & cond_mom & cond_rsi & cond_vol & cond_bo

        n = len(df)
        signal = np.zeros(n, dtype=int)
        confidence = np.zeros(n, dtype=float)

        in_pos = False
        highest_close = 0.0
        entry_price = 0.0

        for i in range(1, n):
            c = df.iloc[i]["close"]
            a = atr.iloc[i] if not np.isnan(atr.iloc[i]) and atr.iloc[i] > 0 else c * 0.02

            if not in_pos:
                if entry_trigger.iloc[i]:
                    in_pos = True
                    entry_price = c
                    highest_close = c
                    signal[i] = 1
                    raw_conf = 0.60 + min(0.35, float(mom.iloc[i])) if not np.isnan(mom.iloc[i]) else 0.70
                    confidence[i] = min(0.95, max(0.50, raw_conf))
            else:
                highest_close = max(highest_close, c)
                trail_stop = highest_close - (self.trail_atr * a)
                hard_stop = entry_price - (self.initial_stop_atr * a)

                # Exit check
                if c < max(trail_stop, hard_stop):
                    in_pos = False
                    signal[i] = 0
                    confidence[i] = 0.0
                else:
                    signal[i] = 1
                    raw_conf = 0.60 + min(0.35, float(mom.iloc[i])) if not np.isnan(mom.iloc[i]) else 0.70
                    confidence[i] = min(0.95, max(0.50, raw_conf))

        signals = pd.DataFrame({
            "datetime": df["datetime"],
            "signal": signal,
            "confidence": confidence,
        })
        signals["strategy"] = self.name
        return signals

    def get_parameters(self) -> dict:
        return {
            "mom_period": self.mom_period,
            "trail_atr": self.trail_atr,
            "initial_stop_atr": self.initial_stop_atr,
            "breakout_period": self.breakout_period,
            "min_rsi": self.min_rsi,
            "max_rsi": self.max_rsi,
            "min_rvol": self.min_rvol,
        }

    @staticmethod
    def simulate_universe_portfolio(
        universe_data: dict[str, pd.DataFrame],
        index_df: pd.DataFrame,
        n_positions: int = 3,
        trail_atr: float = 2.5,
        initial_stop_atr: float = 1.8,
        mom_period: int = 60,
        initial_capital: float = 1000000.0,
    ) -> dict:
        """
        Run a full cross-sectional dynamic rotation portfolio simulation
        across the entire liquid universe with Indian statutory transaction costs.
        """
        cost_model = IndianCostModel()
        pos_size_pct = 0.96 / n_positions

        # Ensure index features exist
        idx_work = index_df.copy()
        if "ema_50" not in idx_work.columns and "close" in idx_work.columns:
            idx_work["ema_50"] = idx_work["close"].ewm(span=50, adjust=False).mean()
        dates = idx_work["datetime"].sort_values().unique()

        # Prepare universe data
        prepared_universe = {}
        for sym, df in universe_data.items():
            if sym.startswith("INDEX_") or len(df) < 100:
                continue
            df_copy = df.copy()
            if "ema_50" not in df_copy.columns:
                df_copy["ema_50"] = df_copy["close"].ewm(span=50, adjust=False).mean()
            if "ema_200" not in df_copy.columns:
                df_copy["ema_200"] = df_copy["close"].ewm(span=200, adjust=False).mean()
            if f"mom_{mom_period}" not in df_copy.columns and "mom_60" not in df_copy.columns:
                df_copy["mom_60"] = df_copy["close"].pct_change(mom_period)
            if "rolling_high_20" not in df_copy.columns:
                df_copy["rolling_high_20"] = df_copy["high"].rolling(20).max().shift(1)
            if "dist_from_ath" not in df_copy.columns:
                df_copy["dist_from_ath"] = (df_copy["close"] - df_copy["close"].cummax()) / df_copy["close"].cummax().replace(0, np.nan)
            if "relative_volume_20" not in df_copy.columns and "volume" in df_copy.columns:
                df_copy["relative_volume_20"] = df_copy["volume"] / df_copy["volume"].rolling(20).mean().replace(0, np.nan)
            if "rsi_14" not in df_copy.columns:
                df_copy["rsi_14"] = 60.0
            prepared_universe[sym] = df_copy

        date_indices = {d: {} for d in dates}
        for sym, df in prepared_universe.items():
            for row in df.itertuples():
                if row.datetime in date_indices:
                    date_indices[row.datetime][sym] = row

        idx_rows = {row.datetime: row for row in idx_work.itertuples()}

        capital = initial_capital
        positions = {}
        equity_history = []
        trades = []

        for current_date in dates[250:]:
            current_idx = idx_rows.get(current_date)
            if not current_idx:
                continue
            current_stocks = date_indices.get(current_date, {})

            # 1. Update existing positions and check exits
            closed_syms = []
            for sym, pos in list(positions.items()):
                row = current_stocks.get(sym)
                if not row:
                    continue
                c = row.close
                pos["highest_close"] = max(pos["highest_close"], c)
                a = getattr(row, "atr_14", c * 0.02)
                trail_stop = pos["highest_close"] - (trail_atr * a)
                hard_stop = pos["entry_price"] - (initial_stop_atr * a)

                if c < max(trail_stop, hard_stop):
                    exec_price = c
                    proceeds = exec_price * pos["shares"]
                    cost = cost_model.compute_cost(proceeds, OrderType.DELIVERY, is_buy=False).total
                    capital += (proceeds - cost)
                    pnl = (proceeds - cost) - (pos["entry_price"] * pos["shares"])
                    trades.append({
                        "symbol": sym,
                        "entry_date": pos["entry_date"],
                        "exit_date": current_date,
                        "entry_price": pos["entry_price"],
                        "exit_price": exec_price,
                        "shares": pos["shares"],
                        "pnl": pnl,
                        "return_pct": (exec_price / pos["entry_price"] - 1) * 100,
                    })
                    closed_syms.append(sym)

            for sym in closed_syms:
                del positions[sym]

            mtm = capital + sum(
                current_stocks[s].close * p["shares"]
                for s, p in positions.items()
                if s in current_stocks
            )
            equity_history.append({"datetime": current_date, "equity": mtm})

            # 2. Check entries if capacity exists and broad market is above 50 EMA
            vacant = n_positions - len(positions)
            if vacant > 0 and current_idx.close > getattr(current_idx, "ema_50", 0):
                candidates = []
                for sym, row in current_stocks.items():
                    if sym in positions:
                        continue
                    c = row.close
                    e50 = getattr(row, "ema_50", 0)
                    e200 = getattr(row, "ema_200", 0)
                    ath_dist = getattr(row, "dist_from_ath", -1)
                    mom = getattr(row, f"mom_{mom_period}", getattr(row, "mom_60", -1))
                    rvol = getattr(row, "relative_volume_20", 0)
                    rsi = getattr(row, "rsi_14", 50)
                    rolling_h = getattr(row, "rolling_high_20", c)

                    if (
                        (c > e50 > e200)
                        and (ath_dist > -0.12)
                        and (mom > 0.08)
                        and (52 <= rsi <= 78)
                        and (rvol >= 1.10)
                        and (c > rolling_h)
                    ):
                        candidates.append((sym, mom, c))

                candidates.sort(key=lambda x: x[1], reverse=True)
                for sym, score, price in candidates[:vacant]:
                    trade_cap = mtm * pos_size_pct
                    if capital >= trade_cap and price > 0:
                        shares = int(trade_cap / price)
                        if shares > 0:
                            cost = cost_model.compute_cost(
                                price * shares, OrderType.DELIVERY, is_buy=True
                            ).total
                            if capital >= (price * shares + cost):
                                capital -= (price * shares + cost)
                                positions[sym] = {
                                    "shares": shares,
                                    "entry_price": price,
                                    "highest_close": price,
                                    "entry_date": current_date,
                                }

        eq_df = pd.DataFrame(equity_history)
        if eq_df.empty:
            return {}

        final_eq = eq_df.iloc[-1]["equity"]
        total_ret = ((final_eq / initial_capital) - 1) * 100
        duration_years = (eq_df.iloc[-1]["datetime"] - eq_df.iloc[0]["datetime"]).days / 365.25
        cagr = ((final_eq / initial_capital) ** (1 / max(1.0, duration_years)) - 1) * 100
        eq_df["daily_ret"] = eq_df["equity"].pct_change()
        sharpe = (
            (eq_df["daily_ret"].mean() / eq_df["daily_ret"].std()) * np.sqrt(252)
            if eq_df["daily_ret"].std() > 0
            else 0.0
        )
        eq_df["cummax"] = eq_df["equity"].cummax()
        eq_df["drawdown"] = (eq_df["equity"] - eq_df["cummax"]) / eq_df["cummax"]
        max_dd = abs(eq_df["drawdown"].min()) * 100

        pnl_wins = [t["pnl"] for t in trades if t["pnl"] > 0]
        pnl_loss = [t["pnl"] for t in trades if t["pnl"] <= 0]
        win_rate = (len(pnl_wins) / len(trades) * 100) if trades else 0.0
        pf = (
            sum(pnl_wins) / abs(sum(pnl_loss))
            if pnl_loss and sum(pnl_loss) != 0
            else 0.0
        )

        return {
            "initial_capital": initial_capital,
            "final_capital": final_eq,
            "total_return_pct": total_ret,
            "cagr": cagr,
            "sharpe_ratio": sharpe,
            "max_drawdown_pct": max_dd,
            "total_trades": len(trades),
            "annual_trades": len(trades) / max(1.0, duration_years),
            "win_rate": win_rate,
            "profit_factor": pf,
            "duration_years": duration_years,
            "equity_curve": eq_df,
            "trades": trades,
        }

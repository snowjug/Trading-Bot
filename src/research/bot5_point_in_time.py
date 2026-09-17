"""
Bot 5 (ActiveMomentumOptionScalperStrategy) — point-in-time research correction.

WHY THIS MODULE EXISTS
----------------------
The original `generate_signals` / `run_single_simulation` contain SAME-BAR
LEAKAGE: three inputs to the day-i entry decision are only knowable after day i
has closed, yet the simulator enters during day i and harvests day i's intrabar
range.

This module reproduces the strategy with a causal chronology. It is ADDITIVE:
`src/strategies/active_momentum_scalper.py` is left untouched so the original
(contaminated) result remains reproducible as evidence.

WHAT WAS CHANGED, AND THE JUSTIFICATION FOR EACH
------------------------------------------------
Nothing here is a parameter change. Every threshold, buffer, multiple and cost
is taken verbatim from the strategy instance. Only the BAR from which three
values are read is corrected:

  ema_20  row -> prev   Justified by the strategy's OWN documentation:
                        "Today's Open > 20 EMA". At today's open the only 20-EMA
                        in existence is the one computed to the previous close.
                        The code read row["ema_20"], which embeds today's close.

  rsi_14  row -> prev   The docstring says only "RSI >= 50" without naming a bar.
                        row["rsi_14"] embeds today's close, so it cannot inform a
                        decision taken during day i. prev is the only causal
                        choice. (Leakage removal, not a redefinition.)

  atr_14  row -> prev   ATR sizes the target/stop AT ENTRY. row["atr_14"] embeds
                        day i's own high/low/close, i.e. the very range the trade
                        is about to experience.

WHAT WAS DELIBERATELY NOT CHANGED
---------------------------------
  * The breakout trigger `high > prev_high x (1 + buffer)` stays on the CURRENT
    bar. It is a crossing EVENT observable in real time and uses no future data.
  * Entry level `prev["high"] x (1 + buffer)` was already causal.
  * Intrabar high/low/close still resolve the EXIT, which is correct: the trade
    is already open, so its subsequent path is legitimately consultable.
  * The strategy remains INTRADAY (docstring rule 4: "Intraday MIS, Mandatory
    03:15 PM Exit"). It is NOT deferred to bar i+1, because the documented intent
    is an intraday breakout, not a next-day entry.

NOT MODELLED (inherited from the original research, unchanged here):
option premium is a flat 100.0 with a fixed 0.55 delta proxy — no option chain,
no strike, no expiry, no bid/ask. P&L below is therefore a SPOT-DELTA PROXY, not
real option P&L, and is labelled as such in the result.
"""

import os
import sys
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.strategies.active_momentum_scalper import ActiveMomentumOptionScalperStrategy
from src.utils.logging import setup_logging

logger = setup_logging("research.bot5_pit")

#: Fields that the original implementation read from the CURRENT bar even though
#: their value is only final after that bar closes.
LEAKED_FIELDS = ("ema_20", "rsi_14", "atr_14")


def generate_signals_point_in_time(
    strategy: ActiveMomentumOptionScalperStrategy,
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Causal reimplementation of `generate_signals`.

    Every filter is evaluated on information available BEFORE day i's close; the
    only current-bar input is the breakout crossing, which is observable live.
    """
    if not strategy.validate_inputs(df):
        return pd.DataFrame()

    calc = strategy.compute_indicators(df)
    signals: List[int] = []
    confidences: List[float] = []

    for i in range(len(calc)):
        if i < 25:
            signals.append(0)
            confidences.append(0.0)
            continue

        row = calc.iloc[i]
        prev = calc.iloc[i - 1]

        # Causal filters — all from the settled previous bar, except today's OPEN
        # (known at 09:15) and the breakout, which is a live crossing event.
        is_ce = (
            prev["close"] > prev["ema_9"]
            and row["open"] > prev["ema_20"]
            and row["high"] > prev["high"] * (1.0 + strategy.breakout_buffer)
            and prev["rsi_14"] >= 50.0
        )
        is_pe = (
            prev["close"] < prev["ema_9"]
            and row["open"] < prev["ema_20"]
            and row["low"] < prev["low"] * (1.0 - strategy.breakout_buffer)
            and prev["rsi_14"] <= 50.0
        )

        if is_ce:
            signals.append(1)
            confidences.append(0.75)
        elif is_pe:
            signals.append(-1)
            confidences.append(0.75)
        else:
            signals.append(0)
            confidences.append(0.0)

    out = pd.DataFrame({
        "datetime": calc["datetime"],
        "signal": signals,
        "confidence": confidences,
    })
    out["strategy"] = strategy.name + "_point_in_time"
    return out


def run_point_in_time_simulation(
    strategy: ActiveMomentumOptionScalperStrategy,
    df: pd.DataFrame,
    symbol: str = "NIFTY",
    lot_default: int = 50,
) -> List[Dict[str, Any]]:
    """
    Causal reimplementation of `run_single_simulation`.

    Identical trade mechanics and identical parameters; the target/stop are sized
    from the PREVIOUS bar's ATR because that is what is known at entry.
    """
    calc = strategy.compute_indicators(df)
    sig_df = generate_signals_point_in_time(strategy, df)
    if sig_df.empty:
        return []
    merged = pd.merge(calc, sig_df[["datetime", "signal"]], on="datetime")

    trades: List[Dict[str, Any]] = []
    for i in range(25, len(merged)):
        row = merged.iloc[i]
        prev = merged.iloc[i - 1]
        sig = row["signal"]
        if sig == 0:
            continue

        # Sizing uses the PREVIOUS bar's ATR — known at entry.
        atr = prev["atr_14"]
        if not np.isfinite(atr) or atr <= 0:
            continue

        date, close, high, low = row["datetime"], row["close"], row["high"], row["low"]
        is_ce = sig == 1
        entry_spot = (
            prev["high"] * (1.0 + strategy.breakout_buffer) if is_ce
            else prev["low"] * (1.0 - strategy.breakout_buffer)
        )
        lot_size = lot_default if date.year < 2024 else max(15, int(lot_default / 2))

        target_pts = strategy.target_atr_mult * atr
        stop_pts = strategy.stop_atr_mult * atr
        opt_delta = 0.55
        target_opt = target_pts * opt_delta
        stop_opt = stop_pts * opt_delta

        if is_ce:
            max_fav_pts = high - entry_spot
            max_adv_pts = entry_spot - low
            close_pts = close - entry_spot
        else:
            max_fav_pts = entry_spot - low
            max_adv_pts = high - entry_spot
            close_pts = entry_spot - close

        # Exit resolution over the bar the position is ALREADY open in.
        if max_adv_pts >= stop_pts and max_fav_pts < (0.25 * atr):
            opt_pnl, hit = -stop_opt, "STOP"
            spot_exit = entry_spot - stop_pts if is_ce else entry_spot + stop_pts
        elif max_fav_pts >= target_pts:
            opt_pnl, hit = target_opt, "TARGET"
            spot_exit = entry_spot + target_pts if is_ce else entry_spot - target_pts
        else:
            opt_pnl = max(-stop_opt, min(target_opt, close_pts * opt_delta))
            hit, spot_exit = "EOD", close

        gross_pnl = opt_pnl * lot_size
        net_pnl = gross_pnl - strategy.friction_per_trade

        trades.append({
            "date": date, "symbol": symbol,
            "option_type": "CE" if is_ce else "PE",
            "spot_entry": float(entry_spot), "spot_exit": float(spot_exit),
            "option_entry_prem": 100.0,               # proxy, inherited unchanged
            "option_exit_prem": max(0.5, 100.0 + opt_pnl),
            "gross_pnl": float(gross_pnl), "net_pnl": float(net_pnl),
            "return_pct": float((opt_pnl / 100.0) * 100.0),
            "win": net_pnl > 0, "exit_reason": hit,
            "pricing_basis": "SPOT_DELTA_PROXY_NOT_REAL_OPTION",
        })
    return trades


def summarise(trades: List[Dict[str, Any]], initial_capital: float) -> Dict[str, Any]:
    """Aggregates a trade list into comparison metrics (no optimisation)."""
    if not trades:
        return {
            "total_trades": 0, "win_rate": 0.0, "net_profit": 0.0,
            "final_capital": initial_capital, "max_drawdown_pct": 0.0,
            "gross_profit": 0.0, "total_friction": 0.0, "trades_per_week": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0, "turnover_notional": 0.0,
        }

    tdf = pd.DataFrame(sorted(trades, key=lambda t: t["date"]))
    equity = initial_capital + tdf["net_pnl"].cumsum()
    peak = equity.cummax()
    dd = ((equity - peak) / peak).min()

    wins = tdf[tdf["net_pnl"] > 0]["net_pnl"]
    losses = tdf[tdf["net_pnl"] <= 0]["net_pnl"]
    weeks = max(1.0, (tdf["date"].max() - tdf["date"].min()).days / 7.0)

    return {
        "total_trades": int(len(tdf)),
        "win_rate": float((tdf["net_pnl"] > 0).mean() * 100.0),
        "net_profit": float(tdf["net_pnl"].sum()),
        "final_capital": float(initial_capital + tdf["net_pnl"].sum()),
        "max_drawdown_pct": float(abs(dd) * 100.0) if pd.notna(dd) else 0.0,
        "gross_profit": float(tdf["gross_pnl"].sum()),
        "total_friction": float(len(tdf) * 45.0),
        "trades_per_week": float(len(tdf) / weeks),
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
        "turnover_notional": float((tdf["spot_entry"] * 1.0).sum()),
    }

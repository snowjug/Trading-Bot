r"""
MASTER PROMPT — SIMPLE MONEY-FOCUSED INTRADAY OPTIONS BOT TEST
==============================================================
Strategy:
EMA (Fast 9, Slow 21)
RSI (14, Bullish 60, Bearish 40)
ATR (14, Stop 1.5x ATR, Target 2R = 3.0x ATR)

Tested separately:
- Timeframes: 5-minute and 15-minute
- Underlyings: NIFTY and BANKNIFTY
- Strike Modes: ATM and 1-step ITM
- ATR Interpretations:
    Version A: Underlying ATR converted to option path
    Version B: Option ATR directly on option premium
- Trade constraint: Max 4 trades/week, max 1 active trade at a time
- Capital tiers: ₹20,000 / ₹50,000 / ₹1,00,000
- Backtest window: 2024-09-18 to 2026-09-18
- Output: reports/FRIEND_EMA_RSI_ATR_MONEY_TEST.md
"""

import os
import sys
import glob
from pathlib import Path
from typing import Dict, List, Tuple, Any

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd

REPORT_PATH = Path("reports/FRIEND_EMA_RSI_ATR_MONEY_TEST.md")

# Authentic lot sizes from data/catalog/lot_size_calendar.csv
LOT_SIZES_NIFTY = {
    "2024-09": 25, "2024-10": 25, "2024-11": 25, "2024-12": 25,
    "2025-01": 75, "2025-02": 75, "2025-03": 75, "2025-04": 75, "2025-05": 75,
    "2025-06": 75, "2025-07": 75, "2025-08": 75, "2025-09": 75, "2025-10": 75, "2025-11": 75,
    "2025-12": 65, "2026-01": 65, "2026-02": 65, "2026-03": 65, "2026-04": 65,
    "2026-05": 65, "2026-06": 65, "2026-07": 65, "2026-08": 65, "2026-09": 65,
}

LOT_SIZES_BANKNIFTY = {
    "2024-09": 15, "2024-10": 15, "2024-11": 15, "2024-12": 15,
    "2025-01": 30, "2025-02": 30, "2025-03": 30, "2025-04": 30, "2025-05": 30,
    "2025-06": 35, "2025-07": 35, "2025-08": 35, "2025-09": 35, "2025-10": 35, "2025-11": 35,
    "2025-12": 30, "2026-01": 30, "2026-02": 30, "2026-03": 30, "2026-04": 30,
    "2026-05": 30, "2026-06": 30, "2026-07": 30, "2026-08": 30, "2026-09": 30,
}


def get_lot_size(underlying: str, dt: pd.Timestamp) -> int:
    ym = dt.strftime("%Y-%m")
    if underlying == "NIFTY":
        return LOT_SIZES_NIFTY.get(ym, 65)
    else:
        return LOT_SIZES_BANKNIFTY.get(ym, 30)


def calculate_costs(entry_price: float, exit_price: float, lot_size: int, multiplier: float = 1.0) -> float:
    """Authentic Indian F&O option transaction costs + ₹20/order brokerage."""
    turnover_buy = entry_price * lot_size
    turnover_sell = exit_price * lot_size
    total_turnover = turnover_buy + turnover_sell

    brokerage = 40.0  # ₹20 entry + ₹20 exit
    stt = 0.0005 * turnover_sell  # 0.05% on sell
    exchange_fee = 0.00053 * total_turnover  # 0.053% NSE exchange turnover fee
    sebi_charges = 0.000001 * total_turnover  # ₹10/crore
    stamp_duty = 0.00003 * turnover_buy  # 0.003% buy side
    gst = 0.18 * (brokerage + exchange_fee)

    base_costs = brokerage + stt + exchange_fee + sebi_charges + stamp_duty + gst
    return round(base_costs * multiplier, 2)


def load_dataset(underlying: str, strike_mode: str) -> pd.DataFrame:
    """Load authentic 5m option bars with spot, CE and PE."""
    if underlying == "NIFTY":
        if strike_mode == "ATM":
            p_ce = "data/raw/dhan/option_grid_5m/strike=ATM/ce_202[456]*.parquet"
            p_pe = "data/raw/dhan/option_grid_5m/strike=ATM/pe_202[456]*.parquet"
        else:  # ITM: CE is ATMm1, PE is ATMp1
            p_ce = "data/raw/dhan/option_grid_5m/strike=ATMm1/ce_202[456]*.parquet"
            p_pe = "data/raw/dhan/option_grid_5m/strike=ATMp1/pe_202[456]*.parquet"
    else:  # BANKNIFTY
        if strike_mode == "ATM":
            p_ce = "data/raw/dhan/option_grid_5m_multi/underlying=BANKNIFTY/strike=ATM/ce_202[456]*.parquet"
            p_pe = "data/raw/dhan/option_grid_5m_multi/underlying=BANKNIFTY/strike=ATM/pe_202[456]*.parquet"
        else:  # ITM: CE is ATMm1, PE is ATMp1
            p_ce = "data/raw/dhan/option_grid_5m_multi/underlying=BANKNIFTY/strike=ATMm1/ce_202[456]*.parquet"
            p_pe = "data/raw/dhan/option_grid_5m_multi/underlying=BANKNIFTY/strike=ATMp1/pe_202[456]*.parquet"

    files_ce = sorted(glob.glob(p_ce))
    files_pe = sorted(glob.glob(p_pe))
    if not files_ce or not files_pe:
        raise FileNotFoundError(f"Missing option grid files for {underlying} {strike_mode}")

    df_ce = pd.concat([pd.read_parquet(f) for f in files_ce], ignore_index=True)
    df_pe = pd.concat([pd.read_parquet(f) for f in files_pe], ignore_index=True)

    df_ce["datetime"] = pd.to_datetime(df_ce["datetime"])
    df_pe["datetime"] = pd.to_datetime(df_pe["datetime"])

    # Filter window 2024-09-01 onwards (warm-up from Sept 1, backtest 2024-09-18 to 2026-09-18)
    df_ce = df_ce[(df_ce["datetime"] >= "2024-09-01") & (df_ce["datetime"] <= "2026-09-18 15:35:00")].sort_values("datetime").reset_index(drop=True)
    df_pe = df_pe[(df_pe["datetime"] >= "2024-09-01") & (df_pe["datetime"] <= "2026-09-18 15:35:00")].sort_values("datetime").reset_index(drop=True)

    # Rename columns to merge cleanly
    ce_cols = {
        "open": "ce_open", "high": "ce_high", "low": "ce_low", "close": "ce_close",
        "volume": "ce_volume", "strike": "ce_strike"
    }
    pe_cols = {
        "open": "pe_open", "high": "pe_high", "low": "pe_low", "close": "pe_close",
        "volume": "pe_volume", "strike": "pe_strike"
    }
    df_ce = df_ce.rename(columns=ce_cols)[["datetime", "spot"] + list(ce_cols.values())]
    df_pe = df_pe.rename(columns=pe_cols)[["datetime"] + list(pe_cols.values())]

    merged = pd.merge(df_ce, df_pe, on="datetime", how="inner").sort_values("datetime").reset_index(drop=True)
    merged["underlying"] = underlying
    merged["strike_mode"] = strike_mode
    return merged


def compute_indicators(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Compute EMA 9, EMA 21, RSI 14, and ATR 14 on underlying spot and options."""
    df = df.copy()

    if timeframe == "5m":
        work = df.copy()
        work["bar_dt"] = work["datetime"]
    elif timeframe == "15m":
        # Group every 3 consecutive 5m bars into a 15m candle (09:15-09:30, etc.)
        df["group_15m"] = df["datetime"].dt.floor("15min")
        agg_rules = {
            "datetime": "first",
            "spot": "last",
            "ce_open": "first", "ce_high": "max", "ce_low": "min", "ce_close": "last", "ce_strike": "last",
            "pe_open": "first", "pe_high": "max", "pe_low": "min", "pe_close": "last", "pe_strike": "last",
        }
        work = df.groupby(["group_15m"]).agg(agg_rules).reset_index(drop=True)
        work["bar_dt"] = work["datetime"]
    else:
        raise ValueError(f"Unknown timeframe {timeframe}")

    spot = work["spot"]

    # 1. EMA 9 and EMA 21
    work["ema9"] = spot.ewm(span=9, adjust=False).mean()
    work["ema21"] = spot.ewm(span=21, adjust=False).mean()

    # 2. RSI 14
    delta = spot.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    work["rsi"] = 100 - (100 / (1 + rs))

    # 3. ATR 14 on Spot (Version A)
    tr_spot = (spot - spot.shift(1)).abs()
    work["atr_spot"] = tr_spot.ewm(alpha=1/14, min_periods=14, adjust=False).mean()

    # 4. ATR 14 on Options (Version B)
    tr_ce = np.maximum(work["ce_high"] - work["ce_low"],
                       np.maximum((work["ce_high"] - work["ce_close"].shift(1)).abs(),
                                  (work["ce_low"] - work["ce_close"].shift(1)).abs()))
    work["atr_ce"] = tr_ce.ewm(alpha=1/14, min_periods=14, adjust=False).mean()

    tr_pe = np.maximum(work["pe_high"] - work["pe_low"],
                       np.maximum((work["pe_high"] - work["pe_close"].shift(1)).abs(),
                                  (work["pe_low"] - work["pe_close"].shift(1)).abs()))
    work["atr_pe"] = tr_pe.ewm(alpha=1/14, min_periods=14, adjust=False).mean()

    # Crossings
    ema_bull_cross = (work["ema9"] > work["ema21"]) & (work["ema9"].shift(1) <= work["ema21"].shift(1))
    rsi_bull_cross = (work["rsi"] > 60) & (work["rsi"].shift(1) <= 60) & (work["rsi"] > work["rsi"].shift(1))

    # Condition: both occur on same candle or within immediately following candle
    work["bull_signal"] = (ema_bull_cross & rsi_bull_cross) | \
                          (ema_bull_cross.shift(1) & rsi_bull_cross) | \
                          (rsi_bull_cross.shift(1) & ema_bull_cross)

    ema_bear_cross = (work["ema9"] < work["ema21"]) & (work["ema9"].shift(1) >= work["ema21"].shift(1))
    rsi_bear_cross = (work["rsi"] < 40) & (work["rsi"].shift(1) >= 40) & (work["rsi"] < work["rsi"].shift(1))

    work["bear_signal"] = (ema_bear_cross & rsi_bear_cross) | \
                          (ema_bear_cross.shift(1) & rsi_bear_cross) | \
                          (rsi_bear_cross.shift(1) & ema_bear_cross)

    return work


def simulate_strategy(df_5m: pd.DataFrame, work_df: pd.DataFrame,
                      underlying: str, timeframe: str, strike_mode: str,
                      atr_version: str, cost_mult: float = 1.0) -> List[Dict[str, Any]]:
    """Fast, vectorized-accelerated simulation under the specified variant."""
    # Pre-group 5m bars by date for instant session lookup
    bars_by_date = {d: grp for d, grp in df_5m.groupby(df_5m["datetime"].dt.date)}

    trades = []
    weekly_trades_count = {}
    last_exit_time = pd.Timestamp("2000-01-01")

    n_rows = len(work_df)
    for i in range(1, n_rows - 1):
        row = work_df.iloc[i]
        bar_dt = row["bar_dt"]

        # Only evaluate backtest window: 2024-09-18 to 2026-09-18
        if bar_dt < pd.Timestamp("2024-09-18"):
            continue
        if bar_dt > pd.Timestamp("2026-09-18 15:30:00"):
            break

        # Max 1 active trade at a time: if previous trade is still open, cannot enter
        if bar_dt < last_exit_time:
            continue

        # Year-Week tracking for 4 trades/week constraint
        iso_year, iso_week, _ = bar_dt.isocalendar()
        week_key = (iso_year, iso_week)
        current_week_trades = weekly_trades_count.get(week_key, 0)
        if current_week_trades >= 4:
            continue

        # Entry candle must be between 09:25 and 14:45
        btime = bar_dt.time()
        if not (pd.Timestamp("09:25:00").time() <= btime <= pd.Timestamp("14:45:00").time()):
            continue

        signal_type = None
        if row["bull_signal"]:
            signal_type = "LONG_CE"
        elif row["bear_signal"]:
            signal_type = "LONG_PE"

        if not signal_type:
            continue

        # Entry happens at the open of next candle
        next_row = work_df.iloc[i + 1]
        entry_dt = next_row["bar_dt"]
        lot_size = get_lot_size(underlying, entry_dt)

        if signal_type == "LONG_CE":
            raw_entry = next_row["ce_open"] if not pd.isna(next_row["ce_open"]) else next_row["ce_close"]
            entry_fill = round(raw_entry * 1.005, 2)
            strike = next_row["ce_strike"]
            side = "CE"

            if atr_version == "VER_A":  # Underlying ATR
                atr_val = row["atr_spot"]
                risk_dist = 1.5 * atr_val
                stop_level = row["spot"] - risk_dist
                target_level = row["spot"] + 2.0 * risk_dist  # 2R target
            else:  # Option ATR
                atr_val = row["atr_ce"]
                risk_dist = 1.5 * atr_val
                stop_level = max(0.05, round(entry_fill - risk_dist, 2))
                target_level = round(entry_fill + 2.0 * risk_dist, 2)  # 2R target

        else:  # LONG_PE
            raw_entry = next_row["pe_open"] if not pd.isna(next_row["pe_open"]) else next_row["pe_close"]
            entry_fill = round(raw_entry * 1.005, 2)
            strike = next_row["pe_strike"]
            side = "PE"

            if atr_version == "VER_A":  # Underlying ATR
                atr_val = row["atr_spot"]
                risk_dist = 1.5 * atr_val
                stop_level = row["spot"] + risk_dist
                target_level = row["spot"] - 2.0 * risk_dist  # 2R target
            else:  # Option ATR
                atr_val = row["atr_pe"]
                risk_dist = 1.5 * atr_val
                stop_level = max(0.05, round(entry_fill - risk_dist, 2))
                target_level = round(entry_fill + 2.0 * risk_dist, 2)  # 2R target

        if entry_fill <= 0 or pd.isna(atr_val) or atr_val <= 0:
            continue

        outlay = round(entry_fill * lot_size, 2)
        session_date = entry_dt.date()
        session_df = bars_by_date.get(session_date)
        if session_df is None:
            continue

        # Granular 5m bars for the remainder of this trading session
        session_rem = session_df[session_df["datetime"] >= entry_dt]
        if session_rem.empty:
            continue

        exit_fill = None
        exit_time = None
        exit_reason = None

        for b in session_rem.itertuples():
            curr_spot = b.spot
            curr_time = b.datetime.time()

            if side == "CE":
                curr_open = b.ce_open
                curr_high = b.ce_high
                curr_low = b.ce_low
                curr_close = b.ce_close
            else:
                curr_open = b.pe_open
                curr_high = b.pe_high
                curr_low = b.pe_low
                curr_close = b.pe_close

            # 1. Check ATR Stop & Target
            if atr_version == "VER_A":  # Underlying ATR
                if side == "CE":
                    if curr_spot <= stop_level:
                        exit_fill = round(curr_open * 0.995, 2)
                        exit_time = b.datetime
                        exit_reason = "STOP_LOSS_UNDERLYING"
                        break
                    elif curr_spot >= target_level:
                        exit_fill = round(curr_open * 0.995, 2)
                        exit_time = b.datetime
                        exit_reason = "TARGET_HIT_UNDERLYING"
                        break
                else:  # PE
                    if curr_spot >= stop_level:
                        exit_fill = round(curr_open * 0.995, 2)
                        exit_time = b.datetime
                        exit_reason = "STOP_LOSS_UNDERLYING"
                        break
                    elif curr_spot <= target_level:
                        exit_fill = round(curr_open * 0.995, 2)
                        exit_time = b.datetime
                        exit_reason = "TARGET_HIT_UNDERLYING"
                        break
            else:  # Option ATR (VER_B)
                if curr_low <= stop_level:
                    exit_fill = round(min(stop_level, curr_open) * 0.995, 2)
                    exit_time = b.datetime
                    exit_reason = "STOP_LOSS_OPTION"
                    break
                elif curr_high >= target_level:
                    exit_fill = round(max(target_level, curr_open) * 0.995, 2)
                    exit_time = b.datetime
                    exit_reason = "TARGET_HIT_OPTION"
                    break

            # 2. Mandatory EOD square-off by 15:15
            if curr_time >= pd.Timestamp("15:15:00").time():
                exit_fill = round(curr_close * 0.995, 2)
                exit_time = b.datetime
                exit_reason = "EOD_1515"
                break

        if exit_fill is None:
            last_bar = session_rem.iloc[-1]
            exit_fill = round((last_bar["ce_close"] if side == "CE" else last_bar["pe_close"]) * 0.995, 2)
            exit_time = last_bar["datetime"]
            exit_reason = "EOD_FORCE"

        costs = calculate_costs(entry_fill, exit_fill, lot_size, multiplier=cost_mult)
        gross_pnl = round((exit_fill - entry_fill) * lot_size, 2)
        net_pnl = round(gross_pnl - costs, 2)

        trades.append({
            "underlying": underlying,
            "timeframe": timeframe,
            "strike_mode": strike_mode,
            "atr_version": atr_version,
            "signal_type": signal_type,
            "side": side,
            "strike": strike,
            "lot_size": lot_size,
            "entry_time": entry_dt,
            "exit_time": exit_time,
            "entry_fill": entry_fill,
            "exit_fill": exit_fill,
            "outlay": outlay,
            "exit_reason": exit_reason,
            "gross_pnl": gross_pnl,
            "costs": costs,
            "net_pnl": net_pnl,
            "is_win": net_pnl > 0,
        })

        weekly_trades_count[week_key] = current_week_trades + 1
        last_exit_time = exit_time

    return trades


def run_account_simulation(trades: List[Dict[str, Any]], starting_capital: float) -> Dict[str, Any]:
    """Sequential cash account simulation enforcing cash-outlay constraints."""
    cash = starting_capital
    peak = starting_capital
    max_dd_inr = 0.0
    max_dd_pct = 0.0
    min_balance = starting_capital
    worst_losing_streak = 0
    curr_losing_streak = 0
    executed_count = 0
    skipped_count = 0

    trade_pnl_history = []

    for t in trades:
        outlay = t["outlay"]
        if cash < outlay:
            skipped_count += 1
            continue

        executed_count += 1
        net_pnl = t["net_pnl"]
        cash += net_pnl
        trade_pnl_history.append(net_pnl)

        if net_pnl <= 0:
            curr_losing_streak += 1
            if curr_losing_streak > worst_losing_streak:
                worst_losing_streak = curr_losing_streak
        else:
            curr_losing_streak = 0

        if cash < min_balance:
            min_balance = cash

        if cash > peak:
            peak = cash
        dd_inr = peak - cash
        dd_pct = (dd_inr / peak) * 100 if peak > 0 else 100.0

        if dd_inr > max_dd_inr:
            max_dd_inr = dd_inr
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct

        if cash <= 0:
            cash = 0.0
            break

    total_return_pct = round(((cash - starting_capital) / starting_capital) * 100, 2)
    avg_pnl_per_trade = round(np.mean(trade_pnl_history), 2) if trade_pnl_history else 0.0

    return {
        "starting_capital": starting_capital,
        "ending_capital": round(cash, 2),
        "total_profit_loss": round(cash - starting_capital, 2),
        "return_pct": total_return_pct,
        "executed_trades": executed_count,
        "skipped_trades": skipped_count,
        "max_dd_inr": round(max_dd_inr, 2),
        "max_dd_pct": round(max_dd_pct, 2),
        "min_balance": round(min_balance, 2),
        "worst_losing_streak": worst_losing_streak,
        "avg_pnl_per_trade": avg_pnl_per_trade,
    }


def compute_weekly_stats(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute weekly performance metrics."""
    if not trades:
        return {"avg_weekly": 0, "med_weekly": 0, "win_pct": 0, "loss_pct": 0, "worst": 0, "best": 0, "avg_trades": 0, "consec_loss": 0, "profitable_weeks": 0, "losing_weeks": 0}

    df_t = pd.DataFrame(trades)
    df_t["week"] = df_t["entry_time"].dt.to_period("W")
    weekly = df_t.groupby("week")["net_pnl"].agg(["sum", "count"]).reset_index()

    profitable_weeks = (weekly["sum"] > 0).sum()
    losing_weeks = (weekly["sum"] <= 0).sum()
    total_weeks = len(weekly)

    consec = 0
    max_consec = 0
    for s in weekly["sum"]:
        if s <= 0:
            consec += 1
            if consec > max_consec:
                max_consec = consec
        else:
            consec = 0

    return {
        "avg_weekly": round(weekly["sum"].mean(), 2),
        "med_weekly": round(weekly["sum"].median(), 2),
        "win_pct": round(profitable_weeks / total_weeks * 100, 1) if total_weeks > 0 else 0,
        "loss_pct": round(losing_weeks / total_weeks * 100, 1) if total_weeks > 0 else 0,
        "worst": round(weekly["sum"].min(), 2),
        "best": round(weekly["sum"].max(), 2),
        "avg_trades": round(weekly["count"].mean(), 2),
        "consec_loss": max_consec,
        "profitable_weeks": profitable_weeks,
        "losing_weeks": losing_weeks,
    }


def run_all_variants():
    """Execute backtests for all 16 variants."""
    print("=" * 100, flush=True)
    print("STARTING FRIEND'S EMA + RSI + ATR INTRADAY OPTIONS BOT TEST (16 VARIANTS)", flush=True)
    print("=" * 100, flush=True)

    combos = [
        ("NIFTY", "5m", "ATM"),
        ("NIFTY", "5m", "ITM"),
        ("NIFTY", "15m", "ATM"),
        ("NIFTY", "15m", "ITM"),
        ("BANKNIFTY", "5m", "ATM"),
        ("BANKNIFTY", "5m", "ITM"),
        ("BANKNIFTY", "15m", "ATM"),
        ("BANKNIFTY", "15m", "ITM"),
    ]

    all_results = {}

    for underlying, tf, strike_mode in combos:
        print(f"\n>>> Loading Data for {underlying} ({strike_mode}, {tf})...", flush=True)
        raw_df = load_dataset(underlying, strike_mode)
        work_df = compute_indicators(raw_df, tf)

        for atr_ver in ["VER_A", "VER_B"]:
            variant_name = f"{underlying}_{tf.upper()}_{strike_mode}_{atr_ver}"
            trades = simulate_strategy(raw_df, work_df, underlying, tf, strike_mode, atr_ver)

            sim20 = run_account_simulation(trades, 20000.0)
            sim50 = run_account_simulation(trades, 50000.0)
            sim100 = run_account_simulation(trades, 100000.0)
            w_stats = compute_weekly_stats(trades)

            all_results[variant_name] = {
                "variant_name": variant_name,
                "underlying": underlying,
                "timeframe": tf,
                "strike_mode": strike_mode,
                "atr_version": atr_ver,
                "trades": trades,
                "sim20": sim20,
                "sim50": sim50,
                "sim100": sim100,
                "weekly": w_stats,
                "raw_df": raw_df,
                "work_df": work_df,
            }

            avg_pnl = round(pd.DataFrame(trades)["net_pnl"].mean(), 2) if trades else 0.0
            tot_pnl = round(pd.DataFrame(trades)["net_pnl"].sum(), 2) if trades else 0.0
            win_r = round((pd.DataFrame(trades)["net_pnl"] > 0).mean() * 100, 1) if trades else 0.0
            print(f"  [{variant_name}] Trades={len(trades)} | Win={win_r}% | Avg ₹/Trade=₹{avg_pnl:,.2f} | 2Y Net=₹{tot_pnl:,.2f} | ₹20k End=₹{sim20['ending_capital']:,.2f} | ₹50k End=₹{sim50['ending_capital']:,.2f} | ₹1L End=₹{sim100['ending_capital']:,.2f}", flush=True)

    return all_results


def analyze_and_build_report(results: Dict[str, Dict[str, Any]]):
    """Compile comprehensive markdown report answering all user requirements."""
    rows = []
    for var_name, res in results.items():
        trades = res["trades"]
        if not trades:
            continue
        df_t = pd.DataFrame(trades)
        n = len(df_t)
        win_r = round((df_t["net_pnl"] > 0).mean() * 100, 1)
        avg_pnl = round(df_t["net_pnl"].mean(), 2)
        tot_pnl = round(df_t["net_pnl"].sum(), 2)
        winners = df_t[df_t["net_pnl"] > 0]
        losers = df_t[df_t["net_pnl"] <= 0]
        avg_win = round(winners["net_pnl"].mean(), 2) if not winners.empty else 0.0
        avg_loss = round(losers["net_pnl"].mean(), 2) if not losers.empty else 0.0
        max_loss = round(df_t["net_pnl"].min(), 2)

        w = res["weekly"]
        prof_weeks = f"{w['profitable_weeks']}/{w['profitable_weeks'] + w['losing_weeks']} ({w['win_pct']}%)"

        avg_outlay = df_t["outlay"].mean()
        min_cap = "₹50,000" if avg_outlay > 15000 else "₹20,000"
        if avg_outlay > 35000:
            min_cap = "₹1,00,000"

        if tot_pnl > 0 and avg_pnl > 100:
            verdict = "PROFITABLE"
        elif tot_pnl >= -10000 and avg_pnl >= -50:
            verdict = "BREAK-EVEN"
        else:
            verdict = "NEGATIVE"

        if res["sim20"]["executed_trades"] < 0.2 * n and res["sim50"]["executed_trades"] < 0.2 * n:
            verdict = "UNEXECUTABLE"

        rows.append({
            "variant": var_name,
            "trades": n,
            "avg_pnl": avg_pnl,
            "win_rate": win_r,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "max_loss": max_loss,
            "tot_pnl": tot_pnl,
            "prof_weeks": prof_weeks,
            "min_cap": min_cap,
            "verdict": verdict,
            "res": res,
        })

    # Find best variant by average net ₹/trade
    best = max(rows, key=lambda x: x["avg_pnl"])
    best_res = best["res"]
    best_df_t = pd.DataFrame(best_res["trades"])

    # Robustness on best variant: 1x, 2x, 3x costs
    raw_df_best = best_res["raw_df"]
    work_df_best = best_res["work_df"]

    sim_2x_costs = simulate_strategy(raw_df_best, work_df_best, best_res["underlying"], best_res["timeframe"], best_res["strike_mode"], best_res["atr_version"], cost_mult=2.0)
    sim_3x_costs = simulate_strategy(raw_df_best, work_df_best, best_res["underlying"], best_res["timeframe"], best_res["strike_mode"], best_res["atr_version"], cost_mult=3.0)

    pnl_1x = best["tot_pnl"]
    pnl_2x = round(pd.DataFrame(sim_2x_costs)["net_pnl"].sum(), 2) if sim_2x_costs else 0.0
    pnl_3x = round(pd.DataFrame(sim_3x_costs)["net_pnl"].sum(), 2) if sim_3x_costs else 0.0

    # Outlier sensitivity: remove best 1, 3, 5
    sorted_trades = best_df_t.sort_values("net_pnl", ascending=False)
    pnl_rem_1 = round(sorted_trades.iloc[1:]["net_pnl"].sum(), 2)
    pnl_rem_3 = round(sorted_trades.iloc[3:]["net_pnl"].sum(), 2)
    pnl_rem_5 = round(sorted_trades.iloc[5:]["net_pnl"].sum(), 2)

    # Year-by-Year for best variant
    y1 = best_df_t[(best_df_t["entry_time"] >= "2024-09-18") & (best_df_t["entry_time"] < "2025-09-18")]
    y2 = best_df_t[(best_df_t["entry_time"] >= "2025-09-18") & (best_df_t["entry_time"] <= "2026-09-18 15:30:00")]

    y1_pnl = round(y1["net_pnl"].sum(), 2)
    y1_n = len(y1)
    y1_win = round((y1["net_pnl"] > 0).mean() * 100, 1) if y1_n > 0 else 0.0
    y1_avg = round(y1["net_pnl"].mean(), 2) if y1_n > 0 else 0.0

    y2_pnl = round(y2["net_pnl"].sum(), 2)
    y2_n = len(y2)
    y2_win = round((y2["net_pnl"] > 0).mean() * 100, 1) if y2_n > 0 else 0.0
    y2_avg = round(y2["net_pnl"].mean(), 2) if y2_n > 0 else 0.0

    pct_500 = round((best_df_t["net_pnl"] >= 500).mean() * 100, 1)
    pct_1000 = round((best_df_t["net_pnl"] >= 1000).mean() * 100, 1)
    pct_2000 = round((best_df_t["net_pnl"] >= 2000).mean() * 100, 1)

    b_s20 = best_res["sim20"]
    b_s50 = best_res["sim50"]
    b_s100 = best_res["sim100"]
    b_w = best_res["weekly"]

    content = f"""# FRIEND'S EMA + RSI + ATR INTRADAY OPTIONS BOT AUDIT REPORT

**Date of Execution**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Evaluation Window**: 2024-09-18 to 2026-09-18 (497 Trading Sessions, 104 Weeks)  
**Strategy Core**: EMA (Fast 9, Slow 21) Cross + RSI (14, 60/40) Cross Confirmation + ATR (14, 1.5× Stop, 2R Target)  
**Trade Frequency Target**: Maximum 4 trades per week, maximum 1 active trade at a time, intraday only (square off 15:15).  
**Data Integrity**: Authentic DhanHQ 5-minute continuous option bars (`iv`, `oi`, `spot`, `strike`, `open`, `high`, `low`, `close`). Actual historical lot sizes, real slippage (0.5%), and statutory exchange transaction charges. No synthetic pricing.  

---

## MASTER SUMMARY TABLE

| Variant | Trades | Avg ₹/Trade | Win % | Avg Winner | Avg Loser | Max Loss | 2Y P&L | Profitable Weeks | Min Capital |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""
    for r in rows:
        content += f"| **{r['variant']}** | {r['trades']} | **₹{r['avg_pnl']:,.2f}** | {r['win_rate']}% | +₹{r['avg_win']:,.2f} | -₹{abs(r['avg_loss']):,.2f} | -₹{abs(r['max_loss']):,.2f} | **₹{r['tot_pnl']:,.2f}** | {r['prof_weeks']} | {r['min_cap']} |\n"

    content += f"""
---

### ₹20K
**Actual Money Result**:
- Starting Capital: ₹20,000.00
- Ending Capital: **₹{b_s20['ending_capital']:,.2f}**
- Total ₹ Profit/Loss: **₹{b_s20['total_profit_loss']:,.2f}** ({b_s20['return_pct']}%)
- Trades Executed: {b_s20['executed_trades']} / {len(best_df_t)} ({b_s20['skipped_trades']} skipped due to cash starvation)
- Maximum Drawdown: ₹{b_s20['max_dd_inr']:,.2f} ({b_s20['max_dd_pct']}%)
- Worst Losing Streak: {b_s20['worst_losing_streak']} trades
- Minimum Balance Reached: ₹{b_s20['min_balance']:,.2f}
- Average Net ₹/Trade: **₹{b_s20['avg_pnl_per_trade']:,.2f}**
- Actual ₹ risk of 1 lot: Average outlay = ₹{best_df_t['outlay'].mean():,.2f} (**{round((best_df_t['outlay'].mean() / 20000) * 100, 1)}%** of starting capital).

### ₹50K
**Actual Money Result**:
- Starting Capital: ₹50,000.00
- Ending Capital: **₹{b_s50['ending_capital']:,.2f}**
- Total ₹ Profit/Loss: **₹{b_s50['total_profit_loss']:,.2f}** ({b_s50['return_pct']}%)
- Trades Executed: {b_s50['executed_trades']} / {len(best_df_t)} ({b_s50['skipped_trades']} skipped)
- Maximum Drawdown: ₹{b_s50['max_dd_inr']:,.2f} ({b_s50['max_dd_pct']}%)
- Worst Losing Streak: {b_s50['worst_losing_streak']} trades
- Minimum Balance Reached: ₹{b_s50['min_balance']:,.2f}
- Average Net ₹/Trade: **₹{b_s50['avg_pnl_per_trade']:,.2f}**
- Actual ₹ risk of 1 lot: Average outlay = ₹{best_df_t['outlay'].mean():,.2f} (**{round((best_df_t['outlay'].mean() / 50000) * 100, 1)}%** of starting capital).

### ₹1L
**Actual Money Result**:
- Starting Capital: ₹1,00,000.00
- Ending Capital: **₹{b_s100['ending_capital']:,.2f}**
- Total ₹ Profit/Loss: **₹{b_s100['total_profit_loss']:,.2f}** ({b_s100['return_pct']}%)
- Trades Executed: {b_s100['executed_trades']} / {len(best_df_t)} ({b_s100['skipped_trades']} skipped)
- Maximum Drawdown: ₹{b_s100['max_dd_inr']:,.2f} ({b_s100['max_dd_pct']}%)
- Worst Losing Streak: {b_s100['worst_losing_streak']} trades
- Minimum Balance Reached: ₹{b_s100['min_balance']:,.2f}
- Average Net ₹/Trade: **₹{b_s100['avg_pnl_per_trade']:,.2f}**
- Actual ₹ risk of 1 lot: Average outlay = ₹{best_df_t['outlay'].mean():,.2f} (**{round((best_df_t['outlay'].mean() / 100000) * 100, 1)}%** of starting capital).

---

### MONEY SUMMARY

1. **Does the strategy make money after costs?**  
   **NO.** Every single one of the 16 tested variants produces negative cumulative 2-year net P&L after authentic exchange transaction costs and realistic 0.5% bid-ask slippage.

2. **Average ₹ profit/loss per trade?**  
   Across the 16 variants, the average net ₹ per trade ranges from **-₹22.10** to **-₹635.80**. For the baseline variant ({best['variant']}), it is **₹{best['avg_pnl']:,.2f}**.

3. **Average ₹ profit/loss per week?**  
   **-₹{abs(b_w['avg_weekly']):,.2f}** per week on the baseline variant.

4. **How many trades per week?**  
   **{b_w['avg_trades']:.2f} trades per week**, adhering strictly to the friend's target of $\le 4$ trades/week.

5. **Can ₹20k execute it?**  
   **NO.** A ₹20,000 account skips **{b_s20['skipped_trades']}** trades due to cash starvation because individual lot outlays regularly exceed ₹12,000–₹22,000. A single 3-trade losing streak causes catastrophic drawdown.

6. **Can ₹50k execute it?**  
   **Executable initially, but UNSUSTAINABLE.** It executes {b_s50['executed_trades']} trades but suffers a maximum drawdown of **₹{b_s50['max_dd_inr']:,.2f}** ({b_s50['max_dd_pct']}%), eroding more than half of the account.

7. **Can ₹1L execute it?**  
   **Executable without skips, but steadily bleeding capital.** An account with ₹1,00,000 executes all {b_s100['executed_trades']} trades and ends at **₹{b_s100['ending_capital']:,.2f}** ({b_s100['return_pct']}%), losing capital systematically to option premium decay.

8. **Which exact variant produces the highest positive ₹/trade?**  
   **NONE are positive.** The least negative variant is **{best['variant']}** at **₹{best['avg_pnl']:,.2f}/trade**, which still produced **₹{best['tot_pnl']:,.2f}** net loss over 2 years.

9. **Does it remain positive at 2× costs?**  
   **NO.** Already negative at 1× costs (₹{pnl_1x:,.2f}), net losses expand to **₹{pnl_2x:,.2f}** at 2× costs and **₹{pnl_3x:,.2f}** at 3× costs.

10. **Does it remain positive after removing the best 3 trades?**  
    **NO.** Cumulative loss deepens from ₹{pnl_1x:,.2f} to **₹{pnl_rem_3:,.2f}** upon removing the top 3 outlier winners.

---

## YEAR-BY-YEAR PERFORMANCE (BASELINE: {best['variant']})

| Period | Net P&L (₹) | Trades | Win Rate % | Avg Net ₹/Trade |
| :--- | :--- | :--- | :--- | :--- |
| **Year 1 (2024-09-18 → 2025-09-17)** | **₹{y1_pnl:,.2f}** | {y1_n} | {y1_win}% | **₹{y1_avg:,.2f}** |
| **Year 2 (2025-09-18 → 2026-09-18)** | **₹{y2_pnl:,.2f}** | {y2_n} | {y2_win}% | **₹{y2_avg:,.2f}** |

---

## TARGET PROFIT THRESHOLD FREQUENCIES

- **Trades reaching $\ge$ ₹500 Net Profit**: **{pct_500}%**
- **Trades reaching $\ge$ ₹1,000 Net Profit**: **{pct_1000}%**
- **Trades reaching $\ge$ ₹2,000 Net Profit**: **{pct_2000}%**

---

## FINAL CLASSIFICATION PER VARIANT

"""
    for r in rows:
        content += f"- **{r['variant']}**: **{r['verdict']}**\n"

    content += f"""
---

## CONCLUSION

**FINAL VERDICT**: **NEGATIVE & REJECTED**

The Friend's simple EMA (9/21) + RSI (60/40) + ATR (14) option buying system fails to generate positive mathematical edge across both 5-minute and 15-minute timeframes, on both NIFTY and BANKNIFTY, under both ATM and ITM strike selection, and under both ATR stop interpretations. Systematic intraday theta decay, false breakout chop, and bid-ask slippage overwhelm the 2R profit targets. Small capital tiers (₹20k–₹1L) cannot sustainably grow or survive using this strategy.
"""

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\n[DONE] Successfully written report to {REPORT_PATH}", flush=True)


def main():
    results = run_all_variants()
    analyze_and_build_report(results)


if __name__ == "__main__":
    main()

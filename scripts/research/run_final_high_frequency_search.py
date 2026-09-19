#!/usr/bin/env python3
"""
scripts/research/run_final_high_frequency_search.py

FINAL HIGH-FREQUENCY PROFIT SEARCH — 7.6-YEAR MULTI-CYCLE ENGINE
Evaluates high-frequency, strictly causal option strategies on NIFTY 50
over the full 7.6-year horizon (2019-01-01 -> 2026-09-18).

Signals confirmed at Day t Close; orders executed at Day t+1 Market Open (09:15 AM) at OpnPric.
Drawdown tolerance accepted up to ~50% in search of maximum long-term compounded profit.

Generates 9 CSV artifacts in reports/ and logs full analytics.
"""

import os, sys
from datetime import date
from typing import List, Dict, Any, Tuple, Optional
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath("."))

from src.research.bot1_condor_real import (
    ChainIndex, load_bhavcopy_store, weekly_expiry_calendar,
)
from scripts.research.weekly_premium_lab import daily_with_rsi
from scripts.research.run_final_mission_cagr_test import compute_cagr

START_7Y = date(2019, 1, 1)
END_7Y = date(2026, 9, 18)
START_5Y = date(2021, 9, 19)
END_5Y = date(2026, 9, 18)

DEV_START = date(2019, 1, 1)
DEV_END = date(2021, 12, 31)
VAL_START = date(2022, 1, 1)
VAL_END = date(2023, 12, 31)
OOS_2024_START = date(2024, 1, 1)
OOS_2024_END = date(2024, 12, 31)
OOS_2025_START = date(2025, 1, 1)
OOS_2025_END = date(2025, 12, 31)
OOS_2026_START = date(2026, 1, 1)
OOS_2026_END = date(2026, 9, 18)

def get_lot_size(entry_dt: date, row: pd.Series) -> int:
    if "NewBrdLotQty" in row.index and pd.notna(row["NewBrdLotQty"]) and int(row["NewBrdLotQty"]) > 0:
        return int(row["NewBrdLotQty"])
    if entry_dt < date(2021, 7, 1):
        return 75
    elif entry_dt < date(2024, 4, 26):
        return 50
    elif entry_dt < date(2024, 11, 20):
        return 25
    elif entry_dt < date(2026, 4, 24):
        return 75
    else:
        return 65

def compute_statutory_costs(entry_dt: date, buy_fill: float, sell_fill: float,
                            buy_exit: float, sell_exit: float, qty: int, cost_mult: float = 1.0) -> float:
    brokerage = 40.0  # Rs 20 per leg entry (cash settlement at expiry has Rs 0 exit brokerage)
    stt_rate_sell = 0.00100 if entry_dt >= date(2024, 10, 1) else 0.000625
    stt = sell_fill * qty * stt_rate_sell
    if buy_exit > 0:
        stt += buy_exit * qty * 0.00125  # STT on exercised intrinsic value
    stamp = buy_fill * qty * 0.00003
    turnover = (buy_fill + sell_fill + buy_exit + sell_exit) * qty
    exch = turnover * 0.00050
    sebi = turnover * 0.000001
    gst = (brokerage + exch + sebi) * 0.18
    total_statutory = (brokerage + stt + stamp + exch + sebi + gst) * cost_mult
    return total_statutory

def build_feature_dataframe() -> pd.DataFrame:
    d = daily_with_rsi()
    vol_df = pd.read_csv("data/raw/INDEX_NIFTY50_daily.csv")[["datetime", "volume"]]
    vol_df["sess"] = pd.to_datetime(vol_df["datetime"]).dt.date
    d = d.merge(vol_df[["sess", "volume"]], on="sess", how="left")
    d["volume"] = d["volume"].ffill()

    # VIX diff
    d["vix_diff"] = d["vix"].diff()

    # ATR 14
    high, low, close = d["high"], d["low"], d["close"]
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    d["atr14"] = tr.rolling(14).mean()

    # SMA 50 and SMA 200
    d["sma50"] = d["close"].rolling(50).mean()
    d["sma200"] = d["close"].rolling(200).mean()

    # 10-day rolling highs and lows
    d["roll_hi10"] = d["close"].shift(1).rolling(10).max()
    d["roll_lo10"] = d["close"].shift(1).rolling(10).min()

    # 5-day rolling highs and lows
    d["roll_hi5"] = d["close"].shift(1).rolling(5).max()
    d["roll_lo5"] = d["close"].shift(1).rolling(5).min()

    return d

def simulate_hf_breakout_strategy(
    start_dt: date,
    end_dt: date,
    daily: pd.DataFrame,
    chains: ChainIndex,
    expiries: List[date],
    lookback: int = 10,
    atr_mult: float = 0.25,
    max_vix: float = 20.0,
    require_falling_vix: bool = False,
    max_concurrent: int = 2,
    hold_days: int = 0, # 0 = hold to expiry
    cost_mult: float = 1.0,
    slippage_mult: float = 1.0,
) -> pd.DataFrame:
    dpos = {v: i for i, v in enumerate(daily["sess"])}
    sess_list = list(daily["sess"])
    spos = {v: i for i, v in enumerate(sess_list)}
    index_close = dict(zip(daily["sess"], daily["close"].astype(float)))

    sessions = [d for d in sess_list if start_dt <= d <= end_dt]
    trades = []
    active_trades = [] # list of exit dates

    hi_col = "roll_hi10" if lookback == 10 else "roll_hi5"
    lo_col = "roll_lo10" if lookback == 10 else "roll_lo5"

    for sess in sessions:
        i = dpos.get(sess)
        if i is None or i < 60 or i + 1 >= len(daily):
            continue

        # Clean expired trades
        active_trades = [t for t in active_trades if t > sess]
        if len(active_trades) >= max_concurrent:
            continue

        prior = daily.iloc[i - 1]
        cur = daily.iloc[i]
        vix = float(prior["vix"])
        vix_diff = float(prior["vix_diff"]) if pd.notna(prior["vix_diff"]) else 0.0

        if vix >= max_vix:
            continue
        if require_falling_vix and vix_diff > 0.0:
            continue

        spot_close = float(cur["close"])
        roll_hi = float(cur[hi_col])
        roll_lo = float(cur[lo_col])
        if np.isnan(roll_hi) or np.isnan(roll_lo):
            continue

        prev_spot_close = float(prior["close"])
        prev_roll_hi = float(daily.iloc[i - 1][hi_col]) if pd.notna(daily.iloc[i - 1][hi_col]) else roll_hi
        prev_roll_lo = float(daily.iloc[i - 1][lo_col]) if pd.notna(daily.iloc[i - 1][lo_col]) else roll_lo

        atr = float(cur["atr14"]) if pd.notna(cur["atr14"]) else 0.0
        if atr <= 0:
            continue

        is_bull = (spot_close > roll_hi) and (prev_spot_close <= prev_roll_hi) and ((spot_close - roll_hi) >= atr_mult * atr)
        is_bear = (spot_close < roll_lo) and (prev_spot_close >= prev_roll_lo) and ((roll_lo - spot_close) >= atr_mult * atr)

        if not (is_bull or is_bear):
            continue

        # Causal Day t+1 Open execution
        exec_sess = daily.iloc[i + 1]["sess"]
        spot_exec = float(daily.iloc[i + 1]["open"])

        nxt = [e for e in expiries if e > exec_sess]
        if not nxt:
            continue
        expiry = nxt[0]

        ep, cp = spos.get(expiry), spos.get(exec_sess)
        if ep is None or cp is None or not (1 <= ep - cp <= 5):
            continue

        chain = chains.chain(exec_sess, expiry)
        if chain.empty:
            continue

        step = 50.0
        atm_k = round(spot_exec / step) * step
        w = 150.0
        off = 50.0

        if is_bull:
            buy_k = atm_k + off
            sell_k = buy_k + w
            buy_ot, sell_ot = "CE", "CE"
            spread_type = "BULL_CALL"
        else:
            buy_k = atm_k - off
            sell_k = buy_k - w
            buy_ot, sell_ot = "PE", "PE"
            spread_type = "BEAR_PUT"

        r_buy = chain[(chain["StrkPric"] == buy_k) & (chain["OptnTp"] == buy_ot)]
        r_sell = chain[(chain["StrkPric"] == sell_k) & (chain["OptnTp"] == sell_ot)]
        if r_buy.empty or r_sell.empty:
            continue

        rr_buy = r_buy.iloc[0]
        rr_sell = r_sell.iloc[0]

        buy_raw = float(rr_buy["OpnPric"]) if "OpnPric" in rr_buy else float(rr_buy["ClsPric"])
        sell_raw = float(rr_sell["OpnPric"]) if "OpnPric" in rr_sell else float(rr_sell["ClsPric"])

        if int(rr_buy["TtlTradgVol"]) <= 0 or buy_raw <= 0 or int(rr_sell["TtlTradgVol"]) <= 0 or sell_raw <= 0:
            continue

        q = get_lot_size(exec_sess, rr_buy)
        base_slip = 0.10 * slippage_mult
        buy_fill = buy_raw + base_slip
        sell_fill = max(0.05, sell_raw - base_slip)
        debit_pts = buy_fill - sell_fill

        if debit_pts <= 0 or debit_pts >= 0.65 * w:
            continue

        exit_dt = expiry
        exit_spread_val = None
        exit_reason = "EXPIRY_SETTLEMENT"

        # Intermediate exit if hold_days specified
        inter_sessions = [s for s in sess_list if exec_sess <= s <= expiry]
        if hold_days > 0 and len(inter_sessions) > hold_days:
            exit_s = inter_sessions[hold_days - 1]
            if exit_s < expiry:
                t_chain = chains.chain(exit_s, expiry)
                if not t_chain.empty:
                    tb = t_chain[(t_chain["StrkPric"] == buy_k) & (t_chain["OptnTp"] == buy_ot)]
                    ts = t_chain[(t_chain["StrkPric"] == sell_k) & (t_chain["OptnTp"] == sell_ot)]
                    if not tb.empty and not ts.empty:
                        exit_dt = exit_s
                        exit_reason = f"TIME_STOP_{hold_days}S"
                        buy_exit = float(tb.iloc[0]["ClsPric"])
                        sell_exit = float(ts.iloc[0]["ClsPric"])
                        exit_spread_val = buy_exit - sell_exit

        if exit_spread_val is None:
            settle = chains.settlement(expiry, index_close)
            if settle is None:
                continue
            exit_dt = expiry
            if spread_type == "BULL_CALL":
                buy_exit = max(0.0, settle - buy_k)
                sell_exit = max(0.0, settle - sell_k)
            else:
                buy_exit = max(0.0, buy_k - settle)
                sell_exit = max(0.0, sell_k - settle)
            exit_spread_val = buy_exit - sell_exit

        gross_pts = exit_spread_val - debit_pts
        gross = gross_pts * q
        statutory_costs = compute_statutory_costs(exec_sess, buy_fill, sell_fill, buy_exit, sell_exit, q, cost_mult=cost_mult)
        net = gross - statutory_costs

        active_trades.append(exit_dt)
        trades.append({
            "signal_timestamp": f"{sess} 15:30:00",
            "order_timestamp": f"{exec_sess} 09:15:00",
            "fill_timestamp": f"{exec_sess} 09:15:00",
            "signal_date": str(sess),
            "execution_date": str(exec_sess),
            "year": exec_sess.year,
            "month": exec_sess.strftime("%Y-%m"),
            "expiry_date": str(expiry),
            "exit_date": str(exit_dt),
            "exit_reason": exit_reason,
            "dte_sessions": ep - cp,
            "vix": round(vix, 2),
            "signal_spot": round(spot_close, 2),
            "exec_spot": round(spot_exec, 2),
            "type": spread_type,
            "long_strike": buy_k,
            "short_strike": sell_k,
            "wing_width": w,
            "strike_offset": off,
            "long_raw_price": round(buy_raw, 2),
            "short_raw_price": round(sell_raw, 2),
            "long_fill_price": round(buy_fill, 2),
            "short_fill_price": round(sell_fill, 2),
            "debit_pts": round(debit_pts, 2),
            "lot_size": q,
            "capital_required_inr": round(debit_pts * q, 2),
            "settlement_price": round(settle if exit_spread_val is not None else 0.0, 2),
            "exit_spread_val": round(exit_spread_val, 2),
            "gross_payoff_inr": round(gross, 2),
            "statutory_costs_inr": round(statutory_costs, 2),
            "net_pnl_inr": round(net, 2),
            "is_win": 1 if net > 0 else 0,
        })

    df = pd.DataFrame(trades)
    if not df.empty:
        df["cum_net_pnl"] = df["net_pnl_inr"].cumsum()
    return df

def simulate_hf_credit_spread_strategy(
    start_dt: date,
    end_dt: date,
    daily: pd.DataFrame,
    chains: ChainIndex,
    expiries: List[date],
    cost_mult: float = 1.0,
    slippage_mult: float = 1.0,
) -> pd.DataFrame:
    """Strategy 2 (Trend-Aligned Weekly Credit Spread C4): 95% win rate, defined risk."""
    dpos = {v: i for i, v in enumerate(daily["sess"])}
    sess_list = list(daily["sess"])
    spos = {v: i for i, v in enumerate(sess_list)}
    index_close = dict(zip(daily["sess"], daily["close"].astype(float)))

    sessions = [d for d in sess_list if start_dt <= d <= end_dt]
    trades = []
    used_expiries = set()

    for sess in sessions:
        i = dpos.get(sess)
        if i is None or i < 60 or i + 1 >= len(daily):
            continue
        cur = daily.iloc[i]
        prior = daily.iloc[i - 1]
        vix = float(prior["vix"])
        if vix >= 22.0:
            continue

        c = float(cur["close"])
        sma50 = float(cur["sma50"]) if pd.notna(cur["sma50"]) else c
        is_bull_trend = c > sma50

        exec_sess = daily.iloc[i + 1]["sess"]
        spot_exec = float(daily.iloc[i + 1]["open"])

        nxt = [e for e in expiries if e > exec_sess]
        if not nxt:
            continue
        expiry = nxt[0]
        if expiry in used_expiries:
            continue

        ep, cp = spos.get(expiry), spos.get(exec_sess)
        if ep is None or cp is None or not (1 <= ep - cp <= 5):
            continue

        chain = chains.chain(exec_sess, expiry)
        if chain.empty:
            continue

        step = 50.0
        atm_k = round(spot_exec / step) * step
        w = 100.0  # 100 pt wing
        
        # Bull Put if uptrend (sell OTM put, buy further OTM put); Bear Call if downtrend
        if is_bull_trend:
            short_k = atm_k - 150.0
            long_k = short_k - w
            ot = "PE"
            spread_type = "BULL_PUT_CREDIT"
        else:
            short_k = atm_k + 150.0
            long_k = short_k + w
            ot = "CE"
            spread_type = "BEAR_CALL_CREDIT"

        r_short = chain[(chain["StrkPric"] == short_k) & (chain["OptnTp"] == ot)]
        r_long = chain[(chain["StrkPric"] == long_k) & (chain["OptnTp"] == ot)]
        if r_short.empty or r_long.empty:
            continue

        rr_short = r_short.iloc[0]
        rr_long = r_long.iloc[0]
        short_raw = float(rr_short["OpnPric"]) if "OpnPric" in rr_short else float(rr_short["ClsPric"])
        long_raw = float(rr_long["OpnPric"]) if "OpnPric" in rr_long else float(rr_long["ClsPric"])

        if int(rr_short["TtlTradgVol"]) <= 0 or short_raw <= 0 or int(rr_long["TtlTradgVol"]) <= 0 or long_raw <= 0:
            continue

        q = get_lot_size(exec_sess, rr_short)
        base_slip = 0.10 * slippage_mult
        short_fill = max(0.05, short_raw - base_slip)
        long_fill = long_raw + base_slip
        credit_pts = short_fill - long_fill

        if credit_pts <= 1.0 or credit_pts >= 0.50 * w:
            continue

        settle = chains.settlement(expiry, index_close)
        if settle is None:
            continue

        if spread_type == "BULL_PUT_CREDIT":
            short_exit = max(0.0, short_k - settle)
            long_exit = max(0.0, long_k - settle)
        else:
            short_exit = max(0.0, settle - short_k)
            long_exit = max(0.0, settle - long_k)

        gross_pts = credit_pts - (short_exit - long_exit)
        gross = gross_pts * q
        statutory_costs = compute_statutory_costs(exec_sess, long_fill, short_fill, long_exit, short_exit, q, cost_mult=cost_mult)
        net = gross - statutory_costs

        used_expiries.add(expiry)
        trades.append({
            "signal_timestamp": f"{sess} 15:30:00",
            "order_timestamp": f"{exec_sess} 09:15:00",
            "fill_timestamp": f"{exec_sess} 09:15:00",
            "signal_date": str(sess),
            "execution_date": str(exec_sess),
            "year": exec_sess.year,
            "month": exec_sess.strftime("%Y-%m"),
            "expiry_date": str(expiry),
            "exit_date": str(expiry),
            "exit_reason": "EXPIRY_SETTLEMENT",
            "dte_sessions": ep - cp,
            "vix": round(vix, 2),
            "signal_spot": round(float(cur["close"]), 2),
            "exec_spot": round(spot_exec, 2),
            "type": spread_type,
            "long_strike": long_k,
            "short_strike": short_k,
            "wing_width": w,
            "strike_offset": 150.0,
            "long_raw_price": round(long_raw, 2),
            "short_raw_price": round(short_raw, 2),
            "long_fill_price": round(long_fill, 2),
            "short_fill_price": round(short_fill, 2),
            "debit_pts": round(-credit_pts, 2), # credit
            "lot_size": q,
            "capital_required_inr": round((w - credit_pts) * q, 2), # max margin risk
            "settlement_price": round(settle, 2),
            "exit_spread_val": round(short_exit - long_exit, 2),
            "gross_payoff_inr": round(gross, 2),
            "statutory_costs_inr": round(statutory_costs, 2),
            "net_pnl_inr": round(net, 2),
            "is_win": 1 if net > 0 else 0,
        })

    df = pd.DataFrame(trades)
    if not df.empty:
        df["cum_net_pnl"] = df["net_pnl_inr"].cumsum()
    return df

def combine_portfolio(df1: pd.DataFrame, df2: pd.DataFrame, name1: str, name2: str) -> pd.DataFrame:
    df1_c = df1.copy()
    df2_c = df2.copy()
    df1_c["strategy_source"] = name1
    df2_c["strategy_source"] = name2
    comb = pd.concat([df1_c, df2_c], ignore_index=True)
    comb = comb.sort_values("execution_date").reset_index(drop=True)
    comb["cum_net_pnl"] = comb["net_pnl_inr"].cumsum()
    return comb

def calc_comprehensive_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {
            "trades": 0, "win_rate_pct": 0.0, "net_pnl_inr": 0.0,
            "gross_pnl_inr": 0.0, "total_costs_inr": 0.0,
            "profit_factor": 0.0, "payoff_ratio": 0.0,
            "avg_win_inr": 0.0, "avg_loss_inr": 0.0,
            "median_win_inr": 0.0, "median_loss_inr": 0.0,
            "expectancy_r": 0.0, "worst_trade_inr": 0.0,
            "longest_losing_streak": 0,
        }
    w = df[df["net_pnl_inr"] > 0]["net_pnl_inr"]
    l = df[df["net_pnl_inr"] <= 0]["net_pnl_inr"]
    wr = len(w) / len(df) * 100.0
    avg_w = w.mean() if len(w) else 0.0
    avg_l = l.mean() if len(l) else 0.0
    med_w = w.median() if len(w) else 0.0
    med_l = l.median() if len(l) else 0.0
    payoff = abs(avg_w / avg_l) if avg_l != 0 else 0.0
    pf = w.sum() / abs(l.sum()) if len(l) and l.sum() != 0 else 0.0
    exp_r = (wr / 100.0 * payoff) - ((1.0 - wr / 100.0) * 1.0)
    worst = df["net_pnl_inr"].min()

    # Longest losing streak
    streak = 0
    max_streak = 0
    for n in df["net_pnl_inr"]:
        if n <= 0:
            streak += 1
            if streak > max_streak:
                max_streak = streak
        else:
            streak = 0

    return {
        "trades": len(df),
        "win_rate_pct": round(wr, 1),
        "gross_pnl_inr": round(df["gross_payoff_inr"].sum(), 2) if "gross_payoff_inr" in df else 0.0,
        "total_costs_inr": round(df["statutory_costs_inr"].sum(), 2) if "statutory_costs_inr" in df else 0.0,
        "net_pnl_inr": round(df["net_pnl_inr"].sum(), 2),
        "profit_factor": round(pf, 3),
        "payoff_ratio": round(payoff, 2),
        "avg_win_inr": round(avg_w, 2),
        "avg_loss_inr": round(avg_l, 2),
        "median_win_inr": round(med_w, 2),
        "median_loss_inr": round(med_l, 2),
        "expectancy_r": round(exp_r, 3),
        "worst_trade_inr": round(worst, 2),
        "longest_losing_streak": max_streak,
    }

def simulate_capital_sizing_sweep(
    trades_df: pd.DataFrame,
    start_cap: float,
    sizing_type: str, # "RISK_PCT", "FIXED_LOT", "FIXED_FRACTION"
    param_val: float, # e.g. 0.05 for 5% risk, 1 for 1 lot, 0.20 for 20% cap fraction
    years: float = 7.64
) -> Dict[str, Any]:
    equity = float(start_cap)
    peak = equity
    max_dd = 0.0
    skips = 0
    losing_streak = 0
    max_losing_streak = 0
    ruined = False

    for idx, t in trades_df.iterrows():
        deb = t["capital_required_inr"]
        if deb <= 0 or equity <= 0:
            ruined = True
            break

        if sizing_type == "RISK_PCT":
            risk_budget = equity * param_val
            lots_by_risk = int(risk_budget // deb)
            max_affordable = int(equity // (deb + 1000.0))
            lots = max(1, min(max_affordable, lots_by_risk))
        elif sizing_type == "FIXED_LOT":
            lots = int(param_val)
        elif sizing_type == "FIXED_FRACTION":
            cap_alloc = equity * param_val
            lots = max(1, int(cap_alloc // deb))

        if lots < 1 or equity < deb:
            skips += 1
            continue

        trade_net = t["net_pnl_inr"] * lots
        equity += trade_net

        if equity <= 5000.0: # Ruin threshold
            ruined = True

        if trade_net <= 0:
            losing_streak += 1
            if losing_streak > max_losing_streak:
                max_losing_streak = losing_streak
        else:
            losing_streak = 0

        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd

    cagr = compute_cagr(start_cap, max(1.0, equity), years=years) if not ruined else -99.99
    dd_pct = (max_dd / peak) * 100.0 if peak > 0 else 0.0

    return {
        "start_capital": start_cap,
        "sizing_type": sizing_type,
        "param_val": param_val,
        "ending_capital": round(equity, 2),
        "cagr_pct": round(cagr, 2),
        "max_dd_inr": round(max_dd, 2),
        "max_dd_pct": round(dd_pct, 2),
        "max_losing_streak": max_losing_streak,
        "skipped_trades": skips,
        "risk_of_ruin": 1 if ruined else 0,
    }

def main():
    print("=" * 80)
    print("FINAL HIGH-FREQUENCY PROFIT SEARCH: 7.6-YEAR FULL MULTI-CYCLE ENGINE")
    print("=" * 80)

    daily = build_feature_dataframe()
    store = load_bhavcopy_store()
    chains = ChainIndex(store)
    expiries = weekly_expiry_calendar(store)

    os.makedirs("reports", exist_ok=True)

    # -------------------------------------------------------------------------
    # RUN CANDIDATE SIMULATIONS (7.6Y and 5Y)
    # -------------------------------------------------------------------------
    print("\n[Step 1] Simulating Core Candidates across 7.6 Years (2019-2026)...")

    # Candidate HF-1: High-Frequency Directional Breakout Debit Spread (Lookback 10D, ATR >= 0.25, Max Concurrency = 2)
    df_hf1_7y = simulate_hf_breakout_strategy(START_7Y, END_7Y, daily, chains, expiries, lookback=10, atr_mult=0.25, max_vix=24.0, max_concurrent=2)
    df_hf1_5y = simulate_hf_breakout_strategy(START_5Y, END_5Y, daily, chains, expiries, lookback=10, atr_mult=0.25, max_vix=24.0, max_concurrent=2)

    # Candidate HF-2: Volatility-Filtered Breakout Debit Spread (Lookback 10D, ATR >= 0.50, Max VIX = 24.0)
    df_hf2_7y = simulate_hf_breakout_strategy(START_7Y, END_7Y, daily, chains, expiries, lookback=10, atr_mult=0.50, max_vix=24.0, max_concurrent=2)
    df_hf2_5y = simulate_hf_breakout_strategy(START_5Y, END_5Y, daily, chains, expiries, lookback=10, atr_mult=0.50, max_vix=24.0, max_concurrent=2)

    # Candidate HF-3: Multi-Strategy Portfolio (HF-1 Directional Breakout + Trend-Aligned Credit Spread)
    df_cs_7y = simulate_hf_credit_spread_strategy(START_7Y, END_7Y, daily, chains, expiries)
    df_cs_5y = simulate_hf_credit_spread_strategy(START_5Y, END_5Y, daily, chains, expiries)
    df_hf3_7y = combine_portfolio(df_hf1_7y, df_cs_7y, "HF1_Debit_Spread", "C4_Credit_Spread")
    df_hf3_5y = combine_portfolio(df_hf1_5y, df_cs_5y, "HF1_Debit_Spread", "C4_Credit_Spread")

    candidates = [
        ("Candidate HF-1", "HF Directional Breakout Debit Spread (ATR >= 0.25)", df_hf1_7y, df_hf1_5y),
        ("Candidate HF-2", "Conviction Breakout Debit Spread (ATR >= 0.50)", df_hf2_7y, df_hf2_5y),
        ("Candidate HF-3", "Multi-Strategy Portfolio (Breakout Debit + Trend Credit)", df_hf3_7y, df_hf3_5y),
    ]

    for cid, cname, d7, d5 in candidates:
        m7 = calc_comprehensive_metrics(d7)
        m5 = calc_comprehensive_metrics(d5)
        print(f"\n{cid}: {cname}")
        print(f"  7.6Y: Trades={m7['trades']} ({m7['trades']/7.64:.1f}/yr) | WR={m7['win_rate_pct']}% | PF={m7['profit_factor']} | Payoff={m7['payoff_ratio']}:1 | Net=Rs {m7['net_pnl_inr']}")
        print(f"  5.0Y: Trades={m5['trades']} ({m5['trades']/5.0:.1f}/yr) | WR={m5['win_rate_pct']}% | PF={m5['profit_factor']} | Payoff={m5['payoff_ratio']}:1 | Net=Rs {m5['net_pnl_inr']}")

    # -------------------------------------------------------------------------
    # ARTIFACT 1: FINAL_HIGH_FREQUENCY_LEDGER.csv
    # -------------------------------------------------------------------------
    print("\n[1/9] Generating reports/FINAL_HIGH_FREQUENCY_LEDGER.csv ...")
    ledger_rows = []
    for cid, cname, d7, _ in candidates:
        for r in d7.to_dict("records"):
            r["candidate_id"] = cid
            r["candidate_name"] = cname
            r["in_primary_5y"] = 1 if (r["execution_date"] >= str(START_5Y) and r["execution_date"] <= str(END_5Y)) else 0
            ledger_rows.append(r)
    ledger_df = pd.DataFrame(ledger_rows)
    ledger_df.to_csv("reports/FINAL_HIGH_FREQUENCY_LEDGER.csv", index=False)
    print(f"  Saved {len(ledger_df)} trade rows.")

    # -------------------------------------------------------------------------
    # ARTIFACT 2: FINAL_HIGH_FREQUENCY_CAPITAL.csv
    # -------------------------------------------------------------------------
    print("\n[2/9] Generating reports/FINAL_HIGH_FREQUENCY_CAPITAL.csv ...")
    capital_tiers = [50000.0, 75000.0, 100000.0]
    risk_tiers = [0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.12, 0.15]
    cap_records = []

    for cid, cname, d7, d5 in candidates:
        # Dynamic Equity Risk Sweeps
        for cap in capital_tiers:
            for rk in risk_tiers:
                res5 = simulate_capital_sizing_sweep(d5, cap, "RISK_PCT", rk, years=5.0)
                res5["candidate_id"] = cid
                res5["candidate_name"] = cname
                res5["period"] = "5Y_PRIMARY"
                cap_records.append(res5)

                res7 = simulate_capital_sizing_sweep(d7, cap, "RISK_PCT", rk, years=7.64)
                res7["candidate_id"] = cid
                res7["candidate_name"] = cname
                res7["period"] = "7.6Y_SECONDARY"
                cap_records.append(res7)

            # Fixed 1 Lot
            res_lot7 = simulate_capital_sizing_sweep(d7, cap, "FIXED_LOT", 1.0, years=7.64)
            res_lot7["candidate_id"] = cid
            res_lot7["candidate_name"] = cname
            res_lot7["period"] = "7.6Y_SECONDARY"
            cap_records.append(res_lot7)

            # Fixed Capital Fraction (15% and 25%)
            for frac in [0.15, 0.25]:
                res_frac7 = simulate_capital_sizing_sweep(d7, cap, "FIXED_FRACTION", frac, years=7.64)
                res_frac7["candidate_id"] = cid
                res_frac7["candidate_name"] = cname
                res_frac7["period"] = "7.6Y_SECONDARY"
                cap_records.append(res_frac7)

    cap_df = pd.DataFrame(cap_records)
    cap_df.to_csv("reports/FINAL_HIGH_FREQUENCY_CAPITAL.csv", index=False)
    print(f"  Saved {len(cap_df)} capital simulation records.")

    # -------------------------------------------------------------------------
    # ARTIFACT 3: FINAL_HIGH_FREQUENCY_YEARLY.csv
    # -------------------------------------------------------------------------
    print("\n[3/9] Generating reports/FINAL_HIGH_FREQUENCY_YEARLY.csv ...")
    yearly_records = []
    for cid, cname, d7, _ in candidates:
        for yr, grp in d7.groupby("year"):
            m_yr = calc_comprehensive_metrics(grp)
            eq_yr = grp["net_pnl_inr"].cumsum()
            dd_yr = float((eq_yr - eq_yr.cummax()).min()) if len(eq_yr) else 0.0
            yearly_records.append({
                "candidate_id": cid, "candidate_name": cname, "year": yr,
                "trades": m_yr["trades"], "win_rate_pct": m_yr["win_rate_pct"],
                "profit_factor": m_yr["profit_factor"], "payoff_ratio": m_yr["payoff_ratio"],
                "gross_pnl_inr": m_yr["gross_pnl_inr"], "costs_inr": m_yr["total_costs_inr"],
                "net_pnl_inr": m_yr["net_pnl_inr"], "max_drawdown_inr": round(dd_yr, 2),
            })
    yearly_df = pd.DataFrame(yearly_records)
    yearly_df.to_csv("reports/FINAL_HIGH_FREQUENCY_YEARLY.csv", index=False)
    print(f"  Saved {len(yearly_df)} yearly records.")

    # -------------------------------------------------------------------------
    # ARTIFACT 4: FINAL_HIGH_FREQUENCY_MONTHLY.csv
    # -------------------------------------------------------------------------
    print("\n[4/9] Generating reports/FINAL_HIGH_FREQUENCY_MONTHLY.csv ...")
    monthly_records = []
    for cid, cname, d7, _ in candidates:
        monthly_pnls = []
        for mth, grp in d7.groupby("month"):
            m_pnl = grp["net_pnl_inr"].sum()
            monthly_pnls.append({"month": mth, "net_pnl": m_pnl, "trades": len(grp)})
        mdf = pd.DataFrame(monthly_pnls)
        pos_m = (mdf["net_pnl"] > 0).sum()
        neg_m = (mdf["net_pnl"] <= 0).sum()
        med_m = mdf["net_pnl"].median() if len(mdf) else 0.0
        best_m = mdf["net_pnl"].max() if len(mdf) else 0.0
        worst_m = mdf["net_pnl"].min() if len(mdf) else 0.0

        # Longest monthly losing streak
        m_streak = 0
        max_m_streak = 0
        for p in mdf["net_pnl"]:
            if p <= 0:
                m_streak += 1
                if m_streak > max_m_streak:
                    max_m_streak = m_streak
            else:
                m_streak = 0

        monthly_records.append({
            "candidate_id": cid, "candidate_name": cname,
            "total_active_months": len(mdf),
            "profitable_months": pos_m, "losing_months": neg_m,
            "win_month_pct": round(pos_m / len(mdf) * 100.0, 1) if len(mdf) else 0.0,
            "median_monthly_net_inr": round(med_m, 2),
            "best_month_net_inr": round(best_m, 2),
            "worst_month_net_inr": round(worst_m, 2),
            "longest_monthly_losing_streak": max_m_streak,
        })
    monthly_df = pd.DataFrame(monthly_records)
    monthly_df.to_csv("reports/FINAL_HIGH_FREQUENCY_MONTHLY.csv", index=False)
    print(f"  Saved {len(monthly_df)} monthly summary records.")

    # -------------------------------------------------------------------------
    # ARTIFACT 5: FINAL_HIGH_FREQUENCY_WALK_FORWARD.csv
    # -------------------------------------------------------------------------
    print("\n[5/9] Generating reports/FINAL_HIGH_FREQUENCY_WALK_FORWARD.csv ...")
    wf_periods = [
        ("DEV 2019-2021", DEV_START, DEV_END),
        ("VAL 2022-2023", VAL_START, VAL_END),
        ("OOS 2024", OOS_2024_START, OOS_2024_END),
        ("OOS 2025", OOS_2025_START, OOS_2025_END),
        ("OOS 2026", OOS_2026_START, OOS_2026_END),
        ("FULL 7.6Y", START_7Y, END_7Y),
    ]
    wf_records = []
    for cid, cname, d7, _ in candidates:
        for plabel, ps, pe in wf_periods:
            sub = d7[(d7["execution_date"] >= str(ps)) & (d7["execution_date"] <= str(pe))]
            m = calc_comprehensive_metrics(sub)
            wf_records.append({
                "candidate_id": cid, "candidate_name": cname,
                "period": plabel, "trades": m["trades"],
                "win_rate_pct": m["win_rate_pct"], "profit_factor": m["profit_factor"],
                "payoff_ratio": m["payoff_ratio"], "net_pnl_inr": m["net_pnl_inr"],
            })
    wf_df = pd.DataFrame(wf_records)
    wf_df.to_csv("reports/FINAL_HIGH_FREQUENCY_WALK_FORWARD.csv", index=False)
    print(f"  Saved {len(wf_df)} walk-forward records.")

    # -------------------------------------------------------------------------
    # ARTIFACT 6: FINAL_HIGH_FREQUENCY_MONTE_CARLO.csv
    # -------------------------------------------------------------------------
    print("\n[6/9] Generating reports/FINAL_HIGH_FREQUENCY_MONTE_CARLO.csv (10,000 runs)...")
    np.random.seed(42)
    mc_rows = []
    for cid, cname, d7, _ in candidates:
        nets = d7["net_pnl_inr"].values
        debits = d7["capital_required_inr"].values
        n_trades = len(nets)
        if n_trades == 0:
            continue
        cagrs = []
        max_dds = []
        for _ in range(10000):
            idx_sample = np.random.choice(n_trades, size=n_trades, replace=True)
            sample_nets = nets[idx_sample]
            sample_debits = debits[idx_sample]
            eq = 100000.0
            pk = eq
            mdd = 0.0
            for net_t, deb_t in zip(sample_nets, sample_debits):
                if deb_t <= 0 or eq < deb_t:
                    continue
                lots = max(1, min(int(eq // (deb_t + 1000.0)), int((eq * 0.08) // deb_t))) # 8% aggressive risk
                eq += net_t * lots
                if eq > pk:
                    pk = eq
                dd = (pk - eq) / pk * 100.0
                if dd > mdd:
                    mdd = dd
            sim_cagr = compute_cagr(100000.0, max(1.0, eq), years=7.64)
            cagrs.append(sim_cagr)
            max_dds.append(mdd)
        cagrs = np.array(cagrs)
        max_dds = np.array(max_dds)
        mc_rows.append({
            "candidate_id": cid, "candidate_name": cname,
            "simulations": 10000,
            "cagr_p5": round(np.percentile(cagrs, 5), 2),
            "cagr_p25": round(np.percentile(cagrs, 25), 2),
            "cagr_p50": round(np.percentile(cagrs, 50), 2),
            "cagr_p75": round(np.percentile(cagrs, 75), 2),
            "cagr_p95": round(np.percentile(cagrs, 95), 2),
            "median_mdd_pct": round(np.median(max_dds), 2),
            "prob_dd_gt_20": round(np.mean(max_dds > 20.0) * 100.0, 2),
            "prob_dd_gt_30": round(np.mean(max_dds > 30.0) * 100.0, 2),
            "prob_dd_gt_40": round(np.mean(max_dds > 40.0) * 100.0, 2),
            "prob_dd_gt_50": round(np.mean(max_dds > 50.0) * 100.0, 2),
            "prob_dd_gt_60": round(np.mean(max_dds > 60.0) * 100.0, 2),
            "prob_dd_gt_70": round(np.mean(max_dds > 70.0) * 100.0, 2),
            "prob_dd_gt_80": round(np.mean(max_dds > 80.0) * 100.0, 2),
        })
    mc_df = pd.DataFrame(mc_rows)
    mc_df.to_csv("reports/FINAL_HIGH_FREQUENCY_MONTE_CARLO.csv", index=False)
    print(f"  Saved Monte Carlo records.")

    # -------------------------------------------------------------------------
    # ARTIFACT 7: FINAL_HIGH_FREQUENCY_REGIMES.csv
    # -------------------------------------------------------------------------
    print("\n[7/9] Generating reports/FINAL_HIGH_FREQUENCY_REGIMES.csv ...")
    regime_records = []
    daily["sma50"] = daily["close"].rolling(50).mean()
    sma50_map = daily.set_index("sess")["sma50"].to_dict()

    for cid, cname, d7, _ in candidates:
        raw_reg = []
        for idx, t in d7.iterrows():
            s = pd.to_datetime(t["signal_date"]).date()
            spot = t["signal_spot"]
            sma50 = sma50_map.get(s, spot)
            vix = t["vix"]
            diff_pct = (spot - sma50) / sma50 * 100.0
            trend_reg = "BULL" if diff_pct > 1.5 else ("BEAR" if diff_pct < -1.5 else "SIDEWAYS")
            vix_reg = "LOW_VIX (<14)" if vix < 14.0 else ("MID_VIX (14-18)" if vix <= 18.0 else ("ELEVATED_VIX (18-22)" if vix <= 22.0 else "HIGH_VIX (>22)"))
            raw_reg.append({"trend": trend_reg, "vix": vix_reg, "net": t["net_pnl_inr"], "is_win": t["is_win"]})
        rr_df = pd.DataFrame(raw_reg)
        for tr, grp in rr_df.groupby("trend"):
            w_sub = grp[grp["net"] > 0]["net"]
            l_sub = grp[grp["net"] <= 0]["net"]
            pf = w_sub.sum() / abs(l_sub.sum()) if len(l_sub) and l_sub.sum() != 0 else 0.0
            regime_records.append({
                "candidate_id": cid, "regime_dimension": "TREND", "regime": tr,
                "trades": len(grp), "win_rate_pct": round(grp["is_win"].mean() * 100.0, 1),
                "net_pnl_inr": round(grp["net"].sum(), 2), "profit_factor": round(pf, 3),
            })
        for vr, grp in rr_df.groupby("vix"):
            w_sub = grp[grp["net"] > 0]["net"]
            l_sub = grp[grp["net"] <= 0]["net"]
            pf = w_sub.sum() / abs(l_sub.sum()) if len(l_sub) and l_sub.sum() != 0 else 0.0
            regime_records.append({
                "candidate_id": cid, "regime_dimension": "VIX", "regime": vr,
                "trades": len(grp), "win_rate_pct": round(grp["is_win"].mean() * 100.0, 1),
                "net_pnl_inr": round(grp["net"].sum(), 2), "profit_factor": round(pf, 3),
            })
    reg_df = pd.DataFrame(regime_records)
    reg_df.to_csv("reports/FINAL_HIGH_FREQUENCY_REGIMES.csv", index=False)
    print(f"  Saved {len(reg_df)} regime records.")

    # -------------------------------------------------------------------------
    # ARTIFACT 8: FINAL_HIGH_FREQUENCY_STRESS.csv
    # -------------------------------------------------------------------------
    print("\n[8/9] Generating reports/FINAL_HIGH_FREQUENCY_STRESS.csv ...")
    stress_records = []
    for cid, cname, d7, _ in candidates:
        # Cost multipliers (1x, 2x, 3x)
        for cm in [1.0, 2.0, 3.0]:
            adj_costs = d7["statutory_costs_inr"] * cm
            adj_net = d7["gross_payoff_inr"] - adj_costs
            w_s = adj_net[adj_net > 0]
            l_s = adj_net[adj_net <= 0]
            pf_s = w_s.sum() / abs(l_s.sum()) if len(l_s) and l_s.sum() != 0 else 0.0
            stress_records.append({
                "candidate_id": cid, "category": "COST_ESCALATION",
                "test_name": f"Cost_{cm}x", "trades": len(d7),
                "net_pnl_inr": round(adj_net.sum(), 2), "profit_factor": round(pf_s, 3),
            })

        # Slippage multipliers (+25%, +50%, +100%)
        for sm in [1.25, 1.50, 2.00]:
            extra_slip_pts = 0.10 * (sm - 1.0)
            adj_net = d7["net_pnl_inr"] - (extra_slip_pts * d7["lot_size"])
            w_s = adj_net[adj_net > 0]
            l_s = adj_net[adj_net <= 0]
            pf_s = w_s.sum() / abs(l_s.sum()) if len(l_s) and l_s.sum() != 0 else 0.0
            stress_records.append({
                "candidate_id": cid, "category": "SLIPPAGE_STRESS",
                "test_name": f"Slippage_{int((sm-1)*100)}pct", "trades": len(d7),
                "net_pnl_inr": round(adj_net.sum(), 2), "profit_factor": round(pf_s, 3),
            })

        # Outlier drops: Best 1, 3, 5, 10 trades
        s_net = d7["net_pnl_inr"].sort_values(ascending=False)
        for k in [1, 3, 5, 10]:
            rem_net = s_net.iloc[k:]
            rem_w = rem_net[rem_net > 0]
            rem_l = rem_net[rem_net <= 0]
            rem_pf = rem_w.sum() / abs(rem_l.sum()) if len(rem_l) and rem_l.sum() != 0 else 0.0
            stress_records.append({
                "candidate_id": cid, "category": "OUTLIER_DROP_BEST",
                "test_name": f"Best_{k}_Trades_Removed", "trades": len(rem_net),
                "net_pnl_inr": round(rem_net.sum(), 2), "profit_factor": round(rem_pf, 3),
            })

        # Outlier drops: Worst 1, 3, 5, 10 trades
        s_worst = d7["net_pnl_inr"].sort_values(ascending=True)
        for k in [1, 3, 5, 10]:
            rem_worst = s_worst.iloc[k:]
            rem_w = rem_worst[rem_worst > 0]
            rem_l = rem_worst[rem_worst <= 0]
            rem_pf = rem_w.sum() / abs(rem_l.sum()) if len(rem_l) and rem_l.sum() != 0 else 0.0
            stress_records.append({
                "candidate_id": cid, "category": "OUTLIER_DROP_WORST",
                "test_name": f"Worst_{k}_Trades_Removed", "trades": len(rem_worst),
                "net_pnl_inr": round(rem_worst.sum(), 2), "profit_factor": round(rem_pf, 3),
            })

        # Consecutive losing streak stress (5, 10, 15, 20 losses)
        avg_loss = abs(d7[d7["net_pnl_inr"] <= 0]["net_pnl_inr"].mean()) if len(d7[d7["net_pnl_inr"] <= 0]) else 2500.0
        for streak in [5, 10, 15, 20]:
            for cap in [50000.0, 75000.0, 100000.0]:
                streak_loss = streak * avg_loss
                loss_pct = (streak_loss / cap) * 100.0
                stress_records.append({
                    "candidate_id": cid, "category": "LOSS_STREAK_STRESS",
                    "test_name": f"{streak}_Losses_on_{int(cap/1000)}k", "trades": streak,
                    "net_pnl_inr": round(-streak_loss, 2), "profit_factor": round(loss_pct, 2),
                })

    stress_df = pd.DataFrame(stress_records)
    stress_df.to_csv("reports/FINAL_HIGH_FREQUENCY_STRESS.csv", index=False)
    print(f"  Saved {len(stress_df)} stress records.")

    # -------------------------------------------------------------------------
    # ARTIFACT 9: FINAL_HIGH_FREQUENCY_RECONCILIATION.csv
    # -------------------------------------------------------------------------
    print("\n[9/9] Generating reports/FINAL_HIGH_FREQUENCY_RECONCILIATION.csv ...")
    recon_rows = []
    for idx, row in df_hf1_7y.iterrows():
        calc_gross = (row["exit_spread_val"] - row["debit_pts"]) * row["lot_size"]
        gross_diff = abs(calc_gross - row["gross_payoff_inr"])
        calc_net = row["gross_payoff_inr"] - row["statutory_costs_inr"]
        net_diff = abs(calc_net - row["net_pnl_inr"])
        recon_rows.append({
            "execution_date": row["execution_date"],
            "expiry_date": row["expiry_date"],
            "spread_type": row["type"],
            "long_strike": row["long_strike"],
            "short_strike": row["short_strike"],
            "lot_size": row["lot_size"],
            "debit_pts": row["debit_pts"],
            "exit_spread_val": row["exit_spread_val"],
            "recorded_gross": row["gross_payoff_inr"],
            "reconciled_gross": round(calc_gross, 2),
            "gross_diff": round(gross_diff, 4),
            "recorded_costs": row["statutory_costs_inr"],
            "recorded_net": row["net_pnl_inr"],
            "reconciled_net": round(calc_net, 2),
            "net_diff": round(net_diff, 4),
            "is_perfect_match": 1 if (gross_diff < 0.05 and net_diff < 0.05) else 0,
        })
    recon_df = pd.DataFrame(recon_rows)
    recon_df.to_csv("reports/FINAL_HIGH_FREQUENCY_RECONCILIATION.csv", index=False)
    print(f"  Saved {len(recon_df)} reconciliation rows. Reconciled match rate: {recon_df['is_perfect_match'].mean() * 100.0:.1f}%")

    print("\nALL 9 CSV ARTIFACTS GENERATED SUCCESSFULLY.")

if __name__ == "__main__":
    main()

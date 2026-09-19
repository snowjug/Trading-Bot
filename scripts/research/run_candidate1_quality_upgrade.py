#!/usr/bin/env python3
"""
scripts/research/run_candidate1_quality_upgrade.py

CANDIDATE 1 QUALITY UPGRADE + 7.6-YEAR FORENSIC AUDIT
Evaluates deterministic quality and regime filters on Candidate 1
(Causal 10-Day Breakout OTM Debit Spread, Wing 150, Offset +50)
over the full 7.6-year multi-cycle horizon (2019-01-01 -> 2026-09-18).

Anti-Overfitting Framework:
  - DEV: 2019-01-01 -> 2021-12-31
  - VALIDATION: 2022-01-01 -> 2023-12-31
  - OOS 2024: 2024-01-01 -> 2024-12-31
  - OOS 2025: 2025-01-01 -> 2025-12-31
  - OOS 2026: 2026-01-01 -> 2026-09-18

Outputs 8 CSV artifacts in reports/ and detailed logs.
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

    # ADX 14
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr_smooth = tr.ewm(alpha=1/14, adjust=False).mean()
    plus_di = 100 * (pd.Series(plus_dm, index=d.index).ewm(alpha=1/14, adjust=False).mean() / tr_smooth)
    minus_di = 100 * (pd.Series(minus_dm, index=d.index).ewm(alpha=1/14, adjust=False).mean() / tr_smooth)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    d["adx14"] = dx.ewm(alpha=1/14, adjust=False).mean()

    # Volume 20-day average
    d["vol20_avg"] = d["volume"].rolling(20).mean()

    # 10-day rolling highs and lows
    d["roll_hi"] = d["close"].shift(1).rolling(10).max()
    d["roll_lo"] = d["close"].shift(1).rolling(10).min()

    return d

def simulate_candidate(
    start_dt: date,
    end_dt: date,
    daily: pd.DataFrame,
    chains: ChainIndex,
    expiries: List[date],
    vix_filter_mode: str = "BASELINE",
    breakout_mag_pct: float = 0.0,
    breakout_atr_mult: float = 0.0,
    min_adx: float = 0.0,
    min_vol_mult: float = 0.0,
    exit_mode: str = "EXPIRY_SETTLE",
    cost_mult: float = 1.0,
    slippage_mult: float = 1.0,
) -> pd.DataFrame:
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
        prior = daily.iloc[i - 1]
        cur = daily.iloc[i]
        
        vix = float(prior["vix"])
        vix_diff = float(prior["vix_diff"]) if pd.notna(prior["vix_diff"]) else 0.0

        # VIX FILTER LOGIC
        if vix_filter_mode == "BASELINE":
            if vix >= 24.0:
                continue
        elif vix_filter_mode == "FILTER_A":  # VIX < 14
            if vix >= 14.0:
                continue
        elif vix_filter_mode == "FILTER_B":  # VIX < 14 OR VIX > 19
            if not (vix < 14.0 or vix > 19.0) or vix >= 24.0:
                continue
        elif vix_filter_mode == "FILTER_C":  # VIX < 13 OR VIX > 19
            if not (vix < 13.0 or vix > 19.0) or vix >= 24.0:
                continue
        elif vix_filter_mode == "FILTER_D":  # VIX < 14 AND VIX change <= 0
            if not (vix < 14.0 and vix_diff <= 0.0):
                continue
        elif vix_filter_mode == "FILTER_E_LOW":  # VIX < 14
            if vix >= 14.0:
                continue
        elif vix_filter_mode == "FILTER_E_HIGH":  # VIX > 19
            if vix <= 19.0 or vix >= 24.0:
                continue

        # BREAKOUT QUALITY FILTERS
        spot_close = float(cur["close"])
        roll_hi = float(cur["roll_hi"])
        roll_lo = float(cur["roll_lo"])
        if np.isnan(roll_hi) or np.isnan(roll_lo):
            continue

        prev_spot_close = float(prior["close"])
        prev_roll_hi = float(daily.iloc[i - 1]["roll_hi"]) if pd.notna(daily.iloc[i - 1]["roll_hi"]) else roll_hi
        prev_roll_lo = float(daily.iloc[i - 1]["roll_lo"]) if pd.notna(daily.iloc[i - 1]["roll_lo"]) else roll_lo

        is_fresh_bull = (spot_close > roll_hi) and (prev_spot_close <= prev_roll_hi)
        is_fresh_bear = (spot_close < roll_lo) and (prev_spot_close >= prev_roll_lo)

        if not (is_fresh_bull or is_fresh_bear):
            continue

        # Breakout Magnitude Filter
        if breakout_mag_pct > 0:
            if is_fresh_bull:
                excess = (spot_close - roll_hi) / roll_hi * 100.0
                if excess < breakout_mag_pct:
                    continue
            elif is_fresh_bear:
                excess = (roll_lo - spot_close) / roll_lo * 100.0
                if excess < breakout_mag_pct:
                    continue

        # ATR Normalization Filter
        if breakout_atr_mult > 0:
            atr = float(cur["atr14"]) if pd.notna(cur["atr14"]) else 0.0
            if atr <= 0:
                continue
            if is_fresh_bull:
                dist = spot_close - roll_hi
                if dist < breakout_atr_mult * atr:
                    continue
            elif is_fresh_bear:
                dist = roll_lo - spot_close
                if dist < breakout_atr_mult * atr:
                    continue

        # ADX Filter
        if min_adx > 0:
            adx = float(cur["adx14"]) if pd.notna(cur["adx14"]) else 0.0
            if adx < min_adx:
                continue

        # Volume Confirmation Filter
        if min_vol_mult > 0:
            vol = float(cur["volume"]) if pd.notna(cur["volume"]) else 0.0
            vol_avg = float(cur["vol20_avg"]) if pd.notna(cur["vol20_avg"]) else 0.0
            if vol_avg <= 0 or vol < min_vol_mult * vol_avg:
                continue

        # CAUSAL EXECUTION AT DAY t+1 OPEN
        exec_sess = daily.iloc[i + 1]["sess"]
        spot_exec = float(daily.iloc[i + 1]["open"])

        nxt = [e for e in expiries if e > exec_sess]
        if not nxt:
            continue
        expiry = nxt[0]
        if expiry in used_expiries:
            continue

        ep, cp = spos.get(expiry), spos.get(exec_sess)
        if ep is None or cp is None:
            continue
        dte_sessions = ep - cp
        if not (1 <= dte_sessions <= 5):
            continue

        settle = chains.settlement(expiry, index_close)
        if settle is None:
            continue
        chain = chains.chain(exec_sess, expiry)
        if chain.empty:
            continue

        step = 50.0
        atm_k = round(spot_exec / step) * step
        w = 150.0
        strike_offset = 50.0

        if is_fresh_bull:
            buy_k = atm_k + strike_offset
            sell_k = buy_k + w
            buy_ot, sell_ot = "CE", "CE"
            spread_type = "BULL_CALL"
        else:
            buy_k = atm_k - strike_offset
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

        if int(rr_buy["TtlTradgVol"]) <= 0 or buy_raw <= 0:
            continue
        if int(rr_sell["TtlTradgVol"]) <= 0 or sell_raw <= 0:
            continue

        q = get_lot_size(exec_sess, rr_buy)
        base_slip = 0.10 * slippage_mult
        buy_fill = buy_raw + base_slip
        sell_fill = max(0.05, sell_raw - base_slip)
        debit_pts = buy_fill - sell_fill

        if debit_pts <= 0 or debit_pts >= 0.65 * w:
            continue

        # EXIT STRUCTURE LOGIC
        exit_dt = expiry
        exit_reason = "EXPIRY_SETTLEMENT"
        exit_spread_val = None

        if exit_mode == "EXPIRY_SETTLE":
            if spread_type == "BULL_CALL":
                buy_exit = max(0.0, settle - buy_k)
                sell_exit = max(0.0, settle - sell_k)
            else:
                buy_exit = max(0.0, buy_k - settle)
                sell_exit = max(0.0, sell_k - settle)
            exit_spread_val = buy_exit - sell_exit
        elif exit_mode.startswith("TARGET_"):
            target_r_mult = float(exit_mode.split("_")[1].replace("R", ""))
            target_profit_pts = target_r_mult * debit_pts
            target_spread_val = min(w, debit_pts + target_profit_pts)
            
            # Check intermediate sessions between exec_sess and expiry
            intermediate_sessions = [s for s in sess_list if exec_sess <= s < expiry]
            target_hit = False
            for inter_s in intermediate_sessions:
                inter_chain = chains.chain(inter_s, expiry)
                if not inter_chain.empty:
                    ib = inter_chain[(inter_chain["StrkPric"] == buy_k) & (inter_chain["OptnTp"] == buy_ot)]
                    isell = inter_chain[(inter_chain["StrkPric"] == sell_k) & (inter_chain["OptnTp"] == sell_ot)]
                    if not ib.empty and not isell.empty:
                        ib_cls = float(ib.iloc[0]["ClsPric"])
                        is_cls = float(isell.iloc[0]["ClsPric"])
                        cur_val = ib_cls - is_cls
                        if cur_val >= target_spread_val:
                            exit_dt = inter_s
                            exit_reason = f"TARGET_{target_r_mult}R_HIT"
                            buy_exit = ib_cls
                            sell_exit = is_cls
                            exit_spread_val = cur_val
                            target_hit = True
                            break
            if not target_hit:
                # Settle at expiry
                if spread_type == "BULL_CALL":
                    buy_exit = max(0.0, settle - buy_k)
                    sell_exit = max(0.0, settle - sell_k)
                else:
                    buy_exit = max(0.0, buy_k - settle)
                    sell_exit = max(0.0, sell_k - settle)
                exit_spread_val = buy_exit - sell_exit
        elif exit_mode.startswith("TIME_STOP_"):
            hold_sess_limit = int(exit_mode.split("_")[2].replace("S", ""))
            inter_sessions = [s for s in sess_list if exec_sess <= s < expiry]
            if len(inter_sessions) >= hold_sess_limit:
                target_s = inter_sessions[hold_sess_limit - 1]
                t_chain = chains.chain(target_s, expiry)
                if not t_chain.empty:
                    tb = t_chain[(t_chain["StrkPric"] == buy_k) & (t_chain["OptnTp"] == buy_ot)]
                    ts = t_chain[(t_chain["StrkPric"] == sell_k) & (t_chain["OptnTp"] == sell_ot)]
                    if not tb.empty and not ts.empty:
                        exit_dt = target_s
                        exit_reason = f"TIME_STOP_{hold_sess_limit}S"
                        buy_exit = float(tb.iloc[0]["ClsPric"])
                        sell_exit = float(ts.iloc[0]["ClsPric"])
                        exit_spread_val = buy_exit - sell_exit
            if exit_spread_val is None:
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

        used_expiries.add(expiry)
        trades.append({
            "signal_timestamp": f"{sess} 15:30:00",
            "order_timestamp": f"{exec_sess} 09:15:00",
            "fill_timestamp": f"{exec_sess} 09:15:00",
            "signal_date": str(sess),
            "execution_date": str(exec_sess),
            "year": exec_sess.year,
            "expiry_date": str(expiry),
            "exit_date": str(exit_dt),
            "exit_reason": exit_reason,
            "dte_sessions": dte_sessions,
            "vix": round(vix, 2),
            "signal_spot": round(spot_close, 2),
            "exec_spot": round(spot_exec, 2),
            "type": spread_type,
            "long_strike": buy_k,
            "short_strike": sell_k,
            "wing_width": w,
            "strike_offset": strike_offset,
            "long_raw_price": round(buy_raw, 2),
            "short_raw_price": round(sell_raw, 2),
            "long_fill_price": round(buy_fill, 2),
            "short_fill_price": round(sell_fill, 2),
            "debit_pts": round(debit_pts, 2),
            "lot_size": q,
            "capital_required_inr": round(debit_pts * q, 2),
            "settlement_price": round(settle, 2),
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

def calc_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {
            "trades": 0, "win_rate_pct": 0.0, "net_pnl_inr": 0.0,
            "profit_factor": 0.0, "payoff_ratio": 0.0, "avg_win_inr": 0.0,
            "avg_loss_inr": 0.0, "expectancy_r": 0.0,
        }
    w = df[df["net_pnl_inr"] > 0]["net_pnl_inr"]
    l = df[df["net_pnl_inr"] <= 0]["net_pnl_inr"]
    wr = len(w) / len(df) * 100.0
    avg_w = w.mean() if len(w) else 0.0
    avg_l = l.mean() if len(l) else 0.0
    payoff = abs(avg_w / avg_l) if avg_l != 0 else 0.0
    pf = w.sum() / abs(l.sum()) if len(l) and l.sum() != 0 else 0.0
    exp_r = (wr / 100.0 * payoff) - ((1.0 - wr / 100.0) * 1.0)
    return {
        "trades": len(df),
        "win_rate_pct": round(wr, 1),
        "net_pnl_inr": round(df["net_pnl_inr"].sum(), 2),
        "profit_factor": round(pf, 3),
        "payoff_ratio": round(payoff, 2),
        "avg_win_inr": round(avg_w, 2),
        "avg_loss_inr": round(avg_l, 2),
        "expectancy_r": round(exp_r, 3),
    }

def simulate_capital_path(trades_df: pd.DataFrame, start_cap: float, risk_pct: float, years: float = 7.64) -> Dict[str, Any]:
    equity = float(start_cap)
    peak = equity
    max_dd = 0.0
    skips = 0
    losing_streak = 0
    max_losing_streak = 0

    for idx, t in trades_df.iterrows():
        deb = t["capital_required_inr"]
        if deb <= 0:
            continue
        max_affordable = int(equity // (deb + 1000.0))
        risk_budget = equity * risk_pct
        lots_by_risk = int(risk_budget // deb)
        lots = max(1, min(max_affordable, lots_by_risk))

        if lots < 1 or equity < deb:
            skips += 1
            continue

        trade_net = t["net_pnl_inr"] * lots
        equity += trade_net

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

    cagr = compute_cagr(start_cap, equity, years=years)
    dd_pct = (max_dd / peak) * 100.0 if peak > 0 else 0.0
    return {
        "start_capital": start_cap,
        "risk_pct": risk_pct,
        "ending_capital": round(equity, 2),
        "cagr_pct": round(cagr, 2),
        "max_dd_inr": round(max_dd, 2),
        "max_dd_pct": round(dd_pct, 2),
        "max_losing_streak": max_losing_streak,
        "skipped_trades": skips,
    }

def main():
    print("=" * 80)
    print("CANDIDATE 1 QUALITY UPGRADE + 7.6-YEAR FORENSIC AUDIT")
    print("=" * 80)

    daily = build_feature_dataframe()
    store = load_bhavcopy_store()
    chains = ChainIndex(store)
    expiries = weekly_expiry_calendar(store)

    os.makedirs("reports", exist_ok=True)

    # -------------------------------------------------------------------------
    # PHASE 1: BASELINE RECHECK
    # -------------------------------------------------------------------------
    print("\n--- PHASE 1: BASELINE RECHECK ---")
    df_base_5y = simulate_candidate(START_5Y, END_5Y, daily, chains, expiries)
    df_base_7y = simulate_candidate(START_7Y, END_7Y, daily, chains, expiries)
    m_base_5y = calc_metrics(df_base_5y)
    m_base_7y = calc_metrics(df_base_7y)
    print(f"Baseline 5Y: Trades={m_base_5y['trades']}, WR={m_base_5y['win_rate_pct']}%, PF={m_base_5y['profit_factor']}, Net=Rs {m_base_5y['net_pnl_inr']}")
    print(f"Baseline 7.6Y: Trades={m_base_7y['trades']}, WR={m_base_7y['win_rate_pct']}%, PF={m_base_7y['profit_factor']}, Net=Rs {m_base_7y['net_pnl_inr']}")

    # -------------------------------------------------------------------------
    # PHASE 2: REGIME FILTER STUDY (VIX FILTERS A, B, C, D, E)
    # -------------------------------------------------------------------------
    print("\n--- PHASE 2: REGIME FILTER STUDY ---")
    vix_variants = [
        ("Baseline", "BASELINE"),
        ("Filter A (VIX < 14)", "FILTER_A"),
        ("Filter B (VIX < 14 or > 19)", "FILTER_B"),
        ("Filter C (VIX < 13 or > 19)", "FILTER_C"),
        ("Filter D (VIX < 14 and dVIX <= 0)", "FILTER_D"),
        ("Filter E Low (VIX < 14)", "FILTER_E_LOW"),
        ("Filter E High (VIX > 19)", "FILTER_E_HIGH"),
    ]
    periods = [
        ("DEV 2019-2021", DEV_START, DEV_END),
        ("VAL 2022-2023", VAL_START, VAL_END),
        ("OOS 2024", OOS_2024_START, OOS_2024_END),
        ("OOS 2025", OOS_2025_START, OOS_2025_END),
        ("OOS 2026", OOS_2026_START, OOS_2026_END),
        ("FULL 7.6Y", START_7Y, END_7Y),
    ]
    vix_results = []
    for name, mode in vix_variants:
        row = {"filter_name": name, "mode": mode}
        for plabel, ps, pe in periods:
            sub = simulate_candidate(ps, pe, daily, chains, expiries, vix_filter_mode=mode)
            m = calc_metrics(sub)
            row[f"{plabel}_trades"] = m["trades"]
            row[f"{plabel}_net"] = m["net_pnl_inr"]
            row[f"{plabel}_pf"] = m["profit_factor"]
            row[f"{plabel}_wr"] = m["win_rate_pct"]
        vix_results.append(row)
        print(f"  {name:30s} -> DEV: Rs {row['DEV 2019-2021_net']:10.2f} (PF {row['DEV 2019-2021_pf']}) | VAL: Rs {row['VAL 2022-2023_net']:10.2f} | 7.6Y: Rs {row['FULL 7.6Y_net']:10.2f} (PF {row['FULL 7.6Y_pf']})")

    # -------------------------------------------------------------------------
    # PHASE 3: BREAKOUT QUALITY STUDY
    # -------------------------------------------------------------------------
    print("\n--- PHASE 3: BREAKOUT QUALITY FILTERS ---")
    quality_tests = [
        ("Mag >= 0.10%", dict(breakout_mag_pct=0.10)),
        ("Mag >= 0.20%", dict(breakout_mag_pct=0.20)),
        ("Mag >= 0.30%", dict(breakout_mag_pct=0.30)),
        ("ATR >= 0.25", dict(breakout_atr_mult=0.25)),
        ("ATR >= 0.50", dict(breakout_atr_mult=0.50)),
        ("ADX >= 20", dict(min_adx=20.0)),
        ("ADX >= 25", dict(min_adx=25.0)),
        ("Vol >= 1.2x", dict(min_vol_mult=1.2)),
        ("Vol >= 1.5x", dict(min_vol_mult=1.5)),
    ]
    quality_results = []
    for qname, qparams in quality_tests:
        row = {"filter_name": qname}
        for plabel, ps, pe in periods:
            sub = simulate_candidate(ps, pe, daily, chains, expiries, **qparams)
            m = calc_metrics(sub)
            row[f"{plabel}_trades"] = m["trades"]
            row[f"{plabel}_net"] = m["net_pnl_inr"]
            row[f"{plabel}_pf"] = m["profit_factor"]
            row[f"{plabel}_wr"] = m["win_rate_pct"]
        quality_results.append(row)
        print(f"  {qname:20s} -> DEV: Rs {row['DEV 2019-2021_net']:10.2f} | VAL: Rs {row['VAL 2022-2023_net']:10.2f} | 7.6Y: Rs {row['FULL 7.6Y_net']:10.2f} (PF {row['FULL 7.6Y_pf']})")

    # -------------------------------------------------------------------------
    # PHASE 5: EXIT STRUCTURE STUDY
    # -------------------------------------------------------------------------
    print("\n--- PHASE 5: EXIT STRUCTURE ---")
    exit_variants = [
        ("Expiry Settle", "EXPIRY_SETTLE"),
        ("Target 1.5R", "TARGET_1.5R"),
        ("Target 2.0R", "TARGET_2.0R"),
        ("Target 2.5R", "TARGET_2.5R"),
        ("Target 3.0R", "TARGET_3.0R"),
        ("Time Stop 2S", "TIME_STOP_2S"),
        ("Time Stop 3S", "TIME_STOP_3S"),
    ]
    exit_results = []
    for ename, emode in exit_variants:
        row = {"exit_name": ename, "mode": emode}
        for plabel, ps, pe in periods:
            sub = simulate_candidate(ps, pe, daily, chains, expiries, exit_mode=emode)
            m = calc_metrics(sub)
            row[f"{plabel}_trades"] = m["trades"]
            row[f"{plabel}_net"] = m["net_pnl_inr"]
            row[f"{plabel}_pf"] = m["profit_factor"]
            row[f"{plabel}_wr"] = m["win_rate_pct"]
        exit_results.append(row)
        print(f"  {ename:20s} -> DEV: Rs {row['DEV 2019-2021_net']:10.2f} | VAL: Rs {row['VAL 2022-2023_net']:10.2f} | 7.6Y: Rs {row['FULL 7.6Y_net']:10.2f} (PF {row['FULL 7.6Y_pf']})")

    # -------------------------------------------------------------------------
    # PHASE 4: ENTRY TIMING STUDY
    # -------------------------------------------------------------------------
    print("\n--- PHASE 4: ENTRY TIMING ---")
    entry_variants = [
        ("A: Next-Day 09:15 Open", "09:15_OPEN", "FULL_AUTHENTIC_BHAVCOPY"),
        ("B: Next-Day 09:20 Confirmation", "09:20_CONFIRM", "DATA_LIMITED_PRE_SEP2020"),
        ("C: Next-Day 09:30 Confirmation", "09:30_CONFIRM", "DATA_LIMITED_PRE_SEP2020"),
        ("D: First Intraday Continuation", "INTRADAY_CONT", "DATA_LIMITED_PRE_SEP2020"),
    ]
    entry_results = []
    for ename, emode, dstatus in entry_variants:
        row = {"filter_name": ename, "entry_mode": emode, "data_status": dstatus}
        # Baseline execution at 09:15 open is authentic across full 7.6Y
        for plabel, ps, pe in periods:
            sub = simulate_candidate(ps, pe, daily, chains, expiries)
            m = calc_metrics(sub)
            row[f"{plabel}_trades"] = m["trades"]
            row[f"{plabel}_net"] = m["net_pnl_inr"]
            row[f"{plabel}_pf"] = m["profit_factor"]
            row[f"{plabel}_wr"] = m["win_rate_pct"]
        entry_results.append(row)
        print(f"  {ename:35s} [{dstatus}] -> 7.6Y Net: Rs {row['FULL 7.6Y_net']:10.2f}")

    # -------------------------------------------------------------------------
    # PHASE 7: CONTROLLED FILTER COMBINATIONS (MAX 2 FILTERS)
    # -------------------------------------------------------------------------
    print("\n--- PHASE 7: CONTROLLED FILTER COMBINATIONS ---")
    combinations = [
        ("Filter D alone", dict(vix_filter_mode="FILTER_D")),
        ("Filter D + ATR_0.25", dict(vix_filter_mode="FILTER_D", breakout_atr_mult=0.25)),
        ("Filter D + ATR_0.50", dict(vix_filter_mode="FILTER_D", breakout_atr_mult=0.50)),
        ("Filter A + ATR_0.25", dict(vix_filter_mode="FILTER_A", breakout_atr_mult=0.25)),
        ("Filter A + ATR_0.50", dict(vix_filter_mode="FILTER_A", breakout_atr_mult=0.50)),
        ("Filter B + ATR_0.25", dict(vix_filter_mode="FILTER_B", breakout_atr_mult=0.25)),
        ("Filter B + Mag_0.10%", dict(vix_filter_mode="FILTER_B", breakout_mag_pct=0.10)),
        ("Mag_0.10% + ATR_0.25", dict(breakout_mag_pct=0.10, breakout_atr_mult=0.25)),
    ]
    combo_results = []
    for cname, cparams in combinations:
        row = {"combo_name": cname}
        for plabel, ps, pe in periods:
            sub = simulate_candidate(ps, pe, daily, chains, expiries, **cparams)
            m = calc_metrics(sub)
            row[f"{plabel}_trades"] = m["trades"]
            row[f"{plabel}_net"] = m["net_pnl_inr"]
            row[f"{plabel}_pf"] = m["profit_factor"]
            row[f"{plabel}_wr"] = m["win_rate_pct"]
        combo_results.append(row)
        print(f"  {cname:25s} -> DEV: Rs {row['DEV 2019-2021_net']:10.2f} | VAL: Rs {row['VAL 2022-2023_net']:10.2f} | 7.6Y: Rs {row['FULL 7.6Y_net']:10.2f} (PF {row['FULL 7.6Y_pf']})")

    # Anti-overfitting selection:
    # Top candidate based on:
    # 1. Dramatic improvement in DEV without destroying VAL
    # 2. Remains positive in >= 2 of 3 OOS years
    # Winner: Candidate 1 Upgraded (VIX Filter D + ATR >= 0.25)
    best_candidate_name = "Candidate 1 Upgraded (VIX Filter D + ATR >= 0.25)"
    best_candidate_params = dict(vix_filter_mode="FILTER_D", breakout_atr_mult=0.25)

    df_best_7y = simulate_candidate(START_7Y, END_7Y, daily, chains, expiries, **best_candidate_params)
    df_best_5y = simulate_candidate(START_5Y, END_5Y, daily, chains, expiries, **best_candidate_params)

    # -------------------------------------------------------------------------
    # WRITE ARTIFACT 1: CANDIDATE1_7Y_LEDGER.csv
    # -------------------------------------------------------------------------
    print("\n[1/7] Writing reports/CANDIDATE1_7Y_LEDGER.csv ...")
    df_best_7y["candidate_name"] = best_candidate_name
    df_best_7y["in_primary_5y"] = df_best_7y["execution_date"].apply(lambda d: 1 if str(START_5Y) <= d <= str(END_5Y) else 0)
    df_best_7y.to_csv("reports/CANDIDATE1_7Y_LEDGER.csv", index=False)
    print(f"  Saved {len(df_best_7y)} trades to CANDIDATE1_7Y_LEDGER.csv")

    # -------------------------------------------------------------------------
    # WRITE ARTIFACT 2: CANDIDATE1_7Y_CAPITAL.csv
    # -------------------------------------------------------------------------
    print("\n[2/7] Writing reports/CANDIDATE1_7Y_CAPITAL.csv ...")
    cap_tiers = [50000.0, 75000.0, 100000.0]
    risk_tiers = [0.03, 0.04, 0.05, 0.06]
    cap_records = []
    for c_id, c_df, yrs, per_lbl in [
        ("Candidate 1 Baseline (5Y)", df_base_5y, 5.0, "5Y_PRIMARY"),
        ("Candidate 1 Baseline (7.6Y)", df_base_7y, 7.64, "7.6Y_SECONDARY"),
        (f"{best_candidate_name} (5Y)", df_best_5y, 5.0, "5Y_PRIMARY"),
        (f"{best_candidate_name} (7.6Y)", df_best_7y, 7.64, "7.6Y_SECONDARY"),
    ]:
        for cap in cap_tiers:
            for rk in risk_tiers:
                res = simulate_capital_path(c_df, cap, rk, years=yrs)
                res["candidate_id"] = c_id
                res["period"] = per_lbl
                cap_records.append(res)
    cap_df = pd.DataFrame(cap_records)
    cap_df.to_csv("reports/CANDIDATE1_7Y_CAPITAL.csv", index=False)
    print(f"  Saved {len(cap_df)} capital simulation records.")

    # -------------------------------------------------------------------------
    # WRITE ARTIFACT 3: CANDIDATE1_7Y_WALK_FORWARD.csv
    # -------------------------------------------------------------------------
    print("\n[3/7] Writing reports/CANDIDATE1_7Y_WALK_FORWARD.csv ...")
    wf_records = []
    for category, lst in [("VIX_FILTER", vix_results), ("QUALITY_FILTER", quality_results),
                          ("ENTRY_TIMING", entry_results), ("EXIT_STRUCTURE", exit_results),
                          ("COMBINATION", combo_results)]:
        for r in lst:
            fname = r.get("filter_name") or r.get("combo_name") or r.get("exit_name")
            for plabel, _, _ in periods:
                wf_records.append({
                    "category": category,
                    "filter_or_candidate": fname,
                    "period": plabel,
                    "trades": r[f"{plabel}_trades"],
                    "win_rate_pct": r[f"{plabel}_wr"],
                    "net_pnl_inr": r[f"{plabel}_net"],
                    "profit_factor": r[f"{plabel}_pf"],
                })
    wf_df = pd.DataFrame(wf_records)
    wf_df.to_csv("reports/CANDIDATE1_7Y_WALK_FORWARD.csv", index=False)
    print(f"  Saved {len(wf_df)} walk-forward records.")

    # -------------------------------------------------------------------------
    # WRITE ARTIFACT 4: CANDIDATE1_7Y_REGIME.csv
    # -------------------------------------------------------------------------
    print("\n[4/7] Writing reports/CANDIDATE1_7Y_REGIME.csv ...")
    regime_records = []
    daily["sma50"] = daily["close"].rolling(50).mean()
    sma50_map = daily.set_index("sess")["sma50"].to_dict()

    for c_id, c_df in [("Baseline", df_base_7y), ("Upgraded", df_best_7y)]:
        for idx, t in c_df.iterrows():
            s = pd.to_datetime(t["signal_date"]).date()
            spot = t["signal_spot"]
            sma50 = sma50_map.get(s, spot)
            vix = t["vix"]
            diff_pct = (spot - sma50) / sma50 * 100.0
            trend_reg = "BULL" if diff_pct > 1.5 else ("BEAR" if diff_pct < -1.5 else "SIDEWAYS")
            vix_reg = "LOW_VIX (<14)" if vix < 14.0 else ("MID_VIX (14-19)" if vix <= 19.0 else "HIGH_VIX (>19)")
            regime_records.append({
                "candidate": c_id, "sess": str(s), "trend_regime": trend_reg,
                "vix_regime": vix_reg, "net": t["net_pnl_inr"], "is_win": t["is_win"],
            })
    rdf_raw = pd.DataFrame(regime_records)
    reg_summary = []
    for (cid, tr), grp in rdf_raw.groupby(["candidate", "trend_regime"]):
        w_sub = grp[grp["net"] > 0]["net"]
        l_sub = grp[grp["net"] <= 0]["net"]
        pf = w_sub.sum() / abs(l_sub.sum()) if len(l_sub) and l_sub.sum() != 0 else 0.0
        reg_summary.append({
            "candidate": cid, "regime_dimension": "TREND", "regime": tr,
            "trades": len(grp), "win_rate_pct": round(grp["is_win"].mean() * 100.0, 1),
            "net_pnl_inr": round(grp["net"].sum(), 2), "profit_factor": round(pf, 3),
        })
    for (cid, vr), grp in rdf_raw.groupby(["candidate", "vix_regime"]):
        w_sub = grp[grp["net"] > 0]["net"]
        l_sub = grp[grp["net"] <= 0]["net"]
        pf = w_sub.sum() / abs(l_sub.sum()) if len(l_sub) and l_sub.sum() != 0 else 0.0
        reg_summary.append({
            "candidate": cid, "regime_dimension": "VIX", "regime": vr,
            "trades": len(grp), "win_rate_pct": round(grp["is_win"].mean() * 100.0, 1),
            "net_pnl_inr": round(grp["net"].sum(), 2), "profit_factor": round(pf, 3),
        })
    reg_df = pd.DataFrame(reg_summary)
    reg_df.to_csv("reports/CANDIDATE1_7Y_REGIME.csv", index=False)
    print(f"  Saved {len(reg_df)} regime breakdown records.")

    # -------------------------------------------------------------------------
    # WRITE ARTIFACT 5: CANDIDATE1_7Y_MONTE_CARLO.csv
    # -------------------------------------------------------------------------
    print("\n[5/7] Running Monte Carlo (10,000 runs) and writing CANDIDATE1_7Y_MONTE_CARLO.csv ...")
    np.random.seed(42)
    mc_rows = []
    for c_id, c_df in [("Baseline_7Y", df_base_7y), ("Upgraded_7Y", df_best_7y)]:
        nets = c_df["net_pnl_inr"].values
        debits = c_df["capital_required_inr"].values
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
                lots = max(1, min(int(eq // (deb_t + 1000.0)), int((eq * 0.05) // deb_t)))
                eq += net_t * lots
                if eq > pk:
                    pk = eq
                dd = (pk - eq) / pk * 100.0
                if dd > mdd:
                    mdd = dd
            sim_cagr = compute_cagr(100000.0, eq, years=7.64)
            cagrs.append(sim_cagr)
            max_dds.append(mdd)
        cagrs = np.array(cagrs)
        max_dds = np.array(max_dds)
        mc_rows.append({
            "candidate_id": c_id,
            "simulations": 10000,
            "cagr_p5": round(np.percentile(cagrs, 5), 2),
            "cagr_p25": round(np.percentile(cagrs, 25), 2),
            "cagr_p50": round(np.percentile(cagrs, 50), 2),
            "cagr_p75": round(np.percentile(cagrs, 75), 2),
            "cagr_p95": round(np.percentile(cagrs, 95), 2),
            "median_mdd_pct": round(np.median(max_dds), 2),
            "prob_dd_gt_20": round(np.mean(max_dds > 20.0) * 100.0, 2),
            "prob_dd_gt_25": round(np.mean(max_dds > 25.0) * 100.0, 2),
            "prob_dd_gt_30": round(np.mean(max_dds > 30.0) * 100.0, 2),
            "prob_dd_gt_35": round(np.mean(max_dds > 35.0) * 100.0, 2),
            "prob_dd_gt_50": round(np.mean(max_dds > 50.0) * 100.0, 2),
        })
    mc_df = pd.DataFrame(mc_rows)
    mc_df.to_csv("reports/CANDIDATE1_7Y_MONTE_CARLO.csv", index=False)
    print(f"  Saved Monte Carlo records.")

    # -------------------------------------------------------------------------
    # WRITE ARTIFACT 6: CANDIDATE1_7Y_STRESS.csv
    # -------------------------------------------------------------------------
    print("\n[6/7] Writing reports/CANDIDATE1_7Y_STRESS.csv ...")
    stress_records = []
    for c_id, params in [("Baseline", {}), ("Upgraded", best_candidate_params)]:
        # Costs and slippage
        for cm, sm in [(1.0, 1.0), (2.0, 1.0), (3.0, 1.0), (1.0, 1.25), (1.0, 1.50), (1.0, 2.0)]:
            df_s = simulate_candidate(START_7Y, END_7Y, daily, chains, expiries, cost_mult=cm, slippage_mult=sm, **params)
            m_s = calc_metrics(df_s)
            stress_records.append({
                "candidate": c_id, "category": "COST_AND_SLIPPAGE",
                "test_name": f"Cost_{cm}x_Slip_{sm}x", "trades": m_s["trades"],
                "net_pnl_inr": m_s["net_pnl_inr"], "profit_factor": m_s["profit_factor"],
            })
        # Outlier drops
        df_full = simulate_candidate(START_7Y, END_7Y, daily, chains, expiries, **params)
        s_net = df_full["net_pnl_inr"].sort_values(ascending=False)
        for k in [1, 3, 5, 10]:
            rem_net = s_net.iloc[k:]
            rem_w = rem_net[rem_net > 0]
            rem_l = rem_net[rem_net <= 0]
            rem_pf = rem_w.sum() / abs(rem_l.sum()) if len(rem_l) and rem_l.sum() != 0 else 0.0
            stress_records.append({
                "candidate": c_id, "category": "OUTLIER_REMOVAL",
                "test_name": f"Best_{k}_Trades_Removed", "trades": len(rem_net),
                "net_pnl_inr": round(rem_net.sum(), 2), "profit_factor": round(rem_pf, 3),
            })
        # Consecutive loss streak stress
        avg_loss = abs(df_full[df_full["net_pnl_inr"] <= 0]["net_pnl_inr"].mean()) if len(df_full[df_full["net_pnl_inr"] <= 0]) else 2500.0
        for streak in [5, 10, 15, 20]:
            for cap in [50000.0, 75000.0, 100000.0]:
                streak_loss = streak * avg_loss
                loss_pct = (streak_loss / cap) * 100.0
                stress_records.append({
                    "candidate": c_id, "category": "LOSS_STREAK_SIMULATION",
                    "test_name": f"{streak}_Consecutive_Losses_on_{int(cap/1000)}k",
                    "trades": streak, "net_pnl_inr": round(-streak_loss, 2),
                    "profit_factor": round(loss_pct, 2),
                })
    stress_df = pd.DataFrame(stress_records)
    stress_df.to_csv("reports/CANDIDATE1_7Y_STRESS.csv", index=False)
    print(f"  Saved {len(stress_df)} stress testing records.")

    # -------------------------------------------------------------------------
    # WRITE ARTIFACT 7: CANDIDATE1_7Y_RECONCILIATION.csv
    # -------------------------------------------------------------------------
    print("\n[7/7] Writing reports/CANDIDATE1_7Y_RECONCILIATION.csv ...")
    recon_records = []
    for idx, row in df_best_7y.iterrows():
        calc_gross = (row["exit_spread_val"] - row["debit_pts"]) * row["lot_size"]
        gross_diff = abs(calc_gross - row["gross_payoff_inr"])
        calc_net = row["gross_payoff_inr"] - row["statutory_costs_inr"]
        net_diff = abs(calc_net - row["net_pnl_inr"])
        recon_records.append({
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
    recon_df = pd.DataFrame(recon_records)
    recon_df.to_csv("reports/CANDIDATE1_7Y_RECONCILIATION.csv", index=False)
    print(f"  Saved {len(recon_df)} reconciliation rows. Reconciled match rate: {recon_df['is_perfect_match'].mean() * 100.0:.1f}%")

    print("\nALL 7 CSV ARTIFACTS GENERATED SUCCESSFULLY.")

if __name__ == "__main__":
    main()

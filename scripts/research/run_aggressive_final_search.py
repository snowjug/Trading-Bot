#!/usr/bin/env python3
"""
scripts/research/run_aggressive_final_search.py

FINAL AGGRESSIVE MONEY SEARCH — 5-YEAR FORENSIC RESEARCH ENGINE
Evaluates high-risk-tolerance, positive-skew, defined-risk derivative strategies
on NIFTY (2019-01-01 -> 2026-09-18).

Generates all 8 forensic CSV artifacts in reports/ and logs complete diagnostics.
"""

import os, sys
from datetime import date
from typing import List, Dict, Any, Tuple
import pandas as pd
import numpy as np

# Add project root to sys.path
sys.path.insert(0, os.path.abspath("."))

from src.research.bot1_condor_real import (
    ChainIndex, load_bhavcopy_store, weekly_expiry_calendar,
)
from scripts.research.weekly_premium_lab import daily_with_rsi
from scripts.research.run_final_mission_cagr_test import compute_cagr

START_5Y = date(2021, 9, 19)
END_5Y = date(2026, 9, 18)
START_7Y = date(2019, 1, 1)

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
    brokerage = 40.0  # Rs 20 per leg entry (exit is cash settlement at expiry = 0 brokerage)
    stt_rate_sell = 0.00100 if entry_dt >= date(2024, 10, 1) else 0.000625
    stt = sell_fill * qty * stt_rate_sell
    if buy_exit > 0:
        stt += buy_exit * qty * 0.00125  # STT on exercise
    stamp = buy_fill * qty * 0.00003
    turnover = (buy_fill + sell_fill + buy_exit + sell_exit) * qty
    exch = turnover * 0.00050
    sebi = turnover * 0.000001
    gst = (brokerage + exch + sebi) * 0.18
    total_statutory = (brokerage + stt + stamp + exch + sebi + gst) * cost_mult
    return total_statutory

def simulate_strategy(
    start_dt: date,
    end_dt: date,
    lookback: int,
    wing_width: float,
    strike_offset: float,
    vix_max: float,
    daily: pd.DataFrame,
    chains: ChainIndex,
    expiries: List[date],
    cost_mult: float = 1.0,
    slippage_mult: float = 1.0,
) -> pd.DataFrame:
    dpos = {v: i for i, v in enumerate(daily["sess"])}
    sess_list = list(daily["sess"])
    spos = {v: i for i, v in enumerate(sess_list)}
    index_close = dict(zip(daily["sess"], daily["close"].astype(float)))
    
    daily_c = daily.copy()
    daily_c["roll_hi"] = daily_c["close"].shift(1).rolling(lookback).max()
    daily_c["roll_lo"] = daily_c["close"].shift(1).rolling(lookback).min()
    hi_map = daily_c.set_index("sess")["roll_hi"].to_dict()
    lo_map = daily_c.set_index("sess")["roll_lo"].to_dict()
    
    sessions = [d for d in sess_list if start_dt <= d <= end_dt]
    trades = []
    used_expiries = set()
    
    for sess in sessions:
        i = dpos.get(sess)
        if i is None or i < 60:
            continue
        prior = daily_c.iloc[i - 1]
        vix = float(prior["vix"])
        if vix >= vix_max:
            continue
            
        spot = float(daily_c.iloc[i]["close"])
        roll_hi = hi_map.get(sess)
        roll_lo = lo_map.get(sess)
        if roll_hi is None or roll_lo is None or np.isnan(roll_hi) or np.isnan(roll_lo):
            continue
            
        is_fresh_bull = (spot > roll_hi) and (float(prior["close"]) <= hi_map.get(daily_c.iloc[i-1]["sess"], spot))
        is_fresh_bear = (spot < roll_lo) and (float(prior["close"]) >= lo_map.get(daily_c.iloc[i-1]["sess"], spot))
        
        if not (is_fresh_bull or is_fresh_bear):
            continue
            
        nxt = [e for e in expiries if e > sess]
        if not nxt:
            continue
        expiry = nxt[0]
        if expiry in used_expiries:
            continue
            
        ep, cp = spos.get(expiry), spos.get(sess)
        if ep is None or cp is None:
            continue
        dte_sessions = ep - cp
        if not (2 <= dte_sessions <= 5):
            continue
            
        settle = chains.settlement(expiry, index_close)
        if settle is None:
            continue
        chain = chains.chain(sess, expiry)
        if chain.empty:
            continue
            
        step = 50.0
        atm_k = round(spot / step) * step
        w = wing_width
        
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
        if int(rr_buy["TtlTradgVol"]) <= 0 or float(rr_buy["ClsPric"]) <= 0:
            continue
        if int(rr_sell["TtlTradgVol"]) <= 0 or float(rr_sell["ClsPric"]) <= 0:
            continue
            
        q = get_lot_size(sess, rr_buy)
        buy_px = float(rr_buy["ClsPric"])
        sell_px = float(rr_sell["ClsPric"])
        
        # Apply realistic execution slippage
        base_slip = 0.10 * slippage_mult
        buy_fill = buy_px + base_slip
        sell_fill = max(0.05, sell_px - base_slip)
        debit_pts = buy_fill - sell_fill
        
        if debit_pts <= 0 or debit_pts >= 0.65 * w:
            continue
            
        if spread_type == "BULL_CALL":
            buy_exit = max(0.0, settle - buy_k)
            sell_exit = max(0.0, settle - sell_k)
        else:
            buy_exit = max(0.0, buy_k - settle)
            sell_exit = max(0.0, sell_k - settle)
            
        gross_pts = (buy_exit - sell_exit) - debit_pts
        gross = gross_pts * q
        
        statutory_costs = compute_statutory_costs(sess, buy_fill, sell_fill, buy_exit, sell_exit, q, cost_mult=cost_mult)
        net = gross - statutory_costs
        
        used_expiries.add(expiry)
        trades.append({
            "sess": sess, "expiry": expiry, "year": sess.year,
            "spot": spot, "settle": settle, "vix": vix,
            "type": spread_type, "buy_k": buy_k, "sell_k": sell_k,
            "buy_fill": round(buy_fill, 2), "sell_fill": round(sell_fill, 2),
            "debit_pts": round(debit_pts, 2), "lot": q,
            "capital_req": round(debit_pts * q, 2),
            "gross_pts": round(gross_pts, 2),
            "gross": round(gross, 2),
            "costs": round(statutory_costs, 2),
            "net": round(net, 2),
            "is_win": 1 if net > 0 else 0,
        })
        
    df = pd.DataFrame(trades)
    if not df.empty:
        df["cum_net"] = df["net"].cumsum()
    return df

def run_capital_simulation(trades: List[Dict[str, Any]], start_cap: float, risk_pct: float, years: float = 5.0):
    equity = float(start_cap)
    peak = equity
    max_dd = 0.0
    skips = 0
    losing_streak = 0
    max_losing_streak = 0
    
    for t in trades:
        debit = t["capital_req"]
        if debit <= 0:
            continue
        max_affordable = int(equity // (debit + 1000.0))
        lots_by_risk = int((equity * risk_pct) // debit)
        lots = max(1, min(max_affordable, lots_by_risk))
        
        if lots < 1 or equity < debit:
            skips += 1
            continue
            
        net_trade = t["net"] * lots
        equity += net_trade
        
        if net_trade <= 0:
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
    print("=" * 70)
    print("STARTING FINAL AGGRESSIVE MONEY SEARCH FORENSIC AUDIT")
    print("=" * 70)
    
    daily = daily_with_rsi()
    store = load_bhavcopy_store()
    chains = ChainIndex(store)
    expiries = weekly_expiry_calendar(store)
    
    candidates = [
        ("Candidate A", "10D Breakout ATM Debit Spread (W200)", 10, 200.0, 0.0, 24.0),
        ("Candidate B", "10D Breakout Convex OTM Debit Spread (W250, Off50)", 10, 250.0, 50.0, 24.0),
        ("Candidate C", "10D Breakout Squeeze Debit Spread (W150)", 10, 150.0, 0.0, 24.0),
    ]
    
    os.makedirs("reports", exist_ok=True)
    
    # 1. TRADE LEDGER
    print("\n[1/8] Generating AGGRESSIVE_TRADE_LEDGER.csv ...")
    all_trades_records = []
    candidate_dfs_5y = {}
    candidate_dfs_7y = {}
    
    for cid, cname, lb, w, off, vx in candidates:
        df_5y = simulate_strategy(START_5Y, END_5Y, lb, w, off, vx, daily, chains, expiries)
        df_7y = simulate_strategy(START_7Y, END_5Y, lb, w, off, vx, daily, chains, expiries)
        candidate_dfs_5y[cid] = df_5y
        candidate_dfs_7y[cid] = df_7y
        
        for r in df_7y.to_dict("records"):
            r["candidate_id"] = cid
            r["candidate_name"] = cname
            r["in_primary_5y"] = 1 if (r["sess"] >= START_5Y and r["sess"] <= END_5Y) else 0
            all_trades_records.append(r)
            
    ledger_df = pd.DataFrame(all_trades_records)
    ledger_df.to_csv("reports/AGGRESSIVE_TRADE_LEDGER.csv", index=False)
    print(f"  Saved {len(ledger_df)} trade records.")
    
    # 2. CAPITAL SIMULATION
    print("\n[2/8] Generating AGGRESSIVE_CAPITAL_SIMULATION.csv ...")
    cap_records = []
    capital_tiers = [50000.0, 75000.0, 100000.0, 150000.0, 200000.0]
    risk_tiers = [0.01, 0.02, 0.03, 0.05, 0.08, 0.10]
    
    for cid, cname, lb, w, off, vx in candidates:
        df_5y = candidate_dfs_5y[cid]
        trds_5y = df_5y.to_dict("records")
        for cap in capital_tiers:
            for rk in risk_tiers:
                res = run_capital_simulation(trds_5y, cap, rk, years=5.0)
                res["candidate_id"] = cid
                res["candidate_name"] = cname
                res["period"] = "5Y_PRIMARY"
                cap_records.append(res)
                
        df_7y = candidate_dfs_7y[cid]
        trds_7y = df_7y.to_dict("records")
        for cap in capital_tiers:
            for rk in risk_tiers:
                res = run_capital_simulation(trds_7y, cap, rk, years=7.64)
                res["candidate_id"] = cid
                res["candidate_name"] = cname
                res["period"] = "7.6Y_SECONDARY"
                cap_records.append(res)
                
    cap_df = pd.DataFrame(cap_records)
    cap_df.to_csv("reports/AGGRESSIVE_CAPITAL_SIMULATION.csv", index=False)
    print(f"  Saved {len(cap_df)} capital simulation tiers.")
    
    # 3. YEARLY RESULTS
    print("\n[3/8] Generating AGGRESSIVE_YEARLY_RESULTS.csv ...")
    yearly_records = []
    for cid, cname, lb, w, off, vx in candidates:
        df_7y = candidate_dfs_7y[cid]
        for yr, grp in df_7y.groupby("year"):
            w_sub = grp[grp["net"] > 0]["net"]
            l_sub = grp[grp["net"] <= 0]["net"]
            wr = len(w_sub) / len(grp) * 100.0 if len(grp) else 0.0
            avg_w = w_sub.mean() if len(w_sub) else 0.0
            avg_l = l_sub.mean() if len(l_sub) else 0.0
            payoff = abs(avg_w / avg_l) if avg_l != 0 else 0.0
            pf = w_sub.sum() / abs(l_sub.sum()) if len(l_sub) and l_sub.sum() != 0 else 0.0
            net_yr = grp["net"].sum()
            eq_yr = grp["net"].cumsum()
            dd_yr = float((eq_yr - eq_yr.cummax()).min()) if len(eq_yr) else 0.0
            
            yearly_records.append({
                "candidate_id": cid,
                "candidate_name": cname,
                "year": yr,
                "trades": len(grp),
                "win_rate_pct": round(wr, 1),
                "avg_win_inr": round(avg_w, 2),
                "avg_loss_inr": round(avg_l, 2),
                "payoff_ratio": round(payoff, 2),
                "profit_factor": round(pf, 3),
                "net_pnl_inr": round(net_yr, 2),
                "max_drawdown_inr": round(dd_yr, 2),
            })
    yearly_df = pd.DataFrame(yearly_records)
    yearly_df.to_csv("reports/AGGRESSIVE_YEARLY_RESULTS.csv", index=False)
    print(f"  Saved {len(yearly_df)} yearly breakdown rows.")
    
    # 4. REGIME RESULTS
    print("\n[4/8] Generating AGGRESSIVE_REGIME_RESULTS.csv ...")
    daily_idx = daily.set_index("sess")
    regime_records = []
    for cid, cname, lb, w, off, vx in candidates:
        df_7y = candidate_dfs_7y[cid]
        for _, t in df_7y.iterrows():
            s = t["sess"]
            row = daily_idx.loc[s]
            spot = float(row["close"])
            sma50 = float(daily_idx["close"].loc[:s].iloc[-50:].mean())
            vix = float(row["vix"])
            diff_pct = (spot - sma50) / sma50 * 100.0
            trend_reg = "BULL" if diff_pct > 1.5 else ("BEAR" if diff_pct < -1.5 else "SIDEWAYS")
            vix_reg = "LOW_VIX (<14)" if vix < 14.0 else ("MID_VIX (14-19)" if vix <= 19.0 else "HIGH_VIX (>19)")
            
            regime_records.append({
                "candidate_id": cid,
                "candidate_name": cname,
                "sess": s,
                "trend_regime": trend_reg,
                "vix_regime": vix_reg,
                "net": t["net"],
                "is_win": t["is_win"],
            })
    rdf_raw = pd.DataFrame(regime_records)
    reg_summary = []
    for (cid, tr), grp in rdf_raw.groupby(["candidate_id", "trend_regime"]):
        w_sub = grp[grp["net"] > 0]["net"]
        l_sub = grp[grp["net"] <= 0]["net"]
        pf = w_sub.sum() / abs(l_sub.sum()) if len(l_sub) and l_sub.sum() != 0 else 0.0
        reg_summary.append({
            "candidate_id": cid, "regime_type": "TREND", "regime": tr,
            "trades": len(grp), "win_rate_pct": round(grp["is_win"].mean() * 100.0, 1),
            "net_pnl_inr": round(grp["net"].sum(), 2), "profit_factor": round(pf, 3),
        })
    for (cid, vr), grp in rdf_raw.groupby(["candidate_id", "vix_regime"]):
        w_sub = grp[grp["net"] > 0]["net"]
        l_sub = grp[grp["net"] <= 0]["net"]
        pf = w_sub.sum() / abs(l_sub.sum()) if len(l_sub) and l_sub.sum() != 0 else 0.0
        reg_summary.append({
            "candidate_id": cid, "regime_type": "VIX", "regime": vr,
            "trades": len(grp), "win_rate_pct": round(grp["is_win"].mean() * 100.0, 1),
            "net_pnl_inr": round(grp["net"].sum(), 2), "profit_factor": round(pf, 3),
        })
    reg_df = pd.DataFrame(reg_summary)
    reg_df.to_csv("reports/AGGRESSIVE_REGIME_RESULTS.csv", index=False)
    print(f"  Saved {len(reg_df)} regime analysis rows.")
    
    # 5. WALK-FORWARD RESULTS
    print("\n[5/8] Generating AGGRESSIVE_WALK_FORWARD.csv ...")
    wf_periods = [
        ("Train 2021-2022", date(2021, 9, 19), date(2022, 12, 31)),
        ("Test 2023", date(2023, 1, 1), date(2023, 12, 31)),
        ("Test 2024", date(2024, 1, 1), date(2024, 12, 31)),
        ("Test 2025", date(2025, 1, 1), date(2025, 12, 31)),
        ("Test 2026", date(2026, 1, 1), date(2026, 9, 18)),
    ]
    wf_records = []
    for cid, cname, lb, w, off, vx in candidates:
        for lbl, s_dt, e_dt in wf_periods:
            df_slice = simulate_strategy(s_dt, e_dt, lb, w, off, vx, daily, chains, expiries)
            w_sub = df_slice[df_slice["net"] > 0]["net"]
            l_sub = df_slice[df_slice["net"] <= 0]["net"]
            wr = len(w_sub) / len(df_slice) * 100.0 if len(df_slice) else 0.0
            avg_w = w_sub.mean() if len(w_sub) else 0.0
            avg_l = l_sub.mean() if len(l_sub) else 0.0
            payoff = abs(avg_w / avg_l) if avg_l != 0 else 0.0
            pf = w_sub.sum() / abs(l_sub.sum()) if len(l_sub) and l_sub.sum() != 0 else 0.0
            wf_records.append({
                "candidate_id": cid, "candidate_name": cname, "period_label": lbl,
                "start_date": str(s_dt), "end_date": str(e_dt), "trades": len(df_slice),
                "win_rate_pct": round(wr, 1), "avg_win_inr": round(avg_w, 2),
                "avg_loss_inr": round(avg_l, 2), "payoff_ratio": round(payoff, 2),
                "profit_factor": round(pf, 3), "net_pnl_inr": round(df_slice["net"].sum(), 2),
            })
    wf_df = pd.DataFrame(wf_records)
    wf_df.to_csv("reports/AGGRESSIVE_WALK_FORWARD.csv", index=False)
    print(f"  Saved {len(wf_df)} walk-forward slices.")
    
    # 6. MONTE CARLO RESULTS (10,000 simulations)
    print("\n[6/8] Generating AGGRESSIVE_MONTE_CARLO.csv (10,000 iterations) ...")
    mc_records = []
    np.random.seed(42)
    n_sims = 10000
    
    for cid, cname, lb, w, off, vx in candidates:
        df_5y = candidate_dfs_5y[cid]
        trds_5y = df_5y.to_dict("records")
        trade_nets = [t["net"] for t in trds_5y]
        trade_debits = [t["capital_req"] for t in trds_5y]
        n_trd = len(trade_nets)
        
        sim_cagrs = []
        sim_dds = []
        
        for _ in range(n_sims):
            idx = np.random.choice(n_trd, size=n_trd, replace=True)
            equity = 100000.0
            peak = equity
            max_dd = 0.0
            for i in idx:
                deb = trade_debits[i]
                lots = max(1, min(int(equity // (deb + 1000.0)), int((equity * 0.05) // deb)))
                if lots < 1 or equity < deb: continue
                equity += trade_nets[i] * lots
                if equity > peak: peak = equity
                d = peak - equity
                if d > max_dd: max_dd = d
            cagr = compute_cagr(100000.0, equity, 5.0)
            dd_pct = (max_dd / peak) * 100.0 if peak > 0 else 0.0
            sim_cagrs.append(cagr)
            sim_dds.append(dd_pct)
            
        cagrs = np.array(sim_cagrs)
        dds = np.array(sim_dds)
        
        mc_records.append({
            "candidate_id": cid, "candidate_name": cname, "capital_tested": 100000.0, "risk_pct": 0.05,
            "cagr_5th_pct": round(np.percentile(cagrs, 5), 2),
            "cagr_25th_pct": round(np.percentile(cagrs, 25), 2),
            "cagr_50th_pct_median": round(np.percentile(cagrs, 50), 2),
            "cagr_75th_pct": round(np.percentile(cagrs, 75), 2),
            "cagr_95th_pct": round(np.percentile(cagrs, 95), 2),
            "dd_5th_pct": round(np.percentile(dds, 5), 2),
            "dd_25th_pct": round(np.percentile(dds, 25), 2),
            "dd_50th_pct_median": round(np.percentile(dds, 50), 2),
            "dd_75th_pct": round(np.percentile(dds, 75), 2),
            "dd_95th_pct": round(np.percentile(dds, 95), 2),
            "prob_dd_gt_20pct": round((dds > 20.0).mean() * 100.0, 2),
            "prob_dd_gt_30pct": round((dds > 30.0).mean() * 100.0, 2),
            "prob_dd_gt_35pct": round((dds > 35.0).mean() * 100.0, 2),
            "prob_dd_gt_50pct": round((dds > 50.0).mean() * 100.0, 2),
        })
    mc_df = pd.DataFrame(mc_records)
    mc_df.to_csv("reports/AGGRESSIVE_MONTE_CARLO.csv", index=False)
    print(f"  Saved {len(mc_df)} Monte Carlo candidate profiles.")
    
    # 7. STRESS RESULTS (Cost, Slippage, Outliers, Loss streaks)
    print("\n[7/8] Generating AGGRESSIVE_STRESS_RESULTS.csv ...")
    stress_records = []
    
    for cid, cname, lb, w, off, vx in candidates:
        # Cost and slippage stress
        for cm, sm in [(1.0, 1.0), (2.0, 1.0), (3.0, 1.0), (1.0, 1.25), (1.0, 1.50), (1.0, 2.0)]:
            df_stress = simulate_strategy(START_5Y, END_5Y, lb, w, off, vx, daily, chains, expiries, cost_mult=cm, slippage_mult=sm)
            w_sub = df_stress[df_stress["net"] > 0]["net"]
            l_sub = df_stress[df_stress["net"] <= 0]["net"]
            pf_s = w_sub.sum() / abs(l_sub.sum()) if len(l_sub) and l_sub.sum() != 0 else 0.0
            stress_records.append({
                "candidate_id": cid, "test_category": "COST_AND_SLIPPAGE",
                "test_name": f"Cost_x{cm}_Slip_x{sm}", "trades": len(df_stress),
                "net_pnl_inr": round(df_stress["net"].sum(), 2), "profit_factor": round(pf_s, 3),
            })
            
        # Outlier removal
        df_base = candidate_dfs_5y[cid]
        sorted_net = df_base["net"].sort_values(ascending=False)
        for k in [1, 3, 5, 10]:
            rem_net = sorted_net.iloc[k:]
            rem_wins = rem_net[rem_net > 0]
            rem_losses = rem_net[rem_net <= 0]
            rem_pf = rem_wins.sum() / abs(rem_losses.sum()) if len(rem_losses) and rem_losses.sum() != 0 else 0.0
            stress_records.append({
                "candidate_id": cid, "test_category": "OUTLIER_REMOVAL",
                "test_name": f"Best_{k}_Trades_Removed", "trades": len(rem_net),
                "net_pnl_inr": round(rem_net.sum(), 2), "profit_factor": round(rem_pf, 3),
            })
            
        # Synthetic loss streak impact
        avg_loss = abs(df_base[df_base["net"] <= 0]["net"].mean())
        for streak in [5, 10, 15, 20]:
            for cap in [50000.0, 75000.0, 100000.0]:
                streak_loss = streak * avg_loss
                loss_pct = (streak_loss / cap) * 100.0
                stress_records.append({
                    "candidate_id": cid, "test_category": "LOSS_STREAK_SIMULATION",
                    "test_name": f"{streak}_Consecutive_Losses_on_{int(cap/1000)}k",
                    "trades": streak, "net_pnl_inr": round(-streak_loss, 2),
                    "profit_factor": round(loss_pct, 2), # stored as loss pct of cap
                })
    stress_df = pd.DataFrame(stress_records)
    stress_df.to_csv("reports/AGGRESSIVE_STRESS_RESULTS.csv", index=False)
    print(f"  Saved {len(stress_df)} stress test rows.")
    
    # 8. P&L RECONCILIATION
    print("\n[8/8] Generating AGGRESSIVE_PNL_RECONCILIATION.csv ...")
    recon_records = []
    for cid, cname, lb, w, off, vx in candidates:
        df_recon = candidate_dfs_5y[cid]
        for idx, row in df_recon.iterrows():
            engine_gross = row["gross"]
            manual_gross = round(row["gross_pts"] * row["lot"], 2)
            diff = round(abs(engine_gross - manual_gross), 4)
            recon_records.append({
                "candidate_id": cid,
                "sess": str(row["sess"]),
                "expiry": str(row["expiry"]),
                "type": row["type"],
                "engine_gross": engine_gross,
                "manual_gross": manual_gross,
                "discrepancy": diff,
                "engine_net": row["net"],
            })
    recon_df = pd.DataFrame(recon_records)
    recon_df.to_csv("reports/AGGRESSIVE_PNL_RECONCILIATION.csv", index=False)
    print(f"  Saved {len(recon_df)} P&L reconciliation entries.")
    
    print("\n" + "=" * 70)
    print("ALL 8 FORENSIC CSV ARTIFACTS GENERATED SUCCESSFULLY IN reports/")
    print("=" * 70)

if __name__ == "__main__":
    main()

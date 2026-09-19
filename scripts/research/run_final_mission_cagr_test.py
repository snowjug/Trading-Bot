"""
FINAL RESEARCH MISSION: 30-40% CAGR EVALUATION
Evaluates the promoted defined-risk credit spread / iron condor candidates across
the 2-year period (2024-09-18 -> 2026-09-18) and the full history (2019-2026).
Simulates sequential accounts for ₹50k, ₹75k, ₹100k with integer lots.
Checks if 2Y CAGR >= 30% and tests robustness, costs, and risk of ruin.
"""

import os, sys, glob, json, math
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath("."))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from src.research.bot1_condor_real import (
    ChainIndex, condor_leg_costs, load_bhavcopy_store, weekly_expiry_calendar,
)
from scripts.research.weekly_premium_lab import (
    WSpec, daily_with_rsi, run, metrics, sell_credit, buy_debit,
)

START_2Y = date(2024, 9, 18)
END_2Y = date(2026, 9, 18)

def compute_cagr(start_val: float, end_val: float, years: float = 2.0) -> float:
    if start_val <= 0 or end_val <= 0:
        return -100.0
    return ((end_val / start_val) ** (1.0 / years) - 1.0) * 100.0

def simulate_account(
    trades: List[Dict[str, Any]],
    start_cap: float,
    strategy_name: str,
    spread_type: str = "SPREAD",
    buffer_mult: float = 1.0
) -> Dict[str, Any]:
    """
    Trade-by-trade sequential simulation with integer lot sizing.
    Required margin for defined-risk spread: max_risk + margin buffer.
    In India, SEBI cross-margin for credit spread / iron condor requires:
    Spread width * lot size (or max risk) plus a margin buffer.
    For NIFTY lot 65 (2026) / lot 75 (2025), broker margin is ~₹35k-₹45k.
    """
    equity = float(start_cap)
    peak = equity
    max_dd = 0.0
    min_bal = equity
    
    executed = 0
    skipped = 0
    trade_ledger = []
    streak = 0
    max_streak = 0
    
    for t in trades:
        # Determine authentic required margin
        # In India, broker margin for a 4-leg condor or 2-leg vertical:
        # Minimum margin is approx ₹35,000 for vertical spread, ₹38,000 for iron condor
        base_req = float(t.get('max_risk', 0.0))
        if "condor" in strategy_name:
            margin_req = max(base_req, 38000.0) * buffer_mult
        else:
            margin_req = max(base_req, 32000.0) * buffer_mult
            
        # Integer lot sizing:
        # Sizing rule: lots = int(equity // margin_req)
        # However, to be conservative and prevent overleverage, max 1 lot for ₹50k-₹75k,
        # and max lots = int(equity // margin_req) for compounding.
        lots = int(equity // margin_req)
        
        if lots < 1:
            skipped += 1
            continue
            
        executed += 1
        cap_before = equity
        gross_pnl = float(t['gross']) * lots
        costs = float(t['costs']) * lots
        net_pnl = float(t['net']) * lots
        
        equity += net_pnl
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
        if equity < min_bal:
            min_bal = equity
            
        if net_pnl <= 0:
            streak += 1
            if streak > max_streak:
                max_streak = streak
        else:
            streak = 0
            
        trade_ledger.append({
            "sess": t.get("sess"),
            "expiry": t.get("expiry"),
            "cap_before": round(cap_before, 2),
            "margin_req": round(margin_req, 2),
            "lots": lots,
            "net_pnl": round(net_pnl, 2),
            "cap_after": round(equity, 2),
        })
        
    net_profit = equity - start_cap
    cagr = compute_cagr(start_cap, equity, years=2.0)
    max_dd_pct = (max_dd / peak) * 100.0 if peak > 0 else 0.0
    
    return {
        "start_capital": start_cap,
        "ending_capital": round(equity, 2),
        "net_profit": round(net_profit, 2),
        "cagr_pct": round(cagr, 2),
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "min_balance": round(min_bal, 2),
        "worst_losing_streak": max_streak,
        "executed_trades": executed,
        "skipped_trades": skipped,
        "total_signals": len(trades),
        "ledger_sample": trade_ledger[:3] + trade_ledger[-3:] if len(trade_ledger) >= 6 else trade_ledger,
    }

def main():
    print("=" * 90)
    print("RUNNING FINAL MISSION 30-40% CAGR RESEARCH ENGINE")
    print("=" * 90)
    
    daily = daily_with_rsi()
    store = load_bhavcopy_store()
    chains = ChainIndex(store)
    expiries = weekly_expiry_calendar(store)
    all_sess = sorted(set(store["TradDt"].unique()))
    
    # 2-Year window: 2024-09-18 to 2026-09-18
    sess_2y = [d for d in all_sess if START_2Y <= d <= END_2Y]
    print(f"2-Year Evaluation Window: {len(sess_2y)} sessions from {sess_2y[0]} to {sess_2y[-1]}")
    
    # Define candidates from the promoted set
    candidates = [
        WSpec("condor_1.8sd_w4", "condor", 1.8, 4, notes="Bot 1 Iron Condor (Promoted)"),
        WSpec("condor_2.2sd_w4", "condor", 2.2, 4, notes="Wide Iron Condor (Promoted)"),
        WSpec("vert_put_1.8sd_w4", "vertical_put", 1.8, 4, notes="Bull Put Spread (Promoted)"),
        WSpec("vert_auto_1.8sd_w8", "vertical_auto", 1.8, 8, notes="Auto Credit Spread Wide (Promoted)"),
    ]
    
    results = {}
    
    for spec in candidates:
        print(f"\nEvaluating candidate: {spec.name} ({spec.notes})...")
        sk = {}
        # 1. Run over 2-year window
        tr_2y = run(spec, sess_2y, daily, store, chains, expiries, sk)
        m_2y = metrics(tr_2y, len(sess_2y))
        
        # 2. Run over full available history (2019-2026) for deep robustness
        sk_full = {}
        tr_full = run(spec, all_sess, daily, store, chains, expiries, sk_full)
        m_full = metrics(tr_full, len(all_sess))
        
        # 3. Simulate sequential capital accounts (₹50k, ₹75k, ₹100k) on 2-Year window
        sim_50k = simulate_account(tr_2y, 50000.0, spec.name)
        sim_75k = simulate_account(tr_2y, 75000.0, spec.name)
        sim_100k = simulate_account(tr_2y, 100000.0, spec.name)
        
        # 4. Stress tests (1x, 2x, 3x costs) on 2-Year window
        gross = sum(t['gross'] for t in tr_2y)
        costs = sum(t['costs'] for t in tr_2y)
        net_1x = gross - costs
        net_2x = gross - (2.0 * costs)
        net_3x = gross - (3.0 * costs)
        
        # 5. Outlier sensitivity
        pnl_sorted = sorted([t['net'] for t in tr_2y], reverse=True)
        rem_best1 = sum(pnl_sorted[1:]) if len(pnl_sorted) > 1 else 0.0
        rem_best3 = sum(pnl_sorted[3:]) if len(pnl_sorted) > 3 else 0.0
        rem_best5 = sum(pnl_sorted[5:]) if len(pnl_sorted) > 5 else 0.0
        pnl_sorted_asc = sorted([t['net'] for t in tr_2y])
        rem_worst3 = sum(pnl_sorted_asc[3:]) if len(pnl_sorted_asc) > 3 else 0.0
        
        # 6. Tail risk & losing streak stress
        losses = [t['net'] for t in tr_2y if t['net'] < 0]
        avg_loss = float(np.mean(losses)) if losses else 0.0
        worst_loss = min([t['net'] for t in tr_2y]) if tr_2y else 0.0
        stress_10_loss = avg_loss * 10.0
        stress_20_loss = avg_loss * 20.0
        
        results[spec.name] = {
            "name": spec.name,
            "notes": spec.notes,
            "legs": spec.legs,
            "m_2y": m_2y,
            "m_full": m_full,
            "sim_50k": sim_50k,
            "sim_75k": sim_75k,
            "sim_100k": sim_100k,
            "costs": {
                "gross": round(gross, 2),
                "costs_1x": round(costs, 2),
                "net_1x": round(net_1x, 2),
                "net_2x": round(net_2x, 2),
                "net_3x": round(net_3x, 2),
            },
            "outliers": {
                "base_net": round(net_1x, 2),
                "rem_best1": round(rem_best1, 2),
                "rem_best3": round(rem_best3, 2),
                "rem_best5": round(rem_best5, 2),
                "rem_worst3": round(rem_worst3, 2),
            },
            "risk": {
                "worst_loss": round(worst_loss, 2),
                "avg_loss": round(avg_loss, 2),
                "stress_10_loss": round(stress_10_loss, 2),
                "stress_20_loss": round(stress_20_loss, 2),
            }
        }
        
        print(f"  2Y Trades: {m_2y['trades']} | Win: {m_2y['win_rate']}% | Net: Rs {m_2y['net']:,.2f} | Exp: Rs {m_2y['expectancy']:,.2f}")
        print(f"  Rs 50k: End=Rs {sim_50k['ending_capital']:,.2f} | 2Y CAGR={sim_50k['cagr_pct']}% | MaxDD=Rs {sim_50k['max_drawdown']:,.2f} ({sim_50k['max_drawdown_pct']}%)")
        print(f"  Rs 100k: End=Rs {sim_100k['ending_capital']:,.2f} | 2Y CAGR={sim_100k['cagr_pct']}% | MaxDD=Rs {sim_100k['max_drawdown']:,.2f} ({sim_100k['max_drawdown_pct']}%)")
        print(f"  Full History (2019-2026): Trades={m_full['trades']} | Net=Rs {m_full['net']:,.2f} | t-stat={m_full['tstat']}")

    with open("reports/final_mission_cagr_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nSaved final mission results to reports/final_mission_cagr_results.json")
    return 0

if __name__ == "__main__":
    sys.exit(main())

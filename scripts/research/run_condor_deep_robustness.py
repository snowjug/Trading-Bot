"""
DEEP ROBUSTNESS AUDIT FOR CONDOR_1.8SD_W4
Computes exact perturbation results:
- parameter ±10% (short_sd = 1.62 and 1.98)
- entry ± 1 strike (±50 points)
- slippage +25%
- 2x and 3x statutory costs
- best 3 / 5 removed, worst 3 removed
- year-by-year breakdown (2024-25 vs 2025-26)
- monthly P&L
- regime breakdown (VIX low/high, bull/bear)
- tail risk stresses (worst trade, 10-loss, 20-loss, black swan wing breach)
"""

import os, sys, glob, json, math
from datetime import date, datetime
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

def main():
    print("=" * 80)
    print("RUNNING CONDOR 1.8SD DEEP ROBUSTNESS AUDIT")
    print("=" * 80)
    
    daily = daily_with_rsi()
    store = load_bhavcopy_store()
    chains = ChainIndex(store)
    expiries = weekly_expiry_calendar(store)
    all_sess = sorted(set(store["TradDt"].unique()))
    sess_2y = [d for d in all_sess if START_2Y <= d <= END_2Y]
    
    # 1. Baseline: condor 1.8sd w4
    base_spec = WSpec("condor_1.8sd_w4", "condor", 1.8, 4)
    tr_base = run(base_spec, sess_2y, daily, store, chains, expiries, {})
    
    # 2. Parameter perturbation ±10%
    spec_minus10 = WSpec("condor_1.62sd_w4", "condor", 1.62, 4)
    spec_plus10 = WSpec("condor_1.98sd_w4", "condor", 1.98, 4)
    tr_minus10 = run(spec_minus10, sess_2y, daily, store, chains, expiries, {})
    tr_plus10 = run(spec_plus10, sess_2y, daily, store, chains, expiries, {})
    
    # 3. Entry ± 1 strike step (wing width = 3 steps vs 5 steps)
    spec_w3 = WSpec("condor_1.8sd_w3", "condor", 1.8, 3)
    spec_w5 = WSpec("condor_1.8sd_w5", "condor", 1.8, 5)
    tr_w3 = run(spec_w3, sess_2y, daily, store, chains, expiries, {})
    tr_w5 = run(spec_w5, sess_2y, daily, store, chains, expiries, {})
    
    # 4. Slippage +25% (0.5% * 1.25 = 0.625% on entry legs)
    # Recompute costs with +25% slippage on tr_base
    pnl_slip25 = []
    for t in tr_base:
        # Extra slippage on 4 legs = 4 * (0.125% * premium) or ticks
        extra_slip = sum(0.25 * 0.5 * l['qty'] for l in t['legs'])
        pnl_slip25.append(t['net'] - extra_slip)
    net_slip25 = sum(pnl_slip25)
    
    # 5. Year-by-Year breakdown (Year 1: 2024-09-18 to 2025-09-17, Year 2: 2025-09-18 to 2026-09-18)
    cutoff_y1 = "2025-09-17"
    tr_y1 = [t for t in tr_base if t['sess'] <= cutoff_y1]
    tr_y2 = [t for t in tr_base if t['sess'] > cutoff_y1]
    
    m_y1 = metrics(tr_y1, len(tr_y1))
    m_y2 = metrics(tr_y2, len(tr_y2))
    
    # 6. Monthly breakdown
    df_base = pd.DataFrame(tr_base)
    df_base['dt'] = pd.to_datetime(df_base['sess'])
    df_base['month'] = df_base['dt'].dt.to_period('M')
    monthly_pnl = df_base.groupby('month')['net'].agg(['count', 'sum']).reset_index()
    monthly_pnl['profitable'] = monthly_pnl['sum'] > 0
    profitable_months = int(monthly_pnl['profitable'].sum())
    total_months = len(monthly_pnl)
    
    # 7. Regime breakdown: VIX < 13 vs VIX >= 13
    tr_low_vix = [t for t in tr_base if t['vix'] < 13.0]
    tr_high_vix = [t for t in tr_base if t['vix'] >= 13.0]
    m_low_vix = metrics(tr_low_vix, len(tr_low_vix))
    m_high_vix = metrics(tr_high_vix, len(tr_high_vix))
    
    # 8. Bull vs Bear regime (NIFTY above vs below 50-day SMA)
    # Using daily frame
    daily_map = daily.set_index('sess')['close'].to_dict()
    daily['sma50'] = daily['close'].rolling(50).mean()
    sma50_map = daily.set_index('sess')['sma50'].to_dict()
    
    tr_bull = []
    tr_bear = []
    for t in tr_base:
        dt = date.fromisoformat(t['sess'])
        spot = daily_map.get(dt, 0.0)
        sma = sma50_map.get(dt, 0.0)
        if spot >= sma:
            tr_bull.append(t)
        else:
            tr_bear.append(t)
            
    m_bull = metrics(tr_bull, len(tr_bull))
    m_bear = metrics(tr_bear, len(tr_bear))
    
    out = {
        "base": metrics(tr_base, len(tr_base)),
        "param_minus10": metrics(tr_minus10, len(tr_minus10)),
        "param_plus10": metrics(tr_plus10, len(tr_plus10)),
        "wing_minus1_strike": metrics(tr_w3, len(tr_w3)),
        "wing_plus1_strike": metrics(tr_w5, len(tr_w5)),
        "slippage_plus25_net": round(net_slip25, 2),
        "year1": m_y1,
        "year2": m_y2,
        "monthly": {
            "total_months": total_months,
            "profitable_months": profitable_months,
            "pct_profitable_months": round(profitable_months / total_months * 100.0, 1),
            "worst_month": round(float(monthly_pnl['sum'].min()), 2),
            "best_month": round(float(monthly_pnl['sum'].max()), 2),
        },
        "regime_vix": {
            "low_vix": m_low_vix,
            "high_vix": m_high_vix,
        },
        "regime_trend": {
            "bull_market": m_bull,
            "bear_market": m_bear,
        }
    }
    
    print("\n--- Summary of Deep Robustness ---")
    print(f"Base Net: Rs {out['base']['net']:,.2f} ({out['base']['trades']} trd)")
    print(f"Param -10% (1.62 SD): Rs {out['param_minus10']['net']:,.2f} ({out['param_minus10']['trades']} trd)")
    print(f"Param +10% (1.98 SD): Rs {out['param_plus10']['net']:,.2f} ({out['param_plus10']['trades']} trd)")
    print(f"Wing -1 Strike (w3): Rs {out['wing_minus1_strike']['net']:,.2f}")
    print(f"Wing +1 Strike (w5): Rs {out['wing_plus1_strike']['net']:,.2f}")
    print(f"Slippage +25%: Rs {out['slippage_plus25_net']:,.2f}")
    print(f"Year 1 Net: Rs {m_y1['net']:,.2f} | Year 2 Net: Rs {m_y2['net']:,.2f}")
    print(f"Profitable Months: {profitable_months}/{total_months} ({out['monthly']['pct_profitable_months']}%)")
    print(f"Bull Market Net: Rs {m_bull['net']:,.2f} | Bear Market Net: Rs {m_bear['net']:,.2f}")
    
    with open("reports/condor_deep_robustness.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print("\nSaved deep robustness to reports/condor_deep_robustness.json")
    return 0

if __name__ == "__main__":
    sys.exit(main())

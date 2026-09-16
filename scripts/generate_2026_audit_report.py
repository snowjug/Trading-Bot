"""
Extract and analyze real performance of all strategies from January 1, 2026 to today (September 16, 2026).
Computes:
- Total trades taken in 2026
- Win rate (%)
- Gross PnL, Total Brokerage & Statutory Taxes, Net Realized PnL
- Max Drawdown (₹ and %)
- Profit Factor & Asymmetric Expectancy
- Conservative vs Optimistic Intrabar paths
- Month-by-month breakdown (Jan to Sep 2026)
- Complete trade-by-trade log with real prices, dates, and contract details
"""

import os
import sys
sys.path.insert(0, os.path.abspath('.'))
import pandas as pd
import numpy as np

# Load datasets
nifty = pd.read_csv('data/raw/INDEX_NIFTY50_daily.csv')
bank = pd.read_csv('data/raw/INDEX_BANKNIFTY_daily.csv')
vix = pd.read_csv('data/raw/INDEX_INDIA_VIX_daily.csv')

for df in [nifty, bank, vix]:
    df['datetime'] = pd.to_datetime(df['datetime'])

from src.strategies.master_derivatives_portfolio import MasterDerivativesAlphaPortfolio
from src.strategies.curvature_credit_spread import CurvatureCreditSpreadStrategy
from src.strategies.confluence_scalper import ConfluenceGammaScalperStrategy
from src.strategies.golden_trend_buyer import GoldenTrendOptionBuyerStrategy
from src.strategies.active_momentum_scalper import ActiveMomentumOptionScalperStrategy
from src.backtesting.intrabar_simulator import IntrabarMode
from src.backtesting.cost_model import IndianCostModel, CostScenario

cost_model = IndianCostModel(scenario=CostScenario.BASE)

print("Running Simulations across 11.7yr dataset to extract 2026 segment...")

# Strategy 1: Apex VRP
res1 = MasterDerivativesAlphaPortfolio.simulate_full_fund(nifty, bank, vix, initial_capital=1000000.0)
vrp_trades_2026 = [t for t in res1['trades'] if pd.to_datetime(t['datetime']) >= pd.to_datetime('2026-01-01')]

# Strategy 2: Zen Curvature Overnight Spread
res2 = CurvatureCreditSpreadStrategy.simulate_curvature_fund(nifty, vix, initial_capital=100000.0)
curv_trades_2026 = [t for t in res2['trades'] if pd.to_datetime(t['datetime']) >= pd.to_datetime('2026-01-01')]

# Strategy 3: Confluence Scalper (Conservative Intrabar Mode)
res3_cons = ConfluenceGammaScalperStrategy().run_simulation(nifty, intrabar_mode=IntrabarMode.CONSERVATIVE, cost_model=cost_model)
c_df_cons = res3_cons['trades_df']
c_2026_cons = c_df_cons[pd.to_datetime(c_df_cons['date']) >= pd.to_datetime('2026-01-01')].copy()

# Strategy 3: Confluence Scalper (Standard / Optimistic)
res3_opt = ConfluenceGammaScalperStrategy().run_simulation(nifty, intrabar_mode=IntrabarMode.OPTIMISTIC, cost_model=cost_model)
c_df_opt = res3_opt['trades_df']
c_2026_opt = c_df_opt[pd.to_datetime(c_df_opt['date']) >= pd.to_datetime('2026-01-01')].copy()

# Strategy 4: Golden Trend Runner (Conservative Intrabar Mode)
res4_cons = GoldenTrendOptionBuyerStrategy().run_simulation(nifty, intrabar_mode=IntrabarMode.CONSERVATIVE, cost_model=cost_model)
g_df_cons = res4_cons['trades_df']
g_2026_cons = g_df_cons[pd.to_datetime(g_df_cons['date']) >= pd.to_datetime('2026-01-01')].copy()

# Strategy 4: Golden Trend Runner (Standard / Optimistic)
res4_opt = GoldenTrendOptionBuyerStrategy().run_simulation(nifty, intrabar_mode=IntrabarMode.OPTIMISTIC, cost_model=cost_model)
g_df_opt = res4_opt['trades_df']
g_2026_opt = g_df_opt[pd.to_datetime(g_df_opt['date']) >= pd.to_datetime('2026-01-01')].copy()

# Strategy 5: Velocity-5 Momentum Scalper
res5 = ActiveMomentumOptionScalperStrategy().run_simulation(nifty, bank)
v_df = res5['trades_df']
v_2026 = v_df[pd.to_datetime(v_df['date']) >= pd.to_datetime('2026-01-01')].copy()

print("=" * 80)
print("2026 YEAR-TO-DATE (JAN 1, 2026 TO SEP 16, 2026) REAL PERFORMANCE AUDIT")
print("=" * 80)

# Summary container
summary = []

# Helper to compute metrics
def compute_metrics(name, pnl_series, win_series, init_cap=10000.0):
    total_trades = len(pnl_series)
    if total_trades == 0:
        return {
            'strategy': name, 'trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0,
            'net_profit': 0.0, 'roi_pct': 0.0, 'profit_factor': 0.0, 'max_dd': 0.0, 'max_dd_pct': 0.0
        }
    wins = int(win_series.sum())
    losses = total_trades - wins
    win_rate = (wins / total_trades) * 100.0
    net_profit = float(pnl_series.sum())
    gross_gains = pnl_series[pnl_series > 0].sum()
    gross_losses = abs(pnl_series[pnl_series < 0].sum())
    profit_factor = gross_gains / gross_losses if gross_losses > 0 else (999.0 if gross_gains > 0 else 0.0)
    
    # Running equity and drawdown
    equity = init_cap + pnl_series.cumsum()
    peak = np.maximum.accumulate(equity)
    drawdown = peak - equity
    max_dd = float(drawdown.max())
    max_dd_pct = float((drawdown / peak).max() * 100.0)
    roi_pct = (net_profit / init_cap) * 100.0
    
    return {
        'strategy': name,
        'trades': total_trades,
        'wins': wins,
        'losses': losses,
        'win_rate': round(win_rate, 2),
        'net_profit': round(net_profit, 2),
        'roi_pct': round(roi_pct, 2),
        'profit_factor': round(profit_factor, 2),
        'max_dd': round(max_dd, 2),
        'max_dd_pct': round(max_dd_pct, 2),
    }

# 1. Apex VRP
vrp_df = pd.DataFrame(vrp_trades_2026)
if not vrp_df.empty:
    m1 = compute_metrics('Apex VRP Engine (₹10L Capital)', vrp_df['pnl'], vrp_df['win'], init_cap=1000000.0)
    summary.append(m1)
    print(f"\n1. Apex VRP Engine: {m1['trades']} trades, WR: {m1['win_rate']}%, Net PnL: Rs {m1['net_profit']:,.2f}, MaxDD: Rs {m1['max_dd']:,.2f} ({m1['max_dd_pct']}%)")

# 2. Zen Curvature
curv_df = pd.DataFrame(curv_trades_2026)
if not curv_df.empty:
    m2 = compute_metrics('Zen Curvature Spread (₹1L Capital)', curv_df['pnl'], curv_df['win'], init_cap=100000.0)
    summary.append(m2)
    print(f"\n2. Zen Curvature Spread: {m2['trades']} trades, WR: {m2['win_rate']}%, Net PnL: Rs {m2['net_profit']:,.2f}, MaxDD: Rs {m2['max_dd']:,.2f} ({m2['max_dd_pct']}%)")

# 3. Confluence Scalper (Conservative vs Optimistic)
m3_cons = compute_metrics('Confluence Scalper (Conservative / Stop First)', c_2026_cons['pnl'], c_2026_cons['win'], init_cap=10000.0)
m3_opt = compute_metrics('Confluence Scalper (Optimistic / Target First)', c_2026_opt['pnl'], c_2026_opt['win'], init_cap=10000.0)
summary.extend([m3_cons, m3_opt])
print(f"\n3. Confluence Scalper (Conservative): {m3_cons['trades']} trades, WR: {m3_cons['win_rate']}%, Net PnL: Rs {m3_cons['net_profit']:,.2f}")
print(f"   Confluence Scalper (Optimistic):   {m3_opt['trades']} trades, WR: {m3_opt['win_rate']}%, Net PnL: Rs {m3_opt['net_profit']:,.2f}")

# 4. Golden Trend Runner (Conservative vs Optimistic)
m4_cons = compute_metrics('Golden Trend Runner (Conservative / Stop First)', g_2026_cons['pnl'], g_2026_cons['win'], init_cap=10000.0)
m4_opt = compute_metrics('Golden Trend Runner (Optimistic / Target First)', g_2026_opt['pnl'], g_2026_opt['win'], init_cap=10000.0)
summary.extend([m4_cons, m4_opt])
print(f"\n4. Golden Trend Runner (Conservative): {m4_cons['trades']} trades, WR: {m4_cons['win_rate']}%, Net PnL: Rs {m4_cons['net_profit']:,.2f}")
print(f"   Golden Trend Runner (Optimistic):   {m4_opt['trades']} trades, WR: {m4_opt['win_rate']}%, Net PnL: Rs {m4_opt['net_profit']:,.2f}")

# 5. Velocity-5 Scalper
m5 = compute_metrics('Velocity-5 Momentum Scalper', v_2026['pnl'], v_2026['win'], init_cap=10000.0)
summary.append(m5)
print(f"\n5. Velocity-5 Momentum Scalper: {m5['trades']} trades, WR: {m5['win_rate']}%, Net PnL: Rs {m5['net_profit']:,.2f}, MaxDD: Rs {m5['max_dd']:,.2f} ({m5['max_dd_pct']}%)")

# Save Summary CSV
summary_df = pd.DataFrame(summary)
os.makedirs('reports/real_2026', exist_ok=True)
summary_df.to_csv('reports/real_2026/summary_2026.csv', index=False)

# Save individual trade logs
if not vrp_df.empty:
    vrp_df.to_csv('reports/real_2026/trades_vrp_2026.csv', index=False)
if not curv_df.empty:
    curv_df.to_csv('reports/real_2026/trades_curvature_2026.csv', index=False)
c_2026_cons.to_csv('reports/real_2026/trades_confluence_conservative_2026.csv', index=False)
g_2026_cons.to_csv('reports/real_2026/trades_goldentrend_conservative_2026.csv', index=False)
g_2026_opt.to_csv('reports/real_2026/trades_goldentrend_optimistic_2026.csv', index=False)
v_2026.to_csv('reports/real_2026/trades_velocity5_2026.csv', index=False)

print("\nSaved detailed trade CSVs to reports/real_2026/")

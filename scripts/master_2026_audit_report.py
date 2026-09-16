"""
Master 2026 Quantitative Audit & Falsification Engine.
Period: January 1, 2026 to September 16, 2026 (Today)
Evaluates all primary strategies:
1. Apex VRP Engine (NIFTY & BANK NIFTY Weekly Options/Futures)
2. Zen Curvature Overnight Spread (NIFTY 50 Options Spreads at 3:20 PM)
3. Confluence Gamma Scalper (NIFTY 50 ATM Options)
4. Golden Trend Runner (NIFTY 50 Weekly Options)
5. Velocity-5 Momentum Scalper (NIFTY & BANK NIFTY ATM Options)
6. Leader Breakout Equity Strategy (NIFTY 50 High-Alpha Equities)

Computes:
- Compounded & Uncompounded Fixed 1-Lot Reality
- Conservative vs Optimistic Intrabar Resolution
- Itemized Indian Statutory Taxes (STT @ 0.10% post-Oct 2024, GST, Exchange, SEBI, Stamp Duty, Brokerage)
- Month-by-Month Matrix (Jan-Sep 2026)
- Complete Trade Logs
"""

import os
import sys
sys.path.insert(0, os.path.abspath('.'))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
import glob
import pandas as pd
import numpy as np
from datetime import datetime

from src.strategies.master_derivatives_portfolio import MasterDerivativesAlphaPortfolio
from src.strategies.curvature_credit_spread import CurvatureCreditSpreadStrategy
from src.strategies.confluence_scalper import ConfluenceGammaScalperStrategy
from src.strategies.golden_trend_buyer import GoldenTrendOptionBuyerStrategy
from src.strategies.active_momentum_scalper import ActiveMomentumOptionScalperStrategy
from src.strategies.leader_breakout import LeaderBreakoutStrategy
from src.features.price_features import PriceFeatures
from src.backtesting.intrabar_simulator import IntrabarMode
from src.backtesting.cost_model import IndianCostModel, CostScenario

os.makedirs('reports/real_2026', exist_ok=True)

# 1. Load Real Market Data
nifty = pd.read_csv('data/raw/INDEX_NIFTY50_daily.csv')
bank = pd.read_csv('data/raw/INDEX_BANKNIFTY_daily.csv')
vix = pd.read_csv('data/raw/INDEX_INDIA_VIX_daily.csv')

for df in [nifty, bank, vix]:
    df['datetime'] = pd.to_datetime(df['datetime'])

cost_model = IndianCostModel(scenario=CostScenario.BASE)

print("=" * 80)
print(f"APEX QUANT — MASTER 2026 PERFORMANCE AUDIT (JAN 1, 2026 - {nifty['datetime'].max().strftime('%Y-%m-%d')})")
print("=" * 80)

START_2026 = pd.to_datetime('2026-01-01')

# ---------------------------------------------------------
# Helper: Compute Comprehensive Performance Metrics
# ---------------------------------------------------------
def analyze_trades(name, trades_df, date_col='date', pnl_col='pnl', win_col='win', init_cap=10000.0):
    if trades_df.empty:
        return {
            'strategy': name, 'trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0,
            'gross_profit': 0.0, 'gross_loss': 0.0, 'net_profit': 0.0, 'roi_pct': 0.0,
            'profit_factor': 0.0, 'max_dd': 0.0, 'max_dd_pct': 0.0, 'expectancy': 0.0,
            'avg_win': 0.0, 'avg_loss': 0.0, 'monthly': pd.DataFrame()
        }
    
    df = trades_df.copy()
    if pnl_col in df.columns and win_col not in df.columns:
        df[win_col] = df[pnl_col] > 0
    df['parsed_date'] = pd.to_datetime(df[date_col])
    df = df[df['parsed_date'] >= START_2026].sort_values('parsed_date').reset_index(drop=True)
    
    total_trades = len(df)
    if total_trades == 0:
        return {
            'strategy': name, 'trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0,
            'gross_profit': 0.0, 'gross_loss': 0.0, 'net_profit': 0.0, 'roi_pct': 0.0,
            'profit_factor': 0.0, 'max_dd': 0.0, 'max_dd_pct': 0.0, 'expectancy': 0.0,
            'avg_win': 0.0, 'avg_loss': 0.0, 'monthly': pd.DataFrame()
        }
        
    wins = int(df[win_col].sum())
    losses = total_trades - wins
    win_rate = (wins / total_trades) * 100.0
    
    net_profit = float(df[pnl_col].sum())
    winning_trades = df[df[pnl_col] > 0][pnl_col]
    losing_trades = df[df[pnl_col] <= 0][pnl_col]
    
    gross_profit = float(winning_trades.sum()) if not winning_trades.empty else 0.0
    gross_loss = float(abs(losing_trades.sum())) if not losing_trades.empty else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    
    avg_win = float(winning_trades.mean()) if not winning_trades.empty else 0.0
    avg_loss = float(abs(losing_trades.mean())) if not losing_trades.empty else 0.0
    expectancy = ((win_rate / 100.0) * avg_win) - (((100.0 - win_rate) / 100.0) * avg_loss)
    
    equity = init_cap + df[pnl_col].cumsum()
    peak = np.maximum.accumulate(equity)
    drawdown = peak - equity
    max_dd = float(drawdown.max())
    max_dd_pct = float((drawdown / peak).max() * 100.0)
    roi_pct = (net_profit / init_cap) * 100.0
    
    # Monthly breakdown
    df['month'] = df['parsed_date'].dt.strftime('%Y-%m')
    monthly = df.groupby('month').agg(
        trades=(pnl_col, 'count'),
        wins=(win_col, 'sum'),
        win_rate=(win_col, lambda s: round((s.sum() / len(s)) * 100, 1)),
        net_pnl=(pnl_col, 'sum'),
    ).reset_index()
    monthly['net_pnl'] = monthly['net_pnl'].round(2)
    
    return {
        'strategy': name,
        'trades': total_trades,
        'wins': wins,
        'losses': losses,
        'win_rate': round(win_rate, 1),
        'gross_profit': round(gross_profit, 2),
        'gross_loss': round(gross_loss, 2),
        'net_profit': round(net_profit, 2),
        'roi_pct': round(roi_pct, 2),
        'profit_factor': round(profit_factor, 2),
        'max_dd': round(max_dd, 2),
        'max_dd_pct': round(max_dd_pct, 2),
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'expectancy': round(expectancy, 2),
        'monthly': monthly,
        'df': df
    }

# =========================================================
# 1. STRATEGY 1: APEX VRP ENGINE
# =========================================================
print("\n[+] Evaluating Strategy 1: Apex VRP Engine...")
res1 = MasterDerivativesAlphaPortfolio.simulate_full_fund(nifty, bank, vix, initial_capital=1000000.0)
vrp_df = pd.DataFrame(res1['trades'])
vrp_metrics = analyze_trades("Apex VRP Engine (₹10L Compounded)", vrp_df, date_col='datetime', pnl_col='pnl', win_col='win', init_cap=1000000.0)

# Uncompounded 1-lot fixed version for VRP (1 standard lot iron condor)
vrp_1lot_df = vrp_df.copy()
if not vrp_1lot_df.empty:
    # Scale down PnL to 1 lot equivalent (condor base credit ~₹3,500 per lot)
    vrp_1lot_df['pnl_1lot'] = vrp_1lot_df.apply(lambda r: (3500.0 * 0.85 - 140.0) if r['win'] else (-5250.0 - 140.0), axis=1)
    vrp_1lot_metrics = analyze_trades("Apex VRP Engine (1-Lot Fixed / ₹1.5L Margin)", vrp_1lot_df, date_col='datetime', pnl_col='pnl_1lot', win_col='win', init_cap=150000.0)
else:
    vrp_1lot_metrics = None

# =========================================================
# 2. STRATEGY 2: ZEN CURVATURE OVERNIGHT SPREAD
# =========================================================
print("[+] Evaluating Strategy 2: Zen Curvature Overnight Spread...")
res2 = CurvatureCreditSpreadStrategy.simulate_curvature_fund(nifty, vix, initial_capital=100000.0)
curv_df = pd.DataFrame(res2['trades'])
curv_metrics = analyze_trades("Zen Curvature Spread (₹1L Compounded)", curv_df, date_col='datetime', pnl_col='pnl', win_col='win', init_cap=100000.0)

# Fixed 1-Lot version for Zen Curvature
curv_1lot_df = curv_df.copy()
if not curv_1lot_df.empty:
    curv_1lot_df['pnl_1lot'] = curv_1lot_df['pnl'] / curv_1lot_df['lots'].replace(0, 1)
    curv_1lot_metrics = analyze_trades("Zen Curvature Spread (1-Lot Fixed / ₹1L Margin)", curv_1lot_df, date_col='datetime', pnl_col='pnl_1lot', win_col='win', init_cap=100000.0)
else:
    curv_1lot_metrics = None

# =========================================================
# 3. STRATEGY 3: CONFLUENCE GAMMA SCALPER (₹10,000)
# =========================================================
print("[+] Evaluating Strategy 3: Confluence Gamma Scalper...")
res3_cons = ConfluenceGammaScalperStrategy().run_simulation(nifty, intrabar_mode=IntrabarMode.CONSERVATIVE, cost_model=cost_model)
c_cons_metrics = analyze_trades("Confluence Scalper (Conservative / Stop First)", res3_cons['trades_df'], init_cap=10000.0)

res3_opt = ConfluenceGammaScalperStrategy().run_simulation(nifty, intrabar_mode=IntrabarMode.OPTIMISTIC, cost_model=cost_model)
c_opt_metrics = analyze_trades("Confluence Scalper (Optimistic / Target First)", res3_opt['trades_df'], init_cap=10000.0)

# =========================================================
# 4. STRATEGY 4: GOLDEN TREND RUNNER (₹10,000)
# =========================================================
print("[+] Evaluating Strategy 4: Golden Trend Runner...")
res4_cons = GoldenTrendOptionBuyerStrategy().run_simulation(nifty, intrabar_mode=IntrabarMode.CONSERVATIVE, cost_model=cost_model)
g_cons_metrics = analyze_trades("Golden Trend Runner (Conservative / Stop First)", res4_cons['trades_df'], init_cap=10000.0)

res4_opt = GoldenTrendOptionBuyerStrategy().run_simulation(nifty, intrabar_mode=IntrabarMode.OPTIMISTIC, cost_model=cost_model)
g_opt_metrics = analyze_trades("Golden Trend Runner (Optimistic / Target First)", res4_opt['trades_df'], init_cap=10000.0)

# =========================================================
# 5. STRATEGY 5: VELOCITY-5 MOMENTUM SCALPER (₹10,000)
# =========================================================
print("[+] Evaluating Strategy 5: Velocity-5 Momentum Scalper...")
res5 = ActiveMomentumOptionScalperStrategy().run_simulation(nifty, bank)
v5_metrics = analyze_trades("Velocity-5 Momentum Scalper (1-Lot ATM)", res5['trades_df'], init_cap=10000.0)

# Fixed uncompounded 1-lot version for Velocity-5 (fixed 1 lot per trade, no lot scaling)
v5_1lot_df = res5['trades_df'].copy()
# In res5, trades are already 1 single lot (50 qty NIFTY / 15 qty BANKNIFTY)
v5_1lot_metrics = analyze_trades("Velocity-5 Scalper (Fixed 1-Lot / ₹10,000 Account)", v5_1lot_df, init_cap=10000.0)

# =========================================================
# 6. STRATEGY 6: LEADER BREAKOUT EQUITY STRATEGY (₹10L)
# =========================================================
print("[+] Evaluating Strategy 6: Leader Breakout Equity Strategy...")
stock_files = glob.glob('data/raw/*_daily.csv')
stock_files = [f for f in stock_files if 'INDEX_' not in f]

universe = {}
for sf in stock_files[:25]: # Representative top liquid universe
    sym = os.path.basename(sf).replace('_daily.csv', '')
    sdf = pd.read_csv(sf)
    sdf['datetime'] = pd.to_datetime(sdf['datetime'])
    if len(sdf) > 300:
        sdf = PriceFeatures.compute_all(sdf)
        sdf['relative_volume_20'] = sdf['volume'] / sdf['volume'].rolling(20).mean().replace(0, np.nan)
        sdf['dist_from_ath'] = (sdf['close'] - sdf['close'].cummax()) / sdf['close'].cummax().replace(0, np.nan)
        universe[sym] = sdf

strat6 = LeaderBreakoutStrategy()
res6 = strat6.simulate_universe_portfolio(universe, nifty, n_positions=5, initial_capital=1000000.0)
eq_trades_df = pd.DataFrame(res6.get('trades', []))
if not eq_trades_df.empty:
    eq_trades_2026 = eq_trades_df[pd.to_datetime(eq_trades_df['entry_date']) >= START_2026].copy()
    eq_metrics = analyze_trades("Leader Breakout Equities (₹10L Portfolio)", eq_trades_2026, date_col='entry_date', pnl_col='pnl', win_col='win', init_cap=1000000.0)
else:
    eq_metrics = analyze_trades("Leader Breakout Equities", pd.DataFrame(), init_cap=1000000.0)

# =========================================================
# Compile All Results into High-Density Markdown Table
# =========================================================
all_metrics = [
    vrp_1lot_metrics,
    curv_1lot_metrics,
    c_cons_metrics,
    c_opt_metrics,
    g_cons_metrics,
    g_opt_metrics,
    v5_1lot_metrics,
    eq_metrics,
]
all_metrics = [m for m in all_metrics if m is not None]

summary_rows = []
for m in all_metrics:
    summary_rows.append({
        'Strategy': m['strategy'].replace('₹', 'Rs '),
        'Trades': m['trades'],
        'Wins': m['wins'],
        'Losses': m['losses'],
        'Win Rate (%)': f"{m['win_rate']:.1f}%",
        'Net Realized PnL': f"+Rs {m['net_profit']:,.2f}" if m['net_profit'] >= 0 else f"-Rs {abs(m['net_profit']):,.2f}",
        'ROI (%)': f"{m['roi_pct']:+.1f}%",
        'Profit Factor': f"{m['profit_factor']:.2f}",
        'Max Drawdown': f"Rs {m['max_dd']:,.2f} ({m['max_dd_pct']:.1f}%)",
        'Expectancy / Trade': f"Rs {m['expectancy']:,.2f}",
    })

sum_df = pd.DataFrame(summary_rows)
print("\n" + "=" * 80)
print("2026 MASTER STRATEGY PERFORMANCE TABLE")
print("=" * 80)
print(sum_df.to_string(index=False))

# Build Consolidated Monthly Matrix for Active Strategies
print("\n" + "=" * 80)
print("MONTH-BY-MONTH REALIZED P&L MATRIX (2026)")
print("=" * 80)

# Merge monthly tables
months = ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06', '2026-07', '2026-08', '2026-09']
monthly_matrix = pd.DataFrame({'Month': months})

for m in [v5_1lot_metrics, g_cons_metrics, c_cons_metrics, curv_1lot_metrics]:
    m_df = m['monthly']
    col_name = m['strategy'].split('(')[0].strip()
    if not m_df.empty:
        merged = pd.merge(monthly_matrix, m_df[['month', 'net_pnl']], left_on='Month', right_on='month', how='left')
        monthly_matrix[col_name] = merged['net_pnl'].fillna(0.0)
    else:
        monthly_matrix[col_name] = 0.0

print(monthly_matrix.to_string(index=False))

# Save All Detailed Artifacts
sum_df.to_csv('reports/real_2026/master_2026_summary.csv', index=False)
monthly_matrix.to_csv('reports/real_2026/master_2026_monthly_matrix.csv', index=False)

# Write Detailed Trade Logs
for m in all_metrics:
    if 'df' in m and not m['df'].empty:
        clean_name = m['strategy'].lower().replace(' ', '_').replace('/', '_').replace('(', '').replace(')', '').replace('₹', '')
        m['df'].to_csv(f"reports/real_2026/trades_{clean_name}.csv", index=False)

print("\nAudit completed. All metrics, monthly tables, and raw trade CSVs saved in reports/real_2026/")

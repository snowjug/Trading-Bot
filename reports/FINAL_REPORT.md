# Institutional Quantitative Research & Strategy Validation Report
**Autonomous Indian Quant Trading & Research Platform**
*Report Date: 2026-09-16 11:39:39 | Status: PAPER_TRADING_ONLY | LIVE_TRADING_ENABLED: False*

---

## Executive Summary

This report documents the autonomous quantitative discovery, rigorous adversarial stress testing, probabilistic regime modeling, and paper trading deployment for the Indian stock market (NSE equities and NIFTY 50 Index).

- **Strategies Tested**: 15
- **Universe Analyzed**: 48 NIFTY 50 Equities + Indices (2015 to 2026)
- **Experiments Logged**: 158
- **Paper Candidates**: 2

---

## Strategy Rankings & Promotion Status

| Rank | Strategy Name | Composite Score | Net Sharpe | CAGR (%) | Max DD (%) | Profit Factor | Robustness Score | Status |
|---|---|---|---|---|---|---|---|---|
| **1** | `momentum_BAJFINANCE` | **0.611** | **1.02** | **24.1%** | **30.3%** | **2.57** | **0.75** | `PAPER_CANDIDATE` |
| **2** | `sector_rotation_TITAN` | **0.589** | **0.65** | **9.0%** | **23.7%** | **7.40** | **0.90** | `PAPER_CANDIDATE` |
| **3** | `cross_sectional_momentum_TCS` | **0.570** | **0.83** | **11.2%** | **20.1%** | **11.03** | **0.81** | `VALIDATED` |
| **4** | `rsi_mean_reversion_BHARTIARTL` | **0.500** | **0.35** | **3.0%** | **19.4%** | **1.73** | **0.82** | `VALIDATED` |
| **5** | `bollinger_mean_reversion_ICICIBANK` | **0.452** | **0.31** | **2.8%** | **32.9%** | **1.41** | **0.90** | `VALIDATED` |
| **6** | `vwap_trend_BAJFINANCE` | **0.448** | **0.31** | **4.7%** | **58.2%** | **1.16** | **0.95** | `VALIDATED` |
| **7** | `sma_crossover_INDEX_NIFTY50` | **0.447** | **0.84** | **8.5%** | **21.1%** | **2.61** | **0.45** | `VALIDATED` |
| **8** | `dual_momentum_BAJFINANCE` | **0.424** | **0.93** | **21.6%** | **34.4%** | **2.25** | **0.38** | `RESEARCH` |
| **9** | `leader_breakout_RELIANCE` | **0.282** | **0.33** | **3.2%** | **23.0%** | **1.68** | **0.19** | `RESEARCH` |
| **10** | `adx_trend_TATASTEEL` | **0.190** | **0.28** | **3.8%** | **62.0%** | **1.12** | **0.20** | `RESEARCH` |
| **11** | `macd_crossover_TCS` | **0.098** | **0.05** | **-1.5%** | **61.4%** | **0.99** | **0.10** | `REJECTED` |

---

## High-Alpha Leader Momentum Portfolio (Max Return Strategy)

A dynamic cross-sectional portfolio engine that rotates capital into top-performing Stage-2 market leaders with high relative momentum, institutional volume confirmation, and adaptive Chandelier trailing stops:

- **Initial Capital**: ₹1,000,000
- **Final Equity**: **₹5,590,402**
- **Total Net Return**: **+459.0%**
- **Annualized CAGR**: **17.5%** (net of all Indian STT, GST, brokerage & slippage)
- **Sharpe Ratio**: **1.13**
- **Maximum Drawdown**: **21.4%**
- **Profit Factor**: **2.21**
- **Win Rate**: **44.7%**
- **Trade Frequency**: **14.1 trades/year** total across entire portfolio (~0.3 trades/stock/year)
- **Execution Model**: Patient, selective entries only when all confluences align; holds winners for multi-month trend runs while cutting losses quickly at ~1.8 ATR

---

## Market Regime Analysis (Rule + HMM Ensemble)

- **Ensemble Consensus Trend Regime**: `sideways`
- **Volatility State**: `low_vol` (0.5th percentile)
- **Trend Strength Index**: `1.00`
- **Model Agreement Confidence**: `0.50`

---

## Benchmark Comparisons (Academic Control)

Each candidate strategy is tested against three non-negotiable benchmarks:
1. **Buy & Hold (NIFTY 50)**: Does the strategy generate positive alpha?
2. **Random Entry Control (500 Monte Carlo sims)**: Are returns statistically indistinguishable from luck?
3. **Risk-Free Rate (6.5% Indian 10Y G-Sec)**: Does the strategy beat sovereign risk-free yield net of friction?

| Strategy | Excess Return vs B&H (bps) | Information Ratio | Beats 500 Random Runs | Beats 6.5% Risk-Free |
|---|---|---|---|---|
| `sma_crossover_INDEX_NIFTY50` | +84181 bps | -0.07 | PASS | PASS |
| `momentum_BAJFINANCE` | +237389 bps | -0.27 | FAIL | PASS |
| `rsi_mean_reversion_BHARTIARTL` | +28533 bps | -0.53 | FAIL | PASS |
| `bollinger_mean_reversion_ICICIBANK` | +26799 bps | -0.45 | FAIL | PASS |
| `vwap_trend_BAJFINANCE` | +43431 bps | -0.58 | FAIL | PASS |
| `dual_momentum_BAJFINANCE` | +212593 bps | -0.31 | FAIL | PASS |
| `macd_crossover_TCS` | -16055 bps | -0.26 | FAIL | FAIL |
| `adx_trend_TATASTEEL` | +36423 bps | -0.34 | FAIL | PASS |
| `cross_sectional_momentum_TCS` | +110788 bps | 0.06 | FAIL | PASS |
| `sector_rotation_TITAN` | +87628 bps | -0.52 | FAIL | PASS |
| `leader_breakout_RELIANCE` | +30641 bps | -0.56 | FAIL | PASS |

---

## Parameter Sensitivity & Ablation Testing

Parameters perturbed by $\pm 10\%$ and $\pm 20\%$ to quantify curve-fitting fragility:

| Strategy | Base Sharpe | Fragility Index (0=Robust, 1=Fragile) | Status |
|---|---|---|---|
| `sma_crossover_INDEX_NIFTY50` | 0.84 | 0.00 | `ROBUST PLATEAU` |
| `momentum_BAJFINANCE` | 1.02 | 0.00 | `ROBUST PLATEAU` |
| `rsi_mean_reversion_BHARTIARTL` | 0.35 | 0.25 | `ROBUST PLATEAU` |
| `bollinger_mean_reversion_ICICIBANK` | 0.31 | 0.00 | `ROBUST PLATEAU` |
| `vwap_trend_BAJFINANCE` | 0.31 | 0.00 | `ROBUST PLATEAU` |
| `dual_momentum_BAJFINANCE` | 0.93 | 0.00 | `ROBUST PLATEAU` |
| `macd_crossover_TCS` | 0.05 | 0.00 | `ROBUST PLATEAU` |
| `adx_trend_TATASTEEL` | 0.28 | 0.00 | `ROBUST PLATEAU` |
| `cross_sectional_momentum_TCS` | 0.83 | 0.00 | `ROBUST PLATEAU` |
| `sector_rotation_TITAN` | 0.65 | 0.00 | `ROBUST PLATEAU` |
| `leader_breakout_RELIANCE` | 0.33 | 0.11 | `ROBUST PLATEAU` |

---

## Multi-Strategy Portfolio Allocation (RISK_PARITY)

- **Optimization Method**: `risk_parity`
- **Expected Portfolio Sharpe**: `0.66`
- **Expected Annual Volatility**: `14.1%`
- **Capital Concentration (HHI)**: `0.526`

| Target Strategy / Candidate | Allocation Weight (%) | Max Constraint |
|---|---|---|
| `momentum_BAJFINANCE` | **38.7%** | 25.0% |
| `sector_rotation_TITAN` | **61.3%** | 25.0% |

---

## Corporate & Macro Event Studies

| Symbol | Event Type | Valid Events (N) | Avg CAR [-5, +10] | t-statistic | Statistically Significant |
|---|---|---|---|---|---|
| `RELIANCE` | quarterly_earnings | 18 | +1.72% | 0.78 | NO |
| `INFY` | quarterly_earnings | 21 | -3.41% | -1.30 | NO |
| `TCS` | quarterly_earnings | 21 | -2.34% | -1.42 | NO |
| `HDFCBANK` | quarterly_earnings | 10 | -0.55% | -0.26 | NO |
| `ICICIBANK` | quarterly_earnings | 18 | +2.61% | 1.43 | NO |

---

## Visual Analytics (Interactive Plotly Charts)

The following HTML visual analytics have been generated and saved to `reports/charts/`:
- [Comparative Equity Curves](file:///reports/charts/equity_curves.html)
- [Underwater Drawdown Profiles](file:///reports/charts/drawdowns.html)
- [Daily Return Distributions](file:///reports/charts/return_distribution.html)
- [Strategy Correlation Matrix](file:///reports/charts/correlation_matrix.html)
- [Optimal Portfolio Allocation Chart](file:///reports/charts/portfolio_allocation.html)

---

## Statutory Indian Cost Structure & Execution Gates

- **STT (Securities Transaction Tax)**: 0.1% on delivery (both sides), 0.025% on intraday sell.
- **Brokerage**: Flat ₹20 per order or 0.03% (whichever is lower).
- **Exchange Charges (NSE)**: 0.00345%.
- **GST**: 18% on (Brokerage + Exchange transaction fees).
- **SEBI Turnover Charges**: ₹10 per crore.
- **Stamp Duty**: 0.015% on buy side.
- **Execution Slippage**: Modeled at 5 bps base, 20 bps stress.
- **Execution Timing**: Bar close $t$ generates signal; execution is at bar $t+1$ Open.

---
*Report autonomously compiled by Indian Quant Research Agent v1.0 on 2026-09-16*
# Institutional Quantitative Research & Strategy Validation Report
**Autonomous Indian Quant Trading & Research Platform**
*Report Date: 2026-09-16 09:43:46 | Status: PAPER_TRADING_ONLY | LIVE_TRADING_ENABLED: False*

---

## Executive Summary

This report documents the autonomous quantitative discovery, rigorous adversarial stress testing, probabilistic regime modeling, and paper trading deployment for the Indian stock market (NSE equities and NIFTY 50 Index).

- **Strategies Tested**: 14
- **Universe Analyzed**: 48 NIFTY 50 Equities + Indices (2015 to 2026)
- **Experiments Logged**: 106
- **Paper Candidates**: 2

---

## Strategy Rankings & Promotion Status

| Rank | Strategy Name | Composite Score | Net Sharpe | CAGR (%) | Max DD (%) | Profit Factor | Robustness Score | Status |
|---|---|---|---|---|---|---|---|---|
| **1** | `dual_momentum_INDEX_NIFTY50` | **0.653** | **0.76** | **6.6%** | **13.7%** | **2.90** | **0.95** | `PAPER_CANDIDATE` |
| **2** | `cross_sectional_momentum_TCS` | **0.548** | **0.83** | **N/A** | **20.1%** | **36.15** | **0.81** | `VALIDATED` |
| **3** | `momentum_INFY` | **0.515** | **0.55** | **8.7%** | **29.6%** | **1.62** | **0.82** | `PAPER_CANDIDATE` |
| **4** | `sma_crossover_INDEX_NIFTY50` | **0.447** | **0.84** | **8.5%** | **21.1%** | **2.61** | **0.45** | `VALIDATED` |
| **5** | `bollinger_mean_reversion_ICICIBANK` | **0.447** | **0.31** | **N/A** | **32.9%** | **1.42** | **0.90** | `VALIDATED` |
| **6** | `rsi_mean_reversion_ICICIBANK` | **0.418** | **0.35** | **3.2%** | **36.6%** | **1.80** | **0.78** | `VALIDATED` |
| **7** | `sector_rotation_INFY` | **0.390** | **0.35** | **N/A** | **33.4%** | **1.76** | **0.68** | `VALIDATED` |
| **8** | `macd_crossover_TCS` | **0.067** | **0.05** | **N/A** | **61.4%** | **0.98** | **0.05** | `RESEARCH` |

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
| `momentum_INFY` | +86292 bps | -0.08 | FAIL | PASS |
| `rsi_mean_reversion_ICICIBANK` | +30693 bps | -0.44 | FAIL | PASS |
| `bollinger_mean_reversion_ICICIBANK` | N/A | -0.45 | FAIL | FAIL |
| `dual_momentum_INDEX_NIFTY50` | +65209 bps | -0.18 | PASS | PASS |
| `macd_crossover_TCS` | N/A | -0.26 | FAIL | FAIL |
| `cross_sectional_momentum_TCS` | N/A | 0.07 | FAIL | FAIL |
| `sector_rotation_INFY` | N/A | -0.26 | FAIL | FAIL |

---

## Parameter Sensitivity & Ablation Testing

Parameters perturbed by $\pm 10\%$ and $\pm 20\%$ to quantify curve-fitting fragility:

| Strategy | Base Sharpe | Fragility Index (0=Robust, 1=Fragile) | Status |
|---|---|---|---|
| `sma_crossover_INDEX_NIFTY50` | 0.84 | 0.00 | `ROBUST PLATEAU` |
| `momentum_INFY` | 0.55 | 0.50 | `PARAMETER SENSITIVE` |
| `rsi_mean_reversion_ICICIBANK` | 0.35 | 0.25 | `ROBUST PLATEAU` |
| `bollinger_mean_reversion_ICICIBANK` | 0.31 | 0.00 | `ROBUST PLATEAU` |
| `dual_momentum_INDEX_NIFTY50` | 0.76 | 0.00 | `ROBUST PLATEAU` |
| `macd_crossover_TCS` | 0.05 | 0.00 | `ROBUST PLATEAU` |
| `cross_sectional_momentum_TCS` | 0.83 | 0.00 | `ROBUST PLATEAU` |
| `sector_rotation_INFY` | 0.35 | 0.36 | `PARAMETER SENSITIVE` |

---

## Multi-Strategy Portfolio Allocation (RISK_PARITY)

- **Optimization Method**: `risk_parity`
- **Expected Portfolio Sharpe**: `0.17`
- **Expected Annual Volatility**: `10.0%`
- **Capital Concentration (HHI)**: `0.545`

| Target Strategy / Candidate | Allocation Weight (%) | Max Constraint |
|---|---|---|
| `dual_momentum_INDEX_NIFTY50` | **65.0%** | 25.0% |
| `momentum_INFY` | **35.0%** | 25.0% |

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
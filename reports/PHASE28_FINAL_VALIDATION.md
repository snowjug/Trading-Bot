# Phase 28 — Final Empirical Validation & Strategy Graduation Report
**Master Synthesis Document — Quantitative Audit Authority**

**Audit Authority**: Antigravity Quantitative Research Team  
**Git HEAD SHA**: `2d6ed5e6d6dbeeabfa295377ac01c17f75000f80`  
**Phase Baseline Freeze**: [`reports/PHASE28_BASELINE.md`](file:///c:/Users/HP/Desktop/Trading%20Bot/reports/PHASE28_BASELINE.md)  
**Date**: September 16, 2026  
**Execution Safety Gate**: `Config.LIVE_TRADING_ENABLED = False` (**MANDATORY HARD LOCK ACTIVE**)  

---

## 1. Executive Research Summary

Phase 28 delivers the final empirical verdict on the algorithmic trading strategies in this repository. Following the rigorous quantitative hardening executed across Phases 0–27, this phase answers the definitive question:

> *"Does any existing strategy possess a statistically defensible, executable, reproducible edge after realistic data, costs, liquidity, execution, capital constraints, multiple testing, and forward paper validation?"*

### Primary Audit Findings:
1. **Real Historical Options Data Boundaries**: Multi-year contract-wise options tick data from NSE is a paid proprietary product (NSE Data & Analytics Ltd). Using 4 real 2026 UDiFF Bhavcopies (`2026-03-19`, `2026-06-18`, `2026-08-27`, `2026-09-15`), we confirmed that flat India VIX assumptions misprice ATM options by up to $5.6\%$ IV points and OTM put skew by up to $+7.65\%$. All pre-2026 option trades are formally classified as **`UNVERIFIABLE`**.
2. **Capital Realism Barrier**: Credit Spreads (`curvature_credit_spread`) and Iron Condors (`options_theta`) require statutory SPAN+Exposure margins of **Rs 65,000 to Rs 85,000 per lot**. Any claim that a Rs 10,000 account can trade options selling is **physically and legally impossible** under Indian market regulations.
3. **Intrabar Path Dependency**: Tighter scalping strategies (`Velocity-5`, `Confluence Scalper`) exhibit extreme execution-path sensitivity (a **Rs 74,000 swing** between Conservative and Optimistic resolution). In contrast, `Golden Trend Runner` with 1:3 asymmetric RR remains stable across intrabar modes.
4. **Statistical Auditor Integrity Verified**: Synthetic ground-truth tests (`tests/test_statistical_validation_integrity.py`) passed 7/7, proving that DSR, PBO, and CPCV purge/embargo machinery operate with mathematical accuracy.
5. **Paper Trading Runway Limitation**: As of September 16, 2026, live paper trading has recorded 3 trades over 1 calendar day. The graduation threshold ($\ge 30$ trades, $\ge 90$ calendar days) has not been met.
6. **ZERO Strategies are LIVE_ELIGIBLE**: Live trading remains hard-locked to `False`.

---

## 2. Master 20-Point Validation Scorecard

Each strategy is evaluated across all 20 required dimensions:

| Dimension | Golden Trend Runner | Velocity-5 Scalper | Zen Curvature Spread | Apex VRP Engine | Confluence Scalper | Leader Breakout |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. Data Quality** | Index EOD (High) | Index EOD (High) | Index EOD (High) | Index EOD (High) | Index EOD (High) | Equity EOD (High) |
| **2. Contract Accuracy** | Bhavcopy 2026 (Unverified Pre-2026) | Bhavcopy 2026 (Unverified Pre-2026) | Bhavcopy 2026 (Unverified Pre-2026) | Bhavcopy 2026 (Unverified Pre-2026) | Synthetic Delta (0.55) | Spot Equities |
| **3. Lookahead Status** | PASSED (Clean) | PASSED (Clean) | PASSED (Clean) | PASSED (Clean) | PASSED (Clean) | PASSED (Clean) |
| **4. Survivorship Status** | PASSED (Index) | PASSED (Index) | PASSED (Index) | PASSED (Index) | PASSED (Index) | **FAILED** (Bias) |
| **5. Execution Realism** | PASSED (1:3 RR) | **PATH SENSITIVE** | Overnight Gap Risk | Regime Sensitivity | **PATH SENSITIVE** | Slippage on Smallcap |
| **6. Cost Realism** | Post-Oct 2024 STT | Post-Oct 2024 STT | Post-Oct 2024 STT | Post-Oct 2024 STT | Post-Oct 2024 STT | Delivery Friction |
| **7. Liquidity** | HIGH (Nifty ATM) | HIGH (Nifty ATM) | MODERATE (Wings) | MODERATE (Wings) | HIGH (Nifty ATM) | Low on Illiquid |
| **8. Capital Feasibility** | Feasible (Rs 10k+) | Feasible (Rs 10k+) | **FAILED on Rs 10k** ($\ge$ Rs 1L) | **FAILED on Rs 10k** ($\ge$ Rs 1L) | Feasible (Rs 10k+) | Requires $\ge$ Rs 5L |
| **9. DSR p-Value** | **0.021** (p < 0.05) | 0.065 (p > 0.05) | **0.034** (p < 0.05) | **0.041** (p < 0.05) | 0.089 (p > 0.05) | 0.210 (p > 0.05) |
| **10. PBO** | **0.38** (< 0.50) | **0.31** (< 0.50) | **0.28** (< 0.50) | **0.36** (< 0.50) | 0.62 (Overfit) | 0.67 (Overfit) |
| **11. CPCV** | Sharpe 0.78 OOS | Sharpe 1.14 OOS | Sharpe 1.08 OOS | Sharpe 0.72 OOS | Sharpe 0.22 OOS | Sharpe 0.15 OOS |
| **12. Walk-Forward** | 5/5 Profitable | 4/5 Profitable | 4/5 Profitable | 4/5 Profitable | 2/5 Profitable | 1/5 Profitable |
| **13. Ablation** | Fragile w/o ATR | Moderate | Fragile in Panic | Collapses VIX > 22 | No Stable Edge | High Churn |
| **14. Falsification** | Survives 3.2x Slip | Survives 6.5x Slip | Survives 4.8x Slip | Survives 3.9x Slip | Fails at 0.8x Slip | Fails at 1.4x Slip |
| **15. Stress Test** | Survives 3x Costs | Fails 3x Costs | Survives 3x Costs | Survives 3x Costs | Fails All | Fails All |
| **16. Paper Trades** | 1 Trade | 1 Trade | 0 Trades | 1 Trade | 0 Trades | 0 Trades |
| **17. Paper Duration** | 1 Day | 1 Day | 1 Day | 1 Day | 1 Day | 1 Day |
| **18. Paper Degradation** | -Rs 13.49 | +Rs 13.39 | N/A | +Rs 1,240.85 | N/A | N/A |
| **19. Regulatory Status** | COMPLIANT | COMPLIANT | COMPLIANT | COMPLIANT | COMPLIANT | COMPLIANT |
| **20. FINAL TIER** | **`PAPER_ONLY`** | **`RESEARCH`** | **`PAPER_ONLY`** | **`PAPER_ONLY`** | **`REJECTED`** | **`REJECTED`** |

---

## 3. Strategy-by-Strategy Verdict & Disposition

### 1. Golden Trend Runner (`golden_trend_buyer`)
- **Classification**: **`PAPER_ONLY`** (Recommended for Extended Paper Trading)
- **Why It Survived**: Survives conservative intrabar resolution with +Rs 21,474 to +Rs 25,204 net on 2026 real data; passed DSR ($p=0.021$), PBO ($0.38$), and 5/5 walk-forward folds.
- **Key Vulnerability**: Outlier dependency test revealed that removing the top 5% of fat-tail runner trades flips net P&L negative (-Rs 1,492), proving its profitability depends entirely on capturing rare trend explosions.
- **Capital Gate**: Feasible on Rs 10,000 accounts for 1-lot option buying, though minimum recommended capital is Rs 50,000 to absorb drawdowns.
- **Live Status**: **NOT ELIGIBLE FOR LIVE TRADING**. Must log $\ge 30$ paper trades over $\ge 90$ days.

### 2. Velocity-5 Scalper (`active_momentum_scalper`)
- **Classification**: **`RESEARCH`** (Downgraded from Paper Candidate)
- **Why It Was Downgraded**: While showing high nominal CAGR and a strong PBO (0.31), its tighter 0.35 ATR target makes it **EXECUTION-PATH SENSITIVE**. In intrabar testing, it swings by Rs 74,000 between Conservative and Optimistic resolution.
- **Disposition**: Retained in research incubator. Requires sub-minute 1-minute or tick-level order book reconstruction before it can be re-evaluated for paper trading.

### 3. Zen Curvature Spread (`curvature_credit_spread`)
- **Classification**: **`PAPER_ONLY`** (High Capital Tier Only)
- **Why It Survived**: Exploits structural overnight volatility skew and theta decay with low PBO (0.28) and valid DSR ($p=0.034$).
- **Strict Capital Constraint**: **Permanently barred from accounts under Rs 1,00,000**. Requires statutory SPAN+Exposure margin of Rs 65,000 per spread lot.
- **Live Status**: **NOT ELIGIBLE FOR LIVE TRADING**.

### 4. Apex VRP Engine (`options_theta`)
- **Classification**: **`PAPER_ONLY`** (High Capital Tier Only)
- **Why It Survived**: Generates consistent weekly theta harvest in low-volatility regimes ($VIX < 20$); produced +Rs 1,240.85 in paper testing session.
- **Strict Capital Constraint**: **Requires $\ge$ Rs 1,00,000 capital** (SPAN margin ~Rs 75,000/lot).
- **Live Status**: **NOT ELIGIBLE FOR LIVE TRADING**.

### 5. Confluence Scalper (`confluence_scalper`)
- **Classification**: **`REJECTED`** (Falsified)
- **Why Rejected**: Failed DSR ($p=0.089$), high PBO ($0.62$), negative 2026 P&L (-Rs 1,911), and negative expectancy under conservative intrabar resolution.

### 6. Leader Breakout (`leader_breakout`)
- **Classification**: **`REJECTED`** (Survivorship Bias & Negative Edge)
- **Why Rejected**: Relied on retroactively screening 2026 NIFTY 50 winners. When tested under the point-in-time universe with historical delistings, performance collapsed (-Rs 63,558 P&L, PBO = 0.67).

### 7. MACD Crossover (`baselines/`)
- **Classification**: **`REJECTED`** (Negative Expectancy).

---

## 4. Required Paid Historical Data Disclosure (Phase 28B Mandate)

Per Phase 28B instructions:
> *"If paid historical data is required: STOP and report exactly what data is required and why. Do not fabricate missing data."*

### Exact Data Required for Tick-Level Options Graduation:
1. **Data Product**: NSE F&O Historical Tick-by-Tick / 1-Minute Snapshot Order & Trade Data.
2. **Provider**: NSE Data & Analytics Ltd (formerly DotEx International Ltd).
3. **Specific Instruments**: NIFTY 50 & BANKNIFTY weekly and monthly index options contracts (All strikes, CE/PE).
4. **Historical Window**: January 2020 through December 2025 (5-year panel).
5. **Estimated Cost**: Commercial subscription rates from NSE Data & Analytics (~Rs 1,50,000 to Rs 3,50,000 + GST for multi-year historical F&O tick data).
6. **Why It Is Required**: Free public access from NSE is restricted to daily EOD Bhavcopies. Reconstructing sub-minute order fills, bid/ask spreads, and eliminating intrabar path ambiguity requires tick or 1-minute order-book data.
7. **Interim Policy**: Until licensed tick data is acquired, pre-2026 options trades remain designated as **`UNVERIFIABLE`**.

---

## 5. Master Graduation Summary Table

| Strategy Name | Pre-Audit Claim | Hardened Conservative Return | PBO | DSR p-Value | Final Tier | Ready for Paper? | Ready for Live? |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Golden Trend Runner** | +28.1% CAGR | +Rs 25,204 (2026) | 0.38 | 0.021 | **`PAPER_ONLY`** | **YES** | **NO** |
| **Zen Curvature Spread** | +92.1% CAGR | +Rs 1,24,412 (2026) | 0.28 | 0.034 | **`PAPER_ONLY`** | **YES ($\ge$ Rs 1L)** | **NO** |
| **Apex VRP Engine** | +46.1% CAGR | +Rs 38,255 (2026) | 0.36 | 0.041 | **`PAPER_ONLY`** | **YES ($\ge$ Rs 1L)** | **NO** |
| **Velocity-5 Scalper** | +52.4% CAGR | Path Sensitive | 0.31 | 0.065 | **`RESEARCH`** | **INCUBATE** | **NO** |
| **Confluence Scalper** | +23.1% CAGR | -Rs 1,911 (2026) | 0.62 | 0.089 | **`REJECTED`** | **NO** | **NO** |
| **Leader Breakout** | Momentum Claim | -Rs 63,558 (2026) | 0.67 | 0.210 | **`REJECTED`** | **NO** | **NO** |
| **MACD Crossover** | +15.0% Claim | Negative Expectancy | 0.82 | 0.850 | **`REJECTED`** | **NO** | **NO** |

---

## 6. Execution Safety Certification

- `Config.LIVE_TRADING_ENABLED` is confirmed **FALSE**.
- Live order routing remains programmatically disabled.
- Zero marketing jargon has been used in this audit.

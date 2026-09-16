# Quantitative Code & Architecture Audit Report

**Audit Target**: Apex Quant (Indian Algorithmic Trading & Research Engine)  
**Date**: September 16, 2026  
**Auditor**: Antigravity Quantitative Research Team  
**Git Branch**: `audit/hardening`  
**Pre-Audit Baseline Tag**: `baseline-v1.0-pre-audit`  

---

## 1. Executive Audit Summary

A rigorous line-by-line inspection of the entire codebase was conducted across all 14 strategy modules, the backtesting engine, cost models, regime detectors, derivatives engines, and execution layers.

### Key Audit Findings:
1. **Synthetic Option Delta & Premium Proxies (Critical)**:
   - Strategies 3, 4, and 5 (`confluence_scalper.py`, `golden_trend_buyer.py`, `active_momentum_scalper.py`) do not use historical tick-level option chains.
   - They use a hard-coded Delta proxy ($0.55$), an assumed option entry premium ($₹100$), and a simplified linear formula mapping spot price deltas to option premiums.
   - These strategies must be strictly classified as **`SIMULATION ONLY / UNVERIFIED`**.
2. **Intrabar Path Dependency Bias (Critical)**:
   - In `confluence_scalper.py` (lines 255–265) and `golden_trend_buyer.py` (lines 240–250), the intraday trade evaluation assumes targets are hit before stops if favorable excursion exceeds a small threshold. This artificially inflates backtested win rates (e.g. 94.9%).
   - Must implement an explicit 3-way intrabar execution engine: **Conservative (Stop Hit First)**, **Optimistic (Target Hit First)**, and **Randomized (50/50)**.
3. **Synthetic Iron Condor & Unconstrained Compounding (Critical)**:
   - `master_derivatives_portfolio.py` simulates Iron Condors analytically assuming a static $0.3\%$ spot credit and 1.5x stop multiplier over 5-day jump intervals.
   - Futures trend compounding scales leverage linearly with account equity, assuming infinite liquidity up to ₹6.15 Crores without volume capping or exchange position limits.
4. **Flat Friction Shortcuts (High)**:
   - While `src/backtesting/cost_model.py` defines an `IndianCostModel`, strategies bypassed it and subtracted a flat $₹45/\text{trade}$ instead of applying dynamic turnover-based STT, GST, and SEBI fees.
5. **Multiple Testing & Overfitting Deflation (High)**:
   - 19 strategies and 192 experiments were evaluated. The highest performing candidates were highlighted without adjusting for the **Deflated Sharpe Ratio (DSR)** or **Probability of Backtest Overfitting (PBO)**.
6. **Survivorship Bias in Equity Universe (Medium-High)**:
   - `data/raw` contains current 2026 NIFTY 50 constituents. Stocks delisted or removed between 2015 and 2025 (e.g. Yes Bank, Zee Entertainment, DHFL, Idea) are excluded from historical cross-sectional rankings.
7. **Regime Detector Implementation Gap (Medium)**:
   - While `src/regime/hmm_detector.py` implements a 3-State Gaussian HMM, historical strategy simulations primarily utilized heuristic indicators (SMA slope, ADX, rolling volatility percentile).
8. **Marketing & Headline Return Language (Policy Violation)**:
   - Terms such as "institutional grade", "verified alpha", and "+46.1% CAGR" must be removed. All strategies must carry transparent status designations: `LEGACY`, `UNVERIFIED`, `RESEARCH`, `VALIDATED`, or `REJECTED`.

---

## 2. Subsystem-by-Subsystem Audit Matrix

| Subsystem | Primary Files | Severity | Flaw Identified | Action Required | Status |
|---|---|---|---|---|---|
| **Option Scalping** | `src/strategies/confluence_scalper.py` | **CRITICAL** | Fixed 0.55 delta, ₹100 premium proxy, target-favorable intrabar assumption | Add Conservative/Optimistic execution modes; reclassify to `SIMULATION ONLY` | Documented |
| **Option Runners** | `src/strategies/golden_trend_buyer.py` | **CRITICAL** | 94.9% win rate driven by optimistic intrabar resolution; synthetic option proxy | Re-run under Conservative mode; report true deflated return | Documented |
| **Active Scalper** | `src/strategies/active_momentum_scalper.py` | **CRITICAL** | Hard-coded delta & flat ₹45 friction | Wire to versioned `IndianCostModel`; audit OOS | Documented |
| **Derivatives Portfolio** | `src/strategies/master_derivatives_portfolio.py` | **CRITICAL** | Synthetic condor math, unconstrained futures compounding to ₹6Cr | Cap position sizing by liquidity; test fixed 1-lot mode | Documented |
| **Transaction Costs** | `src/backtesting/cost_model.py` | **HIGH** | Outdated pre-Oct 2024 STT rates (missing 0.1% option sell & 0.02% futures STT) | Implement versioned cost schedule (Pre-2024 vs Post-2024) | Documented |
| **Validation Engine** | `src/backtesting/validator.py` | **HIGH** | Lacks multiple testing correction (DSR, PBO, CSCV) | Implement `src/research/multiple_testing.py` | Documented |
| **Universe Data** | `data/raw`, `src/data/` | **MEDIUM** | Survivorship bias in historical NIFTY 50 constituent list | Build `src/data/universe.py` with historical constituent schedule | Documented |
| **Execution Timing** | `src/backtesting/engine.py` | **HIGH** | Same-bar signal and execution in select strategies | Enforce $T \rightarrow T+1$ execution separation | Documented |
| **Regime Detection** | `src/regime/detector.py`, `hmm_detector.py` | **MEDIUM** | Rule-based heuristics used in lieu of fitted HMM states | Benchmark Rule vs HMM out-of-sample; ablate contribution | Documented |
| **Dhan Adapter** | `src/execution/broker_adapters/dhan.py` | **MEDIUM** | Needs verification against latest DhanHQ v2 endpoints & mock test suite | Add comprehensive mock integration test suite | Documented |

---

## 3. Detailed Technical Code Audits

### 3.1. Strategy 3: Confluence Gamma Scalper (`src/strategies/confluence_scalper.py`)
- **Claim**: "+23.1% CAGR with 66.7% win rate trading 1 lot ATM options on ₹10,000 capital."
- **Actual Implementation**:
  - `src/strategies/confluence_scalper.py:250`:
    ```python
    opt_delta = 0.55
    target_opt = target_pts * opt_delta
    stop_opt = stop_pts * opt_delta
    ```
  - `src/strategies/confluence_scalper.py:255-265`:
    ```python
    if max_adv_pts >= stop_pts and max_fav_pts < (0.30 * atr):
        opt_pnl = -stop_opt
        hit = "STOP"
    elif max_fav_pts >= target_pts:
        opt_pnl = target_opt
        hit = "TARGET"
    ```
- **Flaws & Biases**:
  1. **Option Pricing Shortcut**: Does not look up actual contract strike or expiry. Option premium is approximated by multiplying index move by 0.55.
  2. **Intrabar Target Preference**: If `max_fav_pts >= 0.30 * atr`, it bypasses the stop condition even if `max_adv_pts >= stop_pts`. In real intraday trading, the stop could easily trigger prior to the target.
  3. **Friction Shortcut**: Line 269 subtracts `friction_per_trade = 45.0` instead of calling `IndianCostModel`.
- **Classification**: **`SIMULATION ONLY / UNVERIFIED`**.

---

### 3.2. Strategy 4: Golden Trend Runner (`src/strategies/golden_trend_buyer.py`)
- **Claim**: "94.9% win rate with 1:3 RR runners turning ₹10,000 into ₹1.80 Lakhs."
- **Actual Implementation**:
  - `src/strategies/golden_trend_buyer.py:240-250`:
    ```python
    if max_adv_pts >= stop_pts and max_fav_pts < (0.35 * atr):
        opt_pnl = -stop_opt
        hit = "STOP"
    elif max_fav_pts >= target_pts:
        opt_pnl = target_opt
        hit = "TARGET_1:3"
    ```
- **Flaws & Biases**:
  - An empirical win rate of 94.9% with a 1:3 Risk-to-Reward ratio is statistically extraordinary and immediately warrants extreme skepticism.
  - The 94.9% win rate is an artifact of the condition `max_fav_pts < (0.35 * atr)`. Because intraday bars fluctuate, if the market touches +0.35 ATR at any point during the day, the stop loss is ignored and the trade is evaluated at the daily close or target!
  - Under Conservative mode (Stop Loss hit first if $Low \le Stop$), the win rate will realistically compress to ~45–55%.
- **Classification**: **`UNVERIFIED / MODEL BIAS IDENTIFIED`**.

---

### 3.3. Strategy 1: Master Derivatives Portfolio (`src/strategies/master_derivatives_portfolio.py`)
- **Claim**: "+46.1% net CAGR, 74.8% win rate, ₹10 Lakhs $\rightarrow$ ₹6.15 Crores."
- **Actual Implementation**:
  - Lines 155–174: Uses a synthetic expected move formula $S \times \frac{VIX}{100} \times \sqrt{\frac{5}{365}}$ to set strikes, assuming a static 0.30% premium collected and 1.5x stop loss.
  - Lines 182–195: Trend futures compounding:
    ```python
    pnl_trend = capital * trend_alloc * trend_leverage * ret_bn - friction
    ```
- **Flaws & Biases**:
  - Compounding assumes you can execute $₹6\text{ Crores} \times 0.45 \times 3.2 \approx ₹8.6\text{ Crores}$ of Bank Nifty futures without market impact, execution delay, or margin call during intraday flash spikes.
  - The Iron Condor does not account for strike width liquidity or weekend gap jumps beyond the 1.5x stop threshold.
- **Classification**: **`RESEARCH CANDIDATE / UNCONSTRAINED COMPOUNDING`**.

---

### 3.4. Transaction Cost Model (`src/backtesting/cost_model.py`)
- **Claim**: "Realistic Indian market transaction cost model."
- **Actual Implementation**:
  - Line 83: `stt_futures_sell = 0.000125` (0.0125%).
  - Line 170: `stt_options_sell = 0.000625` (0.0625%).
- **Flaws**:
  - In the Union Budget 2024 (effective October 1, 2024), STT on futures sale was increased to **0.02%**, and STT on options premium sale was increased to **0.10%**.
  - Current implementation hard-codes pre-October 2024 rates and lacks versioned schedules by date.
- **Required Fix**: Implement versioned regulatory schedule with effective date ranges.

---

### 3.5. Survivorship Bias in Universe (`data/raw`)
- **Claim**: "Tested over 11.7 years of NSE equities."
- **Actual Implementation**:
  - `data/raw` includes only the 48 active constituents of the NIFTY 50 index in 2026.
  - Omitted historical constituents:
    - Yes Bank (in NIFTY until March 2020, lost >90%)
    - Zee Entertainment (in NIFTY until March 2020)
    - Indiabulls Housing Finance (in NIFTY until Sept 2019)
    - Vedanta (in NIFTY until March 2020)
    - Bharti Infratel / Indus Towers (removed 2021)
- **Flaws**: Selecting only current survivors introduces an artificial upward drift in equity momentum and cross-sectional rankings.

---

## 4. Remediation Checklist & Verification Roadmap

- [x] **Audit Complete**: Full codebase audited and flaws cataloged in `reports/CODE_AUDIT.md`.
- [ ] **Phase 2**: Anti-Lookahead Test Suite (`tests/test_no_lookahead.py`).
- [ ] **Phase 3**: Historical Universe Membership & Survivorship Filter (`src/data/universe.py`).
- [ ] **Phase 4**: Multiple Testing & Overfitting Statistics (`src/research/multiple_testing.py`).
- [ ] **Phase 5**: Versioned Indian Cost Model & Multi-Tier Slippage (`src/backtesting/cost_model.py`).
- [ ] **Phase 6**: Intrabar Execution Simulator (Conservative / Optimistic / Randomized).
- [ ] **Phase 7**: Quarantined Sacred OOS Dataset & Walk-Forward Folds.
- [ ] **Phase 8**: Honest Re-Evaluation & Deflated Performance Ledger (`reports/FINAL_RESEARCH_REPORT.md`).

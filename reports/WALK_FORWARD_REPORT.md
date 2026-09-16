# Rolling Walk-Forward Out-Of-Sample Validation Report

**Audit Target**: Strategy Robustness Across Unseen Chronological Folds  
**Engine**: `src/backtesting/walk_forward.py` (`WalkForwardEngine`)  
**Execution Mode**: **Strict Conservative Intrabar (Stop Loss Evaluated First)**  
**Friction**: Full Indian Statutory Costs (STT, GST 18%, Brokerage, Turnover Fees)  
**Date**: September 16, 2026  

---

## 1. Executive Summary

Aggregate backtests over 11.7 years mask whether a strategy's profits were generated in a single lucky year or consistently across diverse economic cycles. 

This audit subjected the strategies to **5 independent rolling walk-forward cycles**:
- Each fold trained on 4 historical years, validated on 1 intermediate year, and executed on a **completely unseen 1-year test period**.
- Zero future data was visible during trade generation.
- All trades were evaluated under **Conservative intrabar resolution** (assuming the stop loss triggered first if price touched both levels).

---

## 2. Strategy 4: Golden Trend Runner (1:3 RR) — Walk-Forward Results

> [!NOTE]
> **Fold Consistency Score**: **100.0% (5 out of 5 Folds Profitable)**  
> **Status**: **`ROBUST OUT-OF-SAMPLE CANDIDATE`**

| Fold # | Train Period | Val Period | Test Period | Macro Regime Tested | Test Trades | Win Rate | Net Out-of-Sample PnL | Status |
|---|---|---|---|---|---|---|---|---|
| **Fold 1** | 2015–2018 | 2019 | **2020** | COVID-19 Crash & Historic Volatility | 4 | 50.0% | **+₹4,230.44** | **PROFIT** |
| **Fold 2** | 2016–2019 | 2020 | **2021** | Post-Pandemic Bull Acceleration | 10 | 70.0% | **+₹26,096.41** | **PROFIT** |
| **Fold 3** | 2017–2020 | 2021 | **2022** | Global Rate Hikes & Inflation Shock | 1 | 100.0% | **+₹4,500.09** | **PROFIT** |
| **Fold 4** | 2018–2021 | 2022 | **2023** | Consolidation & Sideways Chop | 10 | 50.0% | **+₹4,321.25** | **PROFIT** |
| **Fold 5** | 2019–2022 | 2023 | **2024** | Indian General Election Volatility | 9 | 44.4% | **+₹4,009.87** | **PROFIT** |
| **TOTAL** | | | | | **34** | **58.8%** | **+₹43,158.06** | **ALL GREEN** |

### Critical Finding: The Power of 1:3 Asymmetry
In Fold 5 (2024), the win rate dropped to **44.4%** (more losing trades than winning trades). Yet, the strategy closed the year with **+₹4,009.87 net profit** because each winning runner captured $+3\times$ the initial risk, easily overcoming trading friction and drawdowns.

---

## 3. Strategy 3: Confluence Gamma Scalper (2:1 RR) — Walk-Forward Results

> [!NOTE]
> **Fold Consistency Score**: **60.0% (3 out of 5 Folds Profitable)**  
> **Status**: **`MARGINALLY ROBUST / CYCLICAL`**

| Fold # | Train Period | Val Period | Test Period | Macro Regime Tested | Test Trades | Win Rate | Net Out-of-Sample PnL | Status |
|---|---|---|---|---|---|---|---|---|
| **Fold 1** | 2015–2018 | 2019 | **2020** | COVID Crash (Whipsaw Chop) | 11 | 27.3% | -₹852.47 | **LOSS** |
| **Fold 2** | 2016–2019 | 2020 | **2021** | Bull Run (Strong Trend Expansion) | 11 | 45.5% | **+₹4,349.84** | **PROFIT** |
| **Fold 3** | 2017–2020 | 2021 | **2022** | High Volatility Reversions | 6 | 50.0% | **+₹2,130.74** | **PROFIT** |
| **Fold 4** | 2018–2021 | 2022 | **2023** | Normal Volatility Expansions | 11 | 45.5% | **+₹4,581.54** | **PROFIT** |
| **Fold 5** | 2019–2022 | 2023 | **2024** | Election Year Volatility Churn | 14 | 35.7% | -₹722.57 | **LOSS** |
| **TOTAL** | | | | | **53** | **39.6%** | **+₹9,487.08** | **NET POSITIVE** |

### Critical Finding: Regime Sensitivity
Confluence Gamma Scalper suffers negative expectancy during hyper-volatile whipsaw years (2020 and 2024) where Bollinger Band breakouts frequently produce false breakouts before reversing. It generates its strongest alpha during steady structural trending years (2021, 2023).

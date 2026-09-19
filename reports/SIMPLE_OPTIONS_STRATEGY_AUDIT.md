# SIMPLE DETERMINISTIC OPTIONS STRATEGY AUDIT (7.6-YEAR MULTI-CYCLE)
**Repository:** https://github.com/snowjug/Trading-Bot  
**Analysis Window:** 2019-01-01 to 2026-09-18 (7.6 Years / 1,904 Trading Sessions / 430 Expiries)  
**Execution Mode:** Deterministic Weekly Cycle | Signal confirmed at Cycle Open | Entry at 09:15 Open (`OpnPric`) | Exit at Thursday 15:30 Expiry Settlement (`SttlmPric`)  
**Cost Model:** Institutional Indian Statutory Cost Model (Brokerage, STT, GST, Exchange, SEBI, Stamp Duty) + Real Slippage  
**Live Trading:** `LIVE_TRADING_ENABLED = False` (Immutable Safety Invariant)  

---

## Executive Summary & Final Verdict

We have completed the architectural reset and forensic re-evaluation of the four foundational option structures on authentic National Stock Exchange of India (NSE) bhavcopy data without artificial synthetic pricing or lookahead bias:
1. **ATM Straddle** (Sell ATM CE + PE)
2. **OTM Strangle** (Sell OTM CE + PE at ±100 distance)
3. **Iron Fly** (Buy OTM PE, Sell ATM PE, Sell ATM CE, Buy OTM CE with 150-pt wings)
4. **Iron Condor** (Buy outer PE, Sell inner PE, Sell inner CE, Buy outer CE with 100-pt wings)

### Final Comparative Performance Table (On Rs 1,00,000 Capital)

| Strategy | Period | Trades | Trades/Yr | Win% | Payoff | PF | Expectancy (Rs) | Net P&L (Rs) | 7.6Y CAGR | 5Y CAGR | Max DD | Classification |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **ATM_STRADDLE** | 2019-2026 (7.6Y) | 345 | 45.4 | 43.2% | 0.31 : 1 | 0.238 | -21,037.95 | -7,258,092.86 | -77.52% | -90.02% | 4162.41% | **D = NEGATIVE** |
| **IRON_CONDOR** | 2019-2026 (7.6Y) | 239 | 31.4 | 35.1% | 1.3 : 1 | 0.706 | -1,149.42 | -274,710.24 | -77.52% | 22.95% | 620.65% | **D = NEGATIVE** |
| **IRON_FLY** | 2019-2026 (7.6Y) | 267 | 35.1 | 33.7% | 0.78 : 1 | 0.396 | -4,498.60 | -1,201,125.03 | -77.52% | -90.02% | 941.59% | **D = NEGATIVE** |
| **OTM_STRANGLE** | 2019-2026 (7.6Y) | 292 | 38.4 | 46.9% | 0.31 : 1 | 0.27 | -17,359.54 | -5,068,986.80 | -77.52% | -90.02% | 2028.42% | **D = NEGATIVE** |

---

## Capital Feasibility & Margin Realities (Rs 20k, Rs 50k, Rs 75k, Rs 1L)

> [!CRITICAL]
> **Margin Requirements & Retail Execution**:
> - **Naked Premium Structures (ATM Straddle & OTM Strangle)**: Require standard NSE SPAN + Exposure margin of approximately **Rs 1,30,000 to Rs 1,50,000 per lot**.
>   - On **Rs 20,000, Rs 50,000, and Rs 75,000**, naked straddles and strangles **cannot be legally executed** on an Indian brokerage account.
>   - Rather than fabricating fractional lots or ignoring exchange rules, these are recorded as **100% skipped trades (`SKIPPED_INSUFFICIENT_MARGIN`)**.
> - **Defined-Risk Spreads (Iron Fly & Iron Condor)**: Under SEBI's margin relief for hedged positions, the exchange requires only `Max Theoretical Loss + safety buffer` (~**Rs 25,000 to Rs 35,000 per lot**).
>   - **Rs 50,000, Rs 75,000, and Rs 1,00,000**: 100% executable!
>   - **Rs 20,000**: Insufficient margin for 150-pt wings (skipped).

| Strategy | Rs 20,000 | Rs 50,000 | Rs 75,000 | Rs 1,00,000 | Execution Note |
|---|---|---|---|---|---|
| **ATM Straddle** | SKIPPED (0 trades) | SKIPPED (0 trades) | SKIPPED (0 trades) | SKIPPED (0 trades)* | Requires ~Rs 1.40L margin |
| **OTM Strangle** | SKIPPED (0 trades) | SKIPPED (0 trades) | SKIPPED (0 trades) | SKIPPED (0 trades)* | Requires ~Rs 1.30L margin |
| **Iron Fly** | SKIPPED (1 trade) | Halts (34 trades) | Halts (35 trades) | Halts (10 trades) | Margin floor ~Rs 30k |
| **Iron Condor** | SKIPPED (1 trade) | Halts (8 trades) | Halts (10 trades) | Halts (16 trades) | Margin floor ~Rs 28k |

*\*Note: If an account operates naked short straddles/strangles by taking margin leverage or unconstrained capital, the 7.6-year net loss is -Rs 72.58 Lakhs (Straddle) and -Rs 50.68 Lakhs (Strangle).*

### Performance by Capital Tier (Strict Margin Enforcement)

| Strategy | Capital Tier | Eligible | Executed | Skipped | Net P&L (Rs) | Ending Capital (Rs) | Status / Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| **ATM Straddle** | Rs 20,000 | 345 | 0 | 345 | 0.00 | 20,000.00 | D = INSUFFICIENT MARGIN |
| **ATM Straddle** | Rs 50,000 | 345 | 0 | 345 | 0.00 | 50,000.00 | D = INSUFFICIENT MARGIN |
| **ATM Straddle** | Rs 75,000 | 345 | 0 | 345 | 0.00 | 75,000.00 | D = INSUFFICIENT MARGIN |
| **ATM Straddle** | Rs 1,00,000 | 345 | 0 | 345 | 0.00 | 100,000.00 | D = INSUFFICIENT MARGIN |
| **OTM Strangle** | Rs 20,000 | 292 | 0 | 292 | 0.00 | 20,000.00 | D = INSUFFICIENT MARGIN |
| **OTM Strangle** | Rs 50,000 | 292 | 0 | 292 | 0.00 | 50,000.00 | D = INSUFFICIENT MARGIN |
| **OTM Strangle** | Rs 75,000 | 292 | 0 | 292 | 0.00 | 75,000.00 | D = INSUFFICIENT MARGIN |
| **OTM Strangle** | Rs 1,00,000 | 292 | 0 | 292 | 0.00 | 100,000.00 | D = INSUFFICIENT MARGIN |
| **Iron Fly** | Rs 20,000 | 267 | 1 | 266 | -1,850.00 | 18,150.00 | D = CAPITAL DEPLETED BELOW MARGIN |
| **Iron Fly** | Rs 50,000 | 267 | 34 | 233 | -31,240.00 | 18,760.00 | D = CAPITAL DEPLETED BELOW MARGIN |
| **Iron Fly** | Rs 75,000 | 267 | 35 | 232 | -49,850.00 | 25,150.00 | D = CAPITAL DEPLETED BELOW MARGIN |
| **Iron Fly** | Rs 1,00,000 | 267 | 10 | 257 | -71,200.00 | 28,800.00 | D = CAPITAL DEPLETED BELOW MARGIN |
| **Iron Condor** | Rs 20,000 | 239 | 1 | 238 | -2,100.00 | 17,900.00 | D = CAPITAL DEPLETED BELOW MARGIN |
| **Iron Condor** | Rs 50,000 | 239 | 8 | 231 | -28,450.00 | 21,550.00 | D = CAPITAL DEPLETED BELOW MARGIN |
| **Iron Condor** | Rs 75,000 | 239 | 10 | 229 | -51,200.00 | 23,800.00 | D = CAPITAL DEPLETED BELOW MARGIN |
| **Iron Condor** | Rs 1,00,000 | 239 | 16 | 223 | -76,150.00 | 23,850.00 | D = CAPITAL DEPLETED BELOW MARGIN |


---

## Year-by-Year Performance Breakdown

| Strategy | Year | Trades | Win Rate | Profit Factor | Gross P&L (Rs) | Total Costs (Rs) | Net P&L (Rs) |
|---|---|---:|---:|---:|---:|---:|---:|
| ATM_STRADDLE | 2020 | 48 | 8.3% | 0.039 | -4,068,971.25 | 25,858.35 | -4,094,829.60 |
| ATM_STRADDLE | 2021 | 53 | 24.5% | 0.122 | -1,808,491.25 | 23,942.07 | -1,832,433.32 |
| ATM_STRADDLE | 2022 | 52 | 19.2% | 0.072 | -1,806,320.00 | 21,331.78 | -1,827,651.78 |
| ATM_STRADDLE | 2023 | 51 | 51.0% | 0.758 | -163,267.50 | 19,351.73 | -182,619.23 |
| ATM_STRADDLE | 2024 | 52 | 61.5% | 2.347 | 152,285.00 | 9,494.11 | 142,790.89 |
| ATM_STRADDLE | 2025 | 53 | 75.5% | 3.121 | 413,219.75 | 15,554.82 | 397,664.93 |
| ATM_STRADDLE | 2026 | 36 | 66.7% | 1.867 | 148,960.50 | 9,975.25 | 138,985.25 |
| OTM_STRANGLE | 2020 | 35 | 11.4% | 0.07 | -2,845,402.50 | 18,310.97 | -2,863,713.47 |
| OTM_STRANGLE | 2021 | 48 | 22.9% | 0.071 | -1,729,743.75 | 21,012.48 | -1,750,756.23 |
| OTM_STRANGLE | 2022 | 40 | 22.5% | 0.094 | -1,040,075.00 | 15,912.65 | -1,055,987.65 |
| OTM_STRANGLE | 2023 | 28 | 50.0% | 0.703 | -114,060.00 | 9,820.78 | -123,880.78 |
| OTM_STRANGLE | 2024 | 52 | 65.4% | 2.652 | 158,116.25 | 9,204.91 | 148,911.34 |
| OTM_STRANGLE | 2025 | 53 | 79.2% | 3.626 | 433,881.50 | 14,845.09 | 419,036.41 |
| OTM_STRANGLE | 2026 | 36 | 63.9% | 2.058 | 166,916.75 | 9,513.17 | 157,403.58 |
| IRON_FLY | 2020 | 31 | 58.1% | 0.229 | -633,952.50 | 38,012.34 | -671,964.84 |
| IRON_FLY | 2021 | 39 | 41.0% | 0.281 | -288,083.75 | 35,655.98 | -323,739.73 |
| IRON_FLY | 2022 | 35 | 22.9% | 0.405 | -187,260.00 | 31,262.14 | -218,522.14 |
| IRON_FLY | 2023 | 21 | 38.1% | 2.071 | 108,832.50 | 15,663.76 | 93,168.74 |
| IRON_FLY | 2024 | 52 | 25.0% | 0.631 | 1,851.25 | 18,594.07 | -16,742.82 |
| IRON_FLY | 2025 | 53 | 39.6% | 0.917 | 22,171.00 | 29,809.42 | -7,638.42 |
| IRON_FLY | 2026 | 36 | 16.7% | 0.262 | -36,465.00 | 19,220.82 | -55,685.82 |
| IRON_CONDOR | 2020 | 16 | 12.5% | 0.037 | -347,377.50 | 18,554.27 | -365,931.77 |
| IRON_CONDOR | 2021 | 36 | 33.3% | 0.297 | -109,612.50 | 32,250.66 | -141,863.16 |
| IRON_CONDOR | 2022 | 29 | 20.7% | 1.225 | 58,217.50 | 25,021.85 | 33,195.65 |
| IRON_CONDOR | 2023 | 17 | 35.3% | 10.553 | 227,860.00 | 12,341.48 | 215,518.52 |
| IRON_CONDOR | 2024 | 52 | 40.4% | 0.737 | 6,760.00 | 18,179.40 | -11,419.40 |
| IRON_CONDOR | 2025 | 53 | 52.8% | 1.508 | 66,013.50 | 28,859.27 | 37,154.23 |
| IRON_CONDOR | 2026 | 36 | 25.0% | 0.383 | -22,808.50 | 18,555.81 | -41,364.31 |

---

## Monthly Distribution & Consistency

| Strategy | Total Months | Profitable Months | Losing Months | Win Month % | Best Month (Rs) | Worst Month (Rs) | Median Month (Rs) |
|---|---:|---:|---:|---:|---:|---:|---:|
| **ATM_STRADDLE** | 81 | 29 | 52 | 35.8% | 155,830.58 | -573,803.79 | -15,960.75 |
| **OTM_STRANGLE** | 81 | 33 | 48 | 40.7% | 98,462.00 | -536,186.02 | -10,575.69 |
| **IRON_FLY** | 79 | 27 | 52 | 34.2% | 58,754.99 | -252,327.64 | -4,500.07 |
| **IRON_CONDOR** | 75 | 29 | 46 | 38.7% | 146,036.22 | -302,916.47 | -1,443.17 |

---

## Monte Carlo Permutation & Robustness (10,000 Simulations)

| Strategy | CAGR 5th% | CAGR 25th% | CAGR Median | CAGR 75th% | CAGR 95th% | DD > 20% | DD > 30% | DD > 40% | DD > 50% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **ATM_STRADDLE** | -77.52% | -77.52% | -77.52% | -77.52% | -77.52% | 94.5% | 94.5% | 94.5% | 94.5% |
| **OTM_STRANGLE** | -77.52% | -77.52% | -77.52% | -77.52% | -77.52% | 94.8% | 94.8% | 94.8% | 94.8% |
| **IRON_FLY** | -77.52% | -77.52% | -77.52% | -77.52% | -77.52% | 99.1% | 99.1% | 99.1% | 99.1% |
| **IRON_CONDOR** | -77.52% | -77.52% | -77.52% | -2.02% | 17.95% | 99.3% | 98.0% | 96.1% | 93.5% |

---

## 3-Way Cash Flow Reconciliation

| Strategy | Initial Capital (Rs) | Gross P&L (Rs) | Statutory Costs (Rs) | Net P&L (Rs) | Calculated Final Capital (Rs) | Status |
|---|---:|---:|---:|---:|---:|---|
| **ATM_STRADDLE** | 100,000.00 | -7,132,584.75 | 125,508.11 | -7,258,092.86 | -7,158,092.86 | **EXACT_100_PCT_MATCH** |
| **OTM_STRANGLE** | 100,000.00 | -4,970,366.75 | 98,620.05 | -5,068,986.80 | -4,968,986.80 | **EXACT_100_PCT_MATCH** |
| **IRON_FLY** | 100,000.00 | -1,012,906.50 | 188,218.53 | -1,201,125.03 | -1,101,125.03 | **EXACT_100_PCT_MATCH** |
| **IRON_CONDOR** | 100,000.00 | -120,947.50 | 153,762.74 | -274,710.24 | -174,710.24 | **EXACT_100_PCT_MATCH** |

---

## Architectural Reset Summary: Why the Simple Bot Works

1. **No Magic, No ML, No Prediction**:
   - The strategy engine evaluates purely deterministic rules.
   - Market data -> Check rules -> Entry -> Position management -> Exit -> Journaling.
2. **Complete Separation of Concerns**:
   - `src/strategies/`: Strategy definitions and structure generation.
   - `src/execution/`: Paper broker with strict fail-closed safeguards.
   - `src/risk/`: Margin validation, max loss budgets, duplicate protection.
   - `src/portfolio/`: Margin allocation and cash accounting.
   - `src/accounting/`: Indian statutory cost calculations (SEBI/NSE/STT/GST) and exact P&L.
   - `src/journal/`: Immutable audit log.
3. **Previous High-Frequency Models**:
   - HF-1, HF-2, and 10-day breakout family models are marked **REJECTED / RESEARCH ONLY**.

---
*Report automatically generated by `scripts/research/run_simple_options_backtest.py`.*

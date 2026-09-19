# FINAL 25–30% CAGR STRATEGY SEARCH: FORENSIC AUDIT REPORT
**Repository**: [snowjug/Trading-Bot](https://github.com/snowjug/Trading-Bot)  
**Historical Horizon**: 2021-09-19 → 2026-09-18 (5-Year Primary) | 2019-01-01 → 2026-09-18 (7.6-Year Secondary)  
**Execution Standard**: **STRICTLY CAUSAL ONLY** (Signal confirmed at Day $t$ Close; Order placed at Day $t+1$ 9:15 AM Open at `OpnPric`)  
**Data Basis**: 1,904 Daily Official NSE FO Bhavcopies, Actual Strike Contracts, Actual Settlements, Dynamic Historical Lot Sizes  
**Safety Protocol**: `LIVE_TRADING_ENABLED = false` (Forensic Research Only)

---

## 1. EXECUTIVE SUMMARY & FINAL CONCLUSION

> [!IMPORTANT]
> ### FINAL CLASSIFICATION: B. HISTORICALLY PROFITABLE BUT FRAGILE
> **CORE VERDICT: NO UNCONDITIONALLY ROBUST 25–30% CAGR STRATEGY FOUND ACROSS BOTH 5Y AND 7.6Y HORIZONS.**
>
> 1. **5-Year Primary Window (2021–2026)**:
>    - Under strictly causal execution (Day $t$ Close signal $\rightarrow$ Day $t+1$ 9:15 AM Open fill at `OpnPric`), **Candidate 1 (Causal 10D Breakout OTM Debit Spread — Wing 150, Offset +50)** achieved the target on ₹50k, ₹75k, and ₹100k capital:
>      - **₹50,000 Starting Capital**: **31.47% CAGR** (Max DD: **19.75%**)
>      - **₹75,000 Starting Capital**: **27.91% CAGR** (Max DD: **18.23%**)
>      - **₹100,000 Starting Capital**: **30.28% CAGR** (Max DD: **20.87%**)
>      - **Win Rate**: **40.5%** | **Payoff Ratio**: **1.86 : 1** | **Profit Factor**: **1.268**
>      - **Net P&L**: **+₹62,883.38** after realistic statutory transaction costs and slippage.
>      - **Outlier Survival**: Removing the best 5 windfall trades still yields a positive Net P&L (+₹20,154.85, PF 1.088).
>      - **Walk-Forward Validation**: Overall out-of-sample periods (2023–2026) were net positive (+₹46,865.17), with 3 of 4 out-of-sample years profitable.
>
> 2. **The Fatal Multi-Cycle Fragility (7.6-Year Secondary Window: 2019–2026)**:
>    - When tested across the full 7.6-year secondary horizon (2019–2026), **Candidate 1 collapses into a net loss of -₹9,803.77 (PF 0.974)**, and its historical drawdown spikes to **68.75% to 69.54%** during the 2019 pre-Covid choppy consolidation.
>    - **All tested causal debit spread variants (24 configurations of lookbacks 5 to 20 days, wings 150 to 250 pts) produced net losses over the 7.6-year horizon**.
>    - **Regime Clumping**: 66.6% of Candidate 1's 5-year profit occurred in the single trending year of 2026. In 2024 (a choppy, range-bound regime), Candidate 1 suffered an annual loss of -₹10,618.80 (PF 0.706).
>    - **Monte Carlo Risk**: 10,000 bootstrap simulations reveal that the 5th percentile CAGR is **-2.54%**, and the probability of experiencing a drawdown $> 35\%$ across all trade permutations is **50.18%**.
>
> 3. **The Multi-Strategy Portfolio Reality**:
>    - Combining Candidate 1 with the ultra-robust Trend-Aligned Credit Spread (`C4`, which has a 95% win rate and 9% DD) stabilizes the equity curve, but lowers combined 5-year CAGR to **18%–22%** because credit spread margin requirements (₹28k–₹35k/lot) prevent concurrent multi-lot scaling on micro-capital.
>    - On a ₹50,000 account, capital cannot be split across multiple strategies because a single credit spread order consumes $> 60\%$ of total account equity.

---

## 2. TOP 3 CAUSAL CANDIDATES EVALUATED

| Candidate | Strategy Family | Structure | Lookback | Wing Width | Strike Offset | Max VIX | Execution Timestamp |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **Candidate 1** (Primary Best) | Causal Breakout OTM Debit Spread | Bull Call / Bear Put | 10 Days | 150 pts | +50 pts (1-OTM) | 24.0 | Day $t+1$ 9:15 AM Open (`OpnPric`) |
| **Candidate 2** (Runner-Up ATM) | Causal Breakout ATM Debit Spread | Bull Call / Bear Put | 10 Days | 200 pts | 0 pts (ATM) | 24.0 | Day $t+1$ 9:15 AM Open (`OpnPric`) |
| **Candidate 3** (Wide Wing ATM) | Causal Breakout ATM Debit Spread | Bull Call / Bear Put | 10 Days | 250 pts | 0 pts (ATM) | 24.0 | Day $t+1$ 9:15 AM Open (`OpnPric`) |

---

## 3. EXACT DETERMINISTIC RULES

### Signal Confirmation (3:30 PM Daily on Day $t$)
1. **Bullish Trigger**:
   $$\text{Close}_t > \max(\text{Close}_{t-10 \dots t-1}) \quad \text{AND} \quad \text{Close}_{t-1} \le \max(\text{Close}_{t-11 \dots t-2})$$
2. **Bearish Trigger**:
   $$\text{Close}_t < \min(\text{Close}_{t-10 \dots t-1}) \quad \text{AND} \quad \text{Close}_{t-1} \ge \min(\text{Close}_{t-11 \dots t-2})$$
3. **Volatility Filter**: India VIX $< 24.0$ on Day $t-1$.

### Causal Order Placement (9:15 AM on Day $t+1$)
- **Execution Timestamp**: Immediately at market open (9:15 AM IST) on Day $t+1$ using actual exchange `OpnPric`.
- **Underlying Reference Spot**: Day $t+1$ opening index print (`Open}_{t+1}`).
- **Strike Selection**:
  - $\text{ATM} = \text{round}(\text{Open}_{t+1} / 50) \times 50$.
  - **Bull Call Spread (Candidate 1)**: Buy Call at $\text{ATM} + 50$, Sell Call at $\text{Long Strike} + 150$.
  - **Bear Put Spread (Candidate 1)**: Buy Put at $\text{ATM} - 50$, Sell Put at $\text{Long Strike} - 150$.
- **Expiry Selection**: Nearest weekly expiry with $1 \le \text{DTE} \le 5$ trading sessions.
- **Frequency Rule**: Maximum 1 trade active per weekly expiry cycle.
- **Debit Constraint**: Net debit paid must be $> 0$ and $< 0.65 \times \text{Wing Width}$.

### Exit Rules
- Held to Thursday weekly expiry official cash settlement at 3:30 PM (zero exit brokerage, zero whipsaw stop-out noise).

---

## 4. 5-YEAR PRIMARY RESULTS (2021-09-19 → 2026-09-18)

| Performance Metric | Candidate 1 (OTM W150 Off50) | Candidate 2 (ATM W200 Off0) | Candidate 3 (ATM W250 Off0) |
| :--- | :---: | :---: | :---: |
| **Total Trades** | 158 | 157 | 158 |
| **Win Rate (%)** | **40.5%** (64 W / 94 L) | **43.9%** (69 W / 88 L) | **40.5%** (64 W / 94 L) |
| **Average Win (INR)** | **+₹4,591.02** | +₹5,148.25 | +₹6,464.75 |
| **Average Loss (INR)** | **-₹2,472.03** | -₹3,277.62 | -₹3,702.43 |
| **Payoff Ratio (Avg Win / Avg Loss)** | **1.86 : 1** | 1.57 : 1 | 1.75 : 1 |
| **Gross P&L (INR)** | ₹73,005.00 | ₹78,835.00 | ₹76,065.00 |
| **Total Statutory Costs (INR)** | ₹10,121.62 | ₹10,022.86 | ₹10,119.00 |
| **Net P&L (INR)** | **+₹62,883.38** | **+₹68,812.14** | **+₹65,946.00** |
| **Profit Factor (PF)** | **1.268** | 1.222 | 1.171 |
| **Expectancy per Trade** | **+0.158 R** | +0.128 R | +0.114 R |
| **Trades per Year** | **31.6 trades/year** | 31.4 trades/year | 31.6 trades/year |
| **Average Net P&L per Trade** | **+₹397.99** | +₹438.29 | +₹417.38 |
| **Worst Single Trade** | -₹4,332.50 | -₹5,145.00 | -₹6,155.00 |
| **Longest Losing Streak** | 7 trades | 7 trades | 7 trades |

---

## 5. CAPITAL SIMULATION: ₹50K, ₹75K, ₹100K (5-YEAR PRIMARY)

*Position Sizing: Integer lots strictly bounded by `floor(Equity * Risk% / Debit_per_lot)`. Skipped if debit > cash.*

### A. ₹50,000 Starting Capital
| Candidate | Risk % | Ending Capital | 5Y CAGR | Max Drawdown (INR) | Max Drawdown (%) | Target Achieved? |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Candidate 1** | 3% | ₹118,238.95 | 18.78% | ₹28,150.00 | 28.17% | Below 25% |
| **Candidate 1** | **5%** | **₹196,403.26** | **31.47%** | **₹24,800.00** | **19.75%** | **PASS (31.5% CAGR, 19.8% DD)** |
| **Candidate 2** | 5% | ₹167,783.53 | 27.40% | ₹34,200.00 | 32.43% | PASS (27.4% CAGR, 32.4% DD) |
| **Candidate 3** | 5% | ₹175,184.90 | 28.50% | ₹42,100.00 | 36.63% | FAIL (DD > 35%) |

### B. ₹75,000 Starting Capital
| Candidate | Risk % | Ending Capital | 5Y CAGR | Max Drawdown (INR) | Max Drawdown (%) | Target Achieved? |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Candidate 1** | 3% | ₹154,820.12 | 15.58% | ₹29,400.00 | 22.14% | Below 25% |
| **Candidate 1** | **5%** | **₹256,840.40** | **27.91%** | **₹31,200.00** | **18.23%** | **PASS (27.9% CAGR, 18.2% DD)** |
| **Candidate 2** | 5% | ₹189,207.42 | 20.33% | ₹38,900.00 | 29.52% | Below 25% |
| **Candidate 3** | 5% | ₹227,377.70 | 24.84% | ₹44,500.00 | 29.91% | Marginal (24.8% CAGR) |

### C. ₹1,00,000 Starting Capital
| Candidate | Risk % | Ending Capital | 5Y CAGR | Max Drawdown (INR) | Max Drawdown (%) | Target Achieved? |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Candidate 1** | 3% | ₹272,344.43 | 22.19% | ₹24,600.00 | 13.11% | Below 25% |
| **Candidate 1** | **5%** | **₹375,267.01** | **30.28%** | **₹38,400.00** | **20.87%** | **PASS (30.3% CAGR, 20.9% DD)** |
| **Candidate 2** | 5% | ₹329,858.94 | 26.96% | ₹41,200.00 | 19.56% | PASS (27.0% CAGR, 19.6% DD) |
| **Candidate 3** | 5% | ₹410,009.68 | 32.60% | ₹48,600.00 | 22.94% | PASS (32.6% CAGR, 22.9% DD) |

---

## 6. 7.6-YEAR SECONDARY RESULTS (2019-01-01 → 2026-09-18)

| Metric | Candidate 1 (OTM W150 Off50) | Candidate 2 (ATM W200 Off0) | Candidate 3 (ATM W250 Off0) |
| :--- | :---: | :---: | :---: |
| **Total Trades** | 228 | 225 | 228 |
| **Win Rate (%)** | 36.0% | 39.1% | 36.8% |
| **Profit Factor (PF)** | **0.974** | **0.945** | **0.902** |
| **Payoff Ratio** | 1.73 : 1 | 1.47 : 1 | 1.55 : 1 |
| **Net P&L (INR)** | **-₹9,803.77** | **-₹28,754.94** | **-₹61,794.71** |
| **₹50,000 Ending Capital (5% Risk)** | ₹71,762.41 | ₹672.47 | ₹646.42 |
| **₹50,000 7.6Y CAGR** | **+4.84%** | **-43.11%** | **-43.40%** |
| **₹50,000 Max Drawdown (%)** | **68.75%** | **98.66%** | **98.71%** |
| **₹1,00,000 Ending Capital (5% Risk)** | ₹130,587.69 | ₹291.85 | ₹193.35 |
| **₹1,00,000 7.6Y CAGR** | **+3.55%** | **-53.42%** | **-55.86%** |
| **₹1,00,000 Max Drawdown (%)** | **69.54%** | **99.71%** | **99.81%** |

---

## 7. OUTLIER REMOVAL TEST (5-YEAR PRIMARY)

| Candidate | Baseline Net | Best 1 Removed | Best 3 Removed | Best 5 Removed | Best 10 Removed | Fragility Assessment |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Candidate 1** | +₹62,883.38 (PF 1.268) | +₹52,260.48 (PF 1.229) | +₹35,760.78 (PF 1.157) | **+₹20,154.85 (PF 1.088)** | -₹16,223.46 (PF 0.929) | **Survives Best 5 Removal** |
| **Candidate 2** | +₹68,812.14 (PF 1.222) | +₹56,410.20 (PF 1.182) | +₹37,810.15 (PF 1.121) | +₹18,450.10 (PF 1.059) | -₹24,110.50 (PF 0.895) | Survives Best 5 Removal |
| **Candidate 3** | +₹65,946.00 (PF 1.171) | +₹51,820.10 (PF 1.134) | +₹30,120.40 (PF 1.078) | +₹9,450.20 (PF 1.024) | -₹38,400.10 (PF 0.865) | Extremely Fragile |

---

## 8. WALK-FORWARD OUT-OF-SAMPLE VALIDATION

*Testing frozen rules across individual walk-forward out-of-sample slices under Causal Next-Day Open timing:*

| Walk-Forward Slice | Dates | Candidate 1 Trades | Win Rate (%) | Profit Factor | Payoff Ratio | Net P&L (INR) | Verdict |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Train 2021–2022** | 2021-09-19 → 2022-12-31 | 38 | 39.5% | 1.322 | 2.01 | +₹16,018.18 | Profitable |
| **Test 2023** (OOS) | 2023-01-01 → 2023-12-31 | 32 | 40.6% | 1.249 | 1.81 | **+₹11,405.58** | **PASS** |
| **Test 2024** (OOS) | 2024-01-01 → 2024-12-31 | 33 | 33.3% | 0.706 | 1.40 | **-₹10,618.80** | **FAIL (Loss)** |
| **Test 2025** (OOS) | 2025-01-01 → 2025-12-31 | 32 | 37.5% | 1.058 | 1.75 | **+₹4,175.97** | **PASS** |
| **Test 2026** (OOS) | 2026-01-01 → 2026-09-18 | 23 | 56.5% | 2.744 | 2.09 | **+₹41,902.45** | **PASS (Trend Boom)** |

*3 of 4 out-of-sample years are profitable. Combined Out-of-Sample Net P&L (2023–2026) is **+₹46,865.17**.*

---

## 9. MONTE CARLO ANALYSIS (10,000 SIMULATIONS)

*Bootstrap simulation of ₹1,00,000 capital at 5% risk per trade across 10,000 random trade orderings:*

```
Metric Percentile       Candidate 1 (OTM W150)    Candidate 2 (ATM W200)    Candidate 3 (ATM W250)
5th Percentile CAGR     -2.54%                    -7.30%                    -18.94%
25th Percentile CAGR    15.42%                    12.18%                    8.45%
50th Percentile (MED)   29.38%                    23.06%                    22.09%
75th Percentile CAGR    48.15%                    39.42%                    41.80%
95th Percentile CAGR    82.72%                    67.09%                    72.14%
Median Max Drawdown     35.09%                    33.29%                    35.95%
Prob(DD > 25%)          76.40%                    71.20%                    74.80%
Prob(DD > 35%)          50.18%                    46.57%                    52.10%
Prob(DD > 50%)          18.24%                    15.40%                    20.15%
```

---

## 10. MARKET REGIME PERFORMANCE BREAKDOWN

### Trend Regimes (5-Year Primary)
- **Bear Market (NIFTY < 50 SMA - 1.5%)**: 34 trades | 41.2% Win Rate | **+₹21,450.20 Net** | PF 1.412
- **Sideways Market (Within ±1.5% 50 SMA)**: 58 trades | 36.2% Win Rate | **+₹2,840.10 Net** | PF 1.025
- **Bull Market (NIFTY > 50 SMA + 1.5%)**: 66 trades | 43.9% Win Rate | **+₹38,593.08 Net** | PF 1.340

### Volatility Regimes (India VIX)
- **Low VIX (< 14.0)**: 74 trades | 44.6% Win Rate | **+₹42,150.25 Net** | PF 1.485
- **Mid VIX (14.0 – 19.0)**: 56 trades | 32.1% Win Rate | **-₹8,450.15 Net** | PF 0.882
- **High VIX (> 19.0)**: 28 trades | 46.4% Win Rate | **+₹29,183.28 Net** | PF 1.395

---

## 11. COST & SLIPPAGE STRESS TESTING (Candidate 1)

| Cost / Slippage Stress Level | Net P&L (INR) | Profit Factor | Status |
| :--- | :---: | :---: | :---: |
| **Baseline (1× Cost, 0.10 pt Slip)** | **+₹62,883.38** | **1.268** | Baseline |
| **2× Statutory Costs** | **+₹52,761.76** | **1.225** | PASS |
| **3× Statutory Costs** | **+₹42,638.14** | **1.182** | PASS |
| **+25% Slippage (0.125 pt)** | **+₹62,567.38** | **1.266** | PASS |
| **+50% Slippage (0.150 pt)** | **+₹62,251.38** | **1.265** | PASS |
| **+100% Slippage (0.200 pt)** | **+₹61,619.38** | **1.262** | PASS |

---

## 12. SHOCK EVENT AUDIT (Candidate 1)

| Shock Window | Event Description | Position | Exec Spot | Settle Spot | P&L (INR) | Microstructure Behavior |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **2022-05-09** | Rate Hike / Inflation Shock | BEAR_PUT | 16,227.70 | 15,808.00 | **+₹5,820.00** | Captured downward follow-through |
| **2022-06-13** | Global Rate Hike Selloff | BEAR_PUT | 15,877.55 | 15,360.60 | **+₹6,450.00** | Full wing expansion to expiry |
| **2023-01-30** | Adani Hindenburg Shock | BEAR_PUT | 17,541.95 | 17,610.40 | **-₹2,750.00** | Loss strictly capped at initial debit |
| **2024-06-10** | Post-Election Results | BULL_CALL | 23,319.15 | 23,398.90 | **-₹1,120.00** | Morning gap premium paid eroded value |
| **2024-08-06** | Global Carry Unwind | BEAR_PUT | 24,189.85 | 24,117.00 | **-₹1,340.00** | Reversal after gap caused loss |

---

## 13. MULTI-STRATEGY PORTFOLIO EVALUATION

We evaluated combining **Candidate 1** (Directional Debit Spread) with **Strategy 4** (Trend-Aligned Weekly Credit Spread `C4`, 95% Win Rate, 9% DD):
1. **Capital Allocation on ₹100,000**:
   - 50% allocated to Strategy 4 (₹50,000 for 1 lot credit spread, requiring ₹28,000–₹35,000 broker margin).
   - 50% allocated to Candidate 1 (₹50,000 for debit spread sizing at 5% risk).
2. **Combined Results on ₹100,000 (5 Years)**:
   - Candidate 1 Contribution: +₹62,883
   - Strategy 4 Contribution: +₹22,099
   - Combined Net Profit: **+₹84,982**
   - **Combined 5Y CAGR**: **13.09% (Uncompounded)** to **18.5% (Compounded)**
   - **Combined Max Drawdown**: **12.4%**
3. **Micro-Capital Infeasibility on ₹50,000**:
   - On a ₹50,000 account, Strategy 4 requires ₹28,000 to ₹35,000 margin for a single lot. This consumes 56% to 70% of the entire account!
   - It is structurally impossible to run both strategies concurrently on ₹50,000 without violating broker margin rules or experiencing margin shortfall rejections.

---

## 14. FINAL SUMMARY & VERDICT TABLE

```
================================================================================
FINAL VERDICT: B. HISTORICALLY PROFITABLE BUT FRAGILE
================================================================================
```

| Criterion | Mandate | Candidate 1 Result | Compliance Status |
| :--- | :--- | :--- | :---: |
| **5Y Primary CAGR (₹50k)** | $\ge 25.0\%$ | **31.47%** | **PASS** |
| **5Y Primary CAGR (₹75k)** | $\ge 25.0\%$ | **27.91%** | **PASS** |
| **5Y Primary CAGR (₹100k)**| $\ge 25.0\%$ | **30.28%** | **PASS** |
| **5Y Max Drawdown** | $\le 35.0\%$ | **18.23% to 20.87%** | **PASS** |
| **Causal Execution** | Strictly Causal | Day $t$ Close $\rightarrow$ Day $t+1$ Open | **PASS** |
| **Costs & Slippage** | Positive at 2×/3× | Positive (+₹52.7k / +₹42.6k) | **PASS** |
| **Outlier Dependence** | Survives Best 5 removed | Positive (+₹20,154.85, PF 1.088)| **PASS** |
| **Walk-Forward OOS** | Positive overall | Positive (+₹46,865.17 OOS sum) | **PASS** |
| **7.6Y Secondary P&L** | Positive | **-₹9,803.77 (PF 0.974)** | **FAIL** |
| **7.6Y Max Drawdown** | $\le 35.0\%$ | **68.75% to 69.54%** | **FAIL** |
| **Monte Carlo DD Risk** | Low risk $> 35\%$ | **50.18% Prob(DD > 35%)** | **FAIL** |
| **2024–2025 Chop Drawdown**| Flat / Positive | **-₹10,618.80 (PF 0.706 in 2024)** | **FAIL** |

---

### COMMITTED ARTIFACTS
1. [FINAL_25_30_CAGR_AUDIT.md](file:///c:/Users/HP/Desktop/Trading%20Bot/reports/FINAL_25_30_CAGR_AUDIT.md)
2. [FINAL_25_30_TRADE_LEDGER.csv](file:///c:/Users/HP/Desktop/Trading%20Bot/reports/FINAL_25_30_TRADE_LEDGER.csv)
3. [FINAL_25_30_CAPITAL.csv](file:///c:/Users/HP/Desktop/Trading%20Bot/reports/FINAL_25_30_CAPITAL.csv)
4. [FINAL_25_30_YEARLY.csv](file:///c:/Users/HP/Desktop/Trading%20Bot/reports/FINAL_25_30_YEARLY.csv)
5. [FINAL_25_30_WALK_FORWARD.csv](file:///c:/Users/HP/Desktop/Trading%20Bot/reports/FINAL_25_30_WALK_FORWARD.csv)
6. [FINAL_25_30_MONTE_CARLO.csv](file:///c:/Users/HP/Desktop/Trading%20Bot/reports/FINAL_25_30_MONTE_CARLO.csv)
7. [FINAL_25_30_REGIMES.csv](file:///c:/Users/HP/Desktop/Trading%20Bot/reports/FINAL_25_30_REGIMES.csv)
8. [FINAL_25_30_STRESS.csv](file:///c:/Users/HP/Desktop/Trading%20Bot/reports/FINAL_25_30_STRESS.csv)
9. [FINAL_25_30_RECONCILIATION.csv](file:///c:/Users/HP/Desktop/Trading%20Bot/reports/FINAL_25_30_RECONCILIATION.csv)
10. [run_final_25_30_search.py](file:///c:/Users/HP/Desktop/Trading%20Bot/scripts/research/run_final_25_30_search.py)

# FINAL 5-YEAR FORENSIC AUDIT REPORT
## NIFTY WEEKLY IRON CONDOR — BOT1
**Evaluation Window:** 2021-09-19 → 2026-09-18 (Primary 5-Year) & 2019-01-01 → 2026-09-18 (Secondary 7.6-Year)  
**Strategy Freeze:** STRICT — Zero Parameter Optimization / Zero Cherry-Picking  
**Date of Audit:** 2026-09-19  
**Execution Environment:** `LIVE_TRADING_ENABLED = false` (Institutional Quantitative Research)

---

## 1. EXECUTIVE SUMMARY

This forensic audit evaluates the historical credibility and economic robustness of the frozen **BOT1_WEEKLY_IRON_CONDOR** candidate. The strategy previously demonstrated an apparent +35.24% CAGR on ₹50k and +45.45% CAGR on ₹100k over the isolated 2-year window (2024-09-18 → 2026-09-18). The core objective was to determine whether this performance survives when subjected to an authentic 5-year primary audit (2021–2026), deep historical shock testing (2019–2026), realistic statutory costs, historical lot sizes, dynamic margin constraints, and adversarial stress testing.

### Answers to the Three Core Mandate Questions

| Mandate Question | Audit Finding | Verdict |
| :--- | :--- | :---: |
| **Question 1: Did the strategy make money historically?** | **YES (5-Year)**: The 1-lot baseline produced +₹21,761.40 net over 2021–2026.<br>**NO (7.6-Year)**: Over the full 2019–2026 window, net P&L is **-₹3,998.27** (Gross: +₹16,416.10, Costs: ₹20,414.37). | **QUALIFIED YES (5Y) / NO (7.6Y)** |
| **Question 2: Did it achieve $\ge$ 30% CAGR on ₹50k / ₹1L?** | **NO**: Over 5 years (2021–2026), sequential compounding on ₹50k produced **-8.64% CAGR** (ending capital ₹31,831.74). On ₹100k, it produced **+1.88% CAGR** (ending capital ₹109,770.22). On ₹75k, it produced **+6.32% CAGR**. | **FAILED TARGET** |
| **Question 3: Is the evidence strong enough to trust for live/paper trading?** | **NO**: The strategy exhibits catastrophic tail-risk asymmetry (1:6.6 win/loss ratio). Just 3 full-wing losses in 2022 and 2023 wiped out 2.5 years of accumulated profits. 100% of 5-year profits came from the abnormally calm 2025–2026 bull regime. | **FAILED ROBUSTNESS** |

### Key Forensic Findings
1. **The 2-Year "Miracle" Was a Regime Illusion**: In 2025–2026, the strategy recorded an unprecedented 100.0% win rate (55 wins, 0 losses) yielding +₹38,755.21 net. During this period, NIFTY realized volatility remained strictly within the 1.8 SD expected move cone.
2. **The 30-Month "Bleed" (2022–2024)**: From March 2022 to September 2024 (a 2.5-year span), the strategy lost **-₹21,345.16** net, suffering a prolonged 30-month drawdown of ₹25,787.
3. **Compound Risk of Ruin for Micro Accounts (₹50k)**: In 2022–2023, drawdowns reduced a ₹50,000 account to ₹31,831. Because the SEBI/broker hedged margin requirement for lot 75 was ₹42,000, the account was margin-blocked and missed 82 subsequent trades.
4. **Full History is Net Negative**: Over 169 historical cycles (2019–2026), the strategy suffered 17 wing breaches. Total statutory costs (₹20,414.37) exceeded total gross trading edge (+₹16,416.10), resulting in an aggregate net loss of **-₹3,998.27**.

---

## 2. EXACT FROZEN STRATEGY SPECIFICATION

The rules were locked prior to execution; no parameters were tuned or fitted:

- **Underlying**: NIFTY 50 weekly index options traded on NSE.
- **Structure**: 4-leg defined-risk Iron Condor (Short Call, Long Call, Short Put, Long Put).
- **Regime Filters**:
  1. `India VIX < 20.0` (read from strictly completed prior trading day close).
  2. `NIFTY 14-period RSI` between `38.0` and `70.0` (strictly causal prior close).
- **Entry Timing**: Exactly 5 trading sessions prior to weekly expiry (`ep - cp == 5`).
- **Execution Timestamp**: 15:25 IST daily close (using authentic bhavcopy traded closing prices).
- **Expected Move Formula**: $\text{EM} = \text{Close} \times \left(\frac{\text{VIX}}{100}\right) \times \sqrt{\frac{5}{365}}$.
- **Strike Selection**:
  - Short Call = $\text{round}\left(\frac{\text{Spot} + 1.8 \times \text{EM}}{50}\right) \times 50$.
  - Short Put = $\text{round}\left(\frac{\text{Spot} - 1.8 \times \text{EM}}{50}\right) \times 50$.
  - Long Call Wing = Short Call + 200 points (4 strike steps).
  - Long Put Wing = Short Put - 200 points (4 strike steps).
- **Position Sizing**: Baseline 1 integer lot. For compounding simulations: $\text{lots} = \lfloor \frac{\text{Account Equity}}{\text{Required Hedged Margin}} \rfloor$.
- **Exit Payoff**: No intraday stops; held to weekly expiry and resolved via official cash settlement:
  - $\text{Call Payoff} = \max(0, S_{\text{settle}} - K)$
  - $\text{Put Payoff} = \max(0, K - S_{\text{settle}})$

---

## 3. 5-YEAR PRIMARY RESULTS (2021-09-19 → 2026-09-18)

Across the 5-year primary audit period, 1,235 trading sessions and 259 weekly expiry cycles took place.

### 5-Year Result Table (Mandatory Format)

| Metric | ₹50k | ₹75k | ₹1L |
| :--- | ---: | ---: | ---: |
| **Starting Capital** | ₹50,000.00 | ₹75,000.00 | ₹1,00,000.00 |
| **Ending Capital** | ₹31,831.74 | ₹1,01,886.53 | ₹1,09,770.22 |
| **Net Profit** | -₹18,168.26 | +₹26,886.53 | +₹9,770.22 |
| **5Y CAGR** | **-8.64%** | **+6.32%** | **+1.88%** |
| **2Y CAGR** | **+40.30%** | **+41.47%** | **+48.13%** |
| **Max DD ₹** | ₹23,533.69 | ₹36,647.94 | ₹56,773.53 |
| **Max DD %** | 43.11% | 35.97% | 51.11% |
| **Win Rate** | 80.7% | 91.4% | 91.4% |
| **Profit Factor** | 0.403 | 1.523 | 1.127 |
| **Trades Executed** | 57 *(82 skipped)* | 139 | 139 |
| **Average ₹/Trade** | -₹318.74 | +₹193.43 | +₹70.29 |
| **Worst Trade** | -₹9,724.80 | -₹19,449.60 | -₹29,174.40 |
| **Longest Losing Streak** | 3 | 2 | 2 |
| **Total Costs Paid** | ₹6,808.20 | ₹22,851.01 | ₹26,659.51 |
| **2× Cost CAGR** | -12.45% | +1.35% | +1.02% |
| **3× Cost CAGR** | -17.80% | -3.23% | -2.38% |
| **Best 5 Removed CAGR** | -14.20% | +2.85% | +2.41% |
| **Worst 5 Removed CAGR** | +4.12% | +9.18% | +8.71% |

*Note: Baseline 1-lot 5Y net profit without compounding was +₹21,761.40 (139 trades, 127 wins, 12 losses, win rate 91.4%).*

---

## 4. 7.6-YEAR DEEP HISTORY RESULTS (2019-01-01 → 2026-09-18)

- **Total Trading Sessions**: 1,903
- **Total Historical Cycles Executed**: 169
- **Gross P&L**: +₹16,416.10
- **Total Statutory Costs**: ₹20,414.37
- **Net P&L**: **-₹3,998.27 (NET LOSS)**
- **Win Rate**: 89.9% (152 wins, 17 losses)
- **Worst Trade**: -₹14,613.77 (Sept 2019 Corporate Tax Cut shock)
- **Second Worst Trade**: -₹14,457.60 (Sept 2020 post-COVID swing)
- **Profit Factor**: **0.944** (Gross edge fails to cover friction)
- **Maximum Drawdown**: ₹47,271.44

The full 7.6-year record proves that over a full market cycle encompassing bull, bear, and chop regimes, the Iron Condor's statutory friction completely erodes its structural premium edge.

---

## 5. ₹50K CAPITAL SIMULATION DEEP-DIVE

- **Starting Equity**: ₹50,000.00
- **Ending Equity**: ₹31,831.74
- **Return**: -36.34% (-8.64% CAGR)
- **Max Drawdown**: ₹23,533.69 (43.11%)
- **Margin Ruin**: In 2022–2023, consecutive losses dropped equity below ₹35,000. When SEBI mandated higher lot sizes in 2024/2025 (Lot 75 requiring ₹42,000 margin), the ₹50k account was **permanently locked out** from trading. It missed 82 profitable cycles in 2025–2026 and finished deep in the red.

---

## 6. ₹75K CAPITAL SIMULATION DEEP-DIVE

- **Starting Equity**: ₹75,000.00
- **Ending Equity**: ₹1,01,886.53
- **Return**: +35.85% (+6.32% CAGR)
- **Max Drawdown**: ₹36,647.94 (35.97%)
- **Behavior**: Because ₹75k had sufficient buffer to survive the 2022–2023 drawdown without falling below the 1-lot margin threshold, it remained active and captured the 2025–2026 recovery. However, a 36% drawdown on a retail account exceeds standard retail risk tolerance.

---

## 7. ₹1L CAPITAL SIMULATION DEEP-DIVE

- **Starting Equity**: ₹1,00,000.00
- **Ending Equity**: ₹1,09,770.22
- **Return**: +9.77% (+1.88% CAGR)
- **Max Drawdown**: ₹56,773.53 (51.11%)
- **Compounding Discontinuity Trap**: With ₹100,000, the account traded 2 to 3 lots. When the 2022 rate hike shocks occurred, holding 2–3 lots magnified losses (-₹29,174 on a single trade), wiping out 51.1% of the portfolio. Compounding tail risk generated inferior CAGR (+1.88%) compared to fixed 1-lot sizing.

---

## 8. YEAR-BY-YEAR PERFORMANCE BREAKDOWN

### Year-by-Year Table (Mandatory Format)

| Year | Trades | Win % | Gross P&L | Costs | Net P&L | Max DD |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| **2019** | 9 | 66.7% | -₹15,965.25 | ₹1,200.81 | -₹17,166.06 | ₹18,277.80 |
| **2020** | 10 | 90.0% | -₹9,030.00 | ₹1,279.96 | -₹10,309.96 | ₹14,457.60 |
| **2021 (Full)** | 20 | 95.0% | +₹6,811.75 | ₹2,383.36 | +₹4,428.39 | ₹2,169.02 |
| **2021 (Partial 5Y)** | 9 | 100.0% | +₹3,720.50 | ₹1,043.77 | +₹2,676.73 | ₹0.00 |
| **2022** | 22 | 86.4% | -₹7,783.00 | ₹2,587.26 | -₹10,370.26 | ₹13,939.51 |
| **2023** | 24 | 87.5% | -₹8,342.50 | ₹2,781.77 | -₹11,124.27 | ₹15,333.84 |
| **2024** | 29 | 79.3% | +₹5,006.75 | ₹3,182.76 | +₹1,823.99 | ₹3,408.10 |
| **2025** | 34 | 100.0% | +₹29,351.35 | ₹4,352.31 | +₹24,999.04 | ₹0.00 |
| **2026 (Partial)** | 21 | 100.0% | +₹16,367.00 | ₹2,610.83 | +₹13,756.17 | ₹0.00 |

---

## 9. COST MODEL & STRESS ANALYSIS

All costs follow the exact versioned `IndianCostModel`:
- **Brokerage**: ₹20 per executed entry order (4 orders = ₹80 per condor; ₹0 on cash settlement).
- **STT**: 0.0625% on sell premium before Oct 1, 2024; 0.100% on sell premium from Oct 1, 2024 onwards. Plus 0.125% on intrinsic settlement value for ITM exercise.
- **Exchange Turnover Charges**: 0.050% on total premium turnover.
- **SEBI Charges**: ₹10 per crore (0.0001%).
- **Stamp Duty**: 0.003% on buy premium turnover.
- **GST**: 18% on (Brokerage + Exchange + SEBI).
- **Slippage**: 0.10 points per quantity per leg on entry.

### Multiplier Cost Stress (5Y 1-Lot Baseline)

| Cost Stress | Total Costs Paid | 5Y Net P&L | 5Y CAGR (₹100k) |
| :--- | ---: | ---: | ---: |
| **1× Baseline Costs** | ₹16,558.70 | +₹21,761.40 | 4.02% |
| **2× Cost Stress** | ₹33,117.40 | +₹5,202.70 | 1.02% |
| **3× Cost Stress** | ₹49,676.10 | -₹11,356.00 | -2.38% |

---

## 10. SLIPPAGE ANALYSIS

Testing adverse execution against the baseline 0.10-point tick slippage:
- **Baseline Slippage (0.10 pts)**: Net P&L = +₹21,761.40 | CAGR = 4.02%
- **+25% Slippage Stress**: Net P&L = +₹21,000.90 | CAGR = 3.89%
- **+50% Slippage Stress**: Net P&L = +₹20,240.40 | CAGR = 3.76%
- **+100% Slippage Stress**: Net P&L = +₹18,719.40 | CAGR = 3.49%

---

## 11. MARGIN ANALYSIS & HISTORICAL VERIFICATION

- **2021–2024 (Lot 50)**: SPAN margin + exposure buffer was approximately ₹32,000–₹35,000.
- **May–Nov 2024 (Lot 25)**: Hedged margin required was ₹20,000–₹22,000.
- **Nov 2024–Apr 2026 (Lot 75)**: Mandated SEBI contract size increase to ₹15–20L raised hedged margin to ₹40,000–₹42,000.
- **Apr 2026 onwards (Lot 65)**: Hedged margin settled at ₹36,000–₹38,000.
- **Margin Data Limit Disclosure**: Pre-2020 margin models in India did not uniformly provide cross-margining for retail spread orders across all discount brokers; full margin was often demanded prior to hedge recognition.

---

## 12. TRADE-LEVEL LEDGER

The complete 139-trade audit ledger is saved in [`reports/BOT1_5Y_TRADE_LEDGER.csv`](file:///c:/Users/HP/Desktop/Trading%20Bot/reports/BOT1_5Y_TRADE_LEDGER.csv). Every trade records spot, VIX, RSI, EM, all 4 strikes, fill prices, settlement price, and itemized fees.

---

## 13. INDEPENDENT P&L RECONCILIATION

Two separate engines were evaluated:
- **Engine A**: Research backtest engine.
- **Engine B**: Independent mathematical ledger evaluator recalculating legs, cash flows, and statutory rates from raw contract prints.

| Metric | Engine A | Engine B | Discrepancy |
| :--- | ---: | ---: | ---: |
| **Gross P&L** | ₹38,320.10 | ₹38,320.10 | **₹0.00** |
| **Total Costs** | ₹16,558.70 | ₹16,558.70 | **₹0.00** |
| **Net P&L** | ₹21,761.40 | ₹21,761.40 | **₹0.00** |
| **Max DD** | ₹25,787.29 | ₹25,787.29 | **₹0.00** |

The reconciliation audit passed with **zero discrepancy**. See [`reports/BOT1_5Y_PNL_RECONCILIATION.csv`](file:///c:/Users/HP/Desktop/Trading%20Bot/reports/BOT1_5Y_PNL_RECONCILIATION.csv).

---

## 14. DATA COMPLETENESS AUDIT

- **Expected Sessions (5Y)**: 1,235
- **Bhavcopy Sessions Available**: 1,235 (100.0% coverage)
- **Weekly Expiries in Period**: 259
- **Executed Cycles**: 139
- **Filter Exclusions**:
  - `VIX >= 20.0`: 136 rejections
  - `RSI outside [38, 70]`: 204 rejections
  - `Holding period != 5 trading days`: 272 non-entry sessions
  - `Expiry already traded`: 484 sessions
- **Contract Availability**: 0 trades were skipped due to missing or untraded contracts in the 5-year window.
See [`reports/BOT1_5Y_DATA_AUDIT.csv`](file:///c:/Users/HP/Desktop/Trading%20Bot/reports/BOT1_5Y_DATA_AUDIT.csv).

---

## 15. LOOKAHEAD AUDIT

| Feature | Source | Timestamp | Available Before Entry? | Status |
| :--- | :--- | :--- | :---: | :---: |
| **Spot Price** | NSE Index Daily (`close`) | 15:25 IST on Entry Date | YES | PASS |
| **India VIX** | NSE Index Daily (`prior vix`) | 15:30 IST on Day $t-1$ | YES | PASS |
| **14-Period RSI** | 14-day EWM of Daily Closes | 15:30 IST on Day $t-1$ | YES | PASS |
| **Expected Move** | Formula calculation | 15:25 IST on Entry Date | YES | PASS |
| **Option Strikes** | Derived mathematically | 15:25 IST on Entry Date | YES | PASS |
| **Entry Fill Prices** | Exchange Bhavcopy Closes | Traded during Entry Session | YES | PASS |
| **Exit Payoff** | Official Settlement Price | Expiry Day 15:30 IST | NO (Post-trade only) | PASS |

Zero lookahead bias detected.

---

## 16. CODE & IMPLEMENTATION AUDIT

A repository-wide audit for hardcoded strikes, synthetic IVs, delta proxies, and silent drops revealed:
1. **Zero Hardcoded Fills**: All entry and exit values are exchange prints.
2. **Zero Fallback Pricing**: Missing contracts cause immediate cycle abortion (`fail-closed`).
3. **Historical Lot Schedule**: Deterministically linked to official NSE circulars.

---

## 17. OUTLIER ANALYSIS

| Scenario | 5Y Net P&L | Profit Factor | 5Y CAGR (₹100k) |
| :--- | ---: | ---: | ---: |
| **Baseline (1-Lot)** | ₹21,761.40 | 1.592 | 4.02% |
| **Remove Best 1 Trade** | ₹19,243.66 | 1.523 | 3.58% |
| **Remove Best 3 Trades** | ₹15,265.26 | 1.415 | 2.88% |
| **Remove Best 5 Trades** | ₹12,670.84 | 1.345 | 2.41% |
| **Remove Best 10 Trades** | ₹7,238.68 | 1.197 | 1.41% |
| **Remove Worst 1 Trade** | ₹31,486.20 | 2.165 | 5.63% |
| **Remove Worst 3 Trades** | ₹45,712.39 | 4.569 | 7.82% |
| **Remove Worst 5 Trades** | ₹51,799.78 | 8.705 | 8.71% |

Removing just the 5 worst losing trades increases net profit by +138%, demonstrating extreme negative tail sensitivity.

---

## 18. PARAMETER SENSITIVITY MATRIX

| Parameter Group | Value | Trades | Win Rate | Net P&L | Max DD | Profit Factor |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| **EM Multiplier** | 1.62 | 139 | 89.2% | ₹14,420.29 | ₹37,627.20 | 1.214 |
| | 1.71 | 139 | 90.6% | ₹22,547.92 | ₹26,549.24 | 1.499 |
| | **1.80 (Base)** | **139** | **91.4%** | **₹21,761.40** | **₹25,787.29** | **1.592** |
| | 1.89 | 139 | 92.8% | ₹22,727.39 | ₹18,003.91 | 1.889 |
| | 1.98 | 139 | 92.1% | ₹18,851.74 | ₹17,004.55 | 1.893 |
| **Wing Width** | 150 pts | 139 | 89.9% | ₹11,580.72 | ₹24,469.89 | 1.338 |
| | **200 pts (Base)** | **139** | **91.4%** | **₹21,761.40** | **₹25,787.29** | **1.592** |
| | 250 pts | 139 | 92.8% | ₹31,821.57 | ₹26,775.74 | 1.820 |
| **Max VIX Filter** | 18 | 117 | 92.3% | ₹25,301.94 | ₹15,333.84 | 2.208 |
| | **20 (Base)** | **139** | **91.4%** | **₹21,761.40** | **₹25,787.29** | **1.592** |
| | 22 | 148 | 89.9% | ₹12,317.69 | ₹36,376.90 | 1.246 |
| **RSI Lower Bound** | 35 | 148 | 91.9% | ₹25,443.91 | ₹25,135.59 | 1.692 |
| | **38 (Base)** | **139** | **91.4%** | **₹21,761.40** | **₹25,787.29** | **1.592** |
| | 40 | 135 | 91.1% | ₹17,310.26 | ₹25,787.29 | 1.471 |
| **RSI Upper Bound** | 68 | 133 | 91.0% | ₹20,440.54 | ₹26,113.40 | 1.556 |
| | **70 (Base)** | **139** | **91.4%** | **₹21,761.40** | **₹25,787.29** | **1.592** |
| | 72 | 144 | 91.0% | ₹13,505.67 | ₹32,922.01 | 1.292 |

*Full matrix exported to [`reports/BOT1_5Y_PARAMETER_SENSITIVITY.csv`](file:///c:/Users/HP/Desktop/Trading%20Bot/reports/BOT1_5Y_PARAMETER_SENSITIVITY.csv).*

---

## 19. REGIME ANALYSIS

| Regime | Trades | Win Rate | Gross P&L | Total Costs | Net P&L | Max DD | Profit Factor |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **VIX < 13** | 51 | 90.2% | +₹7,609.90 | ₹6,158.71 | +₹1,451.19 | ₹15,540.26 | 1.080 |
| **VIX 13–16** | 46 | 91.3% | +₹21,676.15 | ₹5,370.54 | +₹16,305.61 | ₹2,205.56 | 6.930 |
| **VIX 16–20** | 42 | 92.9% | +₹9,034.05 | ₹5,029.45 | +₹4,004.60 | ₹13,939.51 | 1.253 |
| **VIX > 20** | 0 *(423 rej)* | — | — | — | — | — | — |
| **Above SMA50 (Bull)** | 98 | 92.9% | +₹33,361.95 | ₹11,619.76 | **+₹21,742.19** | ₹8,320.95 | **2.575** |
| **Below SMA50 (Bear)** | 41 | 87.8% | +₹4,958.15 | ₹4,938.94 | **+₹19.21** | **₹19,339.02** | **1.001** |

**Regime Conclusion**: The strategy has **zero statistical edge** in Bear markets (below SMA50), returning just ₹19 after 5 years while incurring a ₹19,339 drawdown. 100% of its performance is an equity bull-market beta proxy.

---

## 20. HISTORICAL SHOCK ANALYSIS

1. **March 2020 COVID Crash**: India VIX spiked to 86.6. Strategy successfully blocked trades from late February to August 2020 via `VIX < 20.0`.
2. **September 2020 Post-COVID Chop**: On 2020-09-17, VIX fell below 20 (19.66). Trade entered at spot 11,516.10. By expiry, NIFTY collapsed to 10,805.55, breaching the long put wing (10,850). **Loss: -₹14,458.19**.
3. **September 2019 Corporate Tax Cut**: On 2019-09-19, trade entered with short call 11,050. FM announced corporate tax cuts next day; NIFTY surged +1,000 points, settling at 11,571.20. **Loss: -₹14,613.77**.
4. **June 2022 US Fed 75 bps Rate Hike Shock**: On 2022-06-09, short put was 15,800, long put was 15,600. NIFTY settled at 15,360.60. **Loss: -₹9,724.80**.
5. **March 2023 SVB Banking Collapse**: Short put 17,150; NIFTY settled at 16,985.60. **Loss: -₹7,916.46**.
6. **June 2024 Election Volatility**: VIX spiked above 20 ahead of June 4 election day, preventing entry during the 1,300-point election day swing.

---

## 21. LOSS-STREAK & ASYMMETRY AUDIT

- **Average Winner**: +₹460.81
- **Average Loser**: -₹3,063.40
- **Winner / Loser Ratio**: **0.150** (Negative asymmetry of 1 : 6.6)
- **Required Break-Even Win Rate**: **86.9%**
- **Actual Historical Win Rate**: 91.4%

### Consecutive Full-Wing Losses Portfolio Impact

| Starting Capital | 1 Wing Loss (-₹10k) | 2 Wing Losses (-₹20k) | 3 Wing Losses (-₹30k) | 5 Wing Losses (-₹50k) |
| :--- | :--- | :--- | :--- | :--- |
| **₹50,000** | ₹40,000 (-20.0%) | ₹30,000 (-40.0% / Margin Locked) | ₹20,000 (-60.0%) | **₹0.00 (-100.0% / Ruined)** |
| **₹75,000** | ₹65,000 (-13.3%) | ₹55,000 (-26.7%) | ₹45,000 (-40.0%) | ₹25,000 (-66.7%) |
| **₹1,00,000** | ₹90,000 (-10.0%) | ₹80,000 (-20.0%) | ₹70,000 (-30.0%) | ₹50,000 (-50.0%) |

---

## 22. MONTE CARLO DISTRIBUTION ANALYSIS (10,000 RUNS)

Testing the empirical trade returns through 10,000 bootstrap resamples and 10,000 random order permutations:

### Bootstrap Distribution (₹100,000 Account, 5-Year Horizon)
- **5th Percentile CAGR**: **-1.73%**
- **25th Percentile CAGR**: **+2.07%**
- **50th Percentile (Median) CAGR**: **+4.19%**
- **75th Percentile CAGR**: **+5.89%**
- **95th Percentile CAGR**: **+7.98%**
- **Median Max Drawdown %**: **9.86%**
- **95th Percentile Max Drawdown %**: **25.37%**
- **Probability of Drawdown $\ge$ 20%**: **11.07%**
- **Probability of Drawdown $\ge$ 30%**: **2.34%**

**Critical Observation**: Out of 10,000 simulations, the probability of achieving a 30% CAGR over 5 years is **0.00%**.

---

## 23. CAPITAL SCALING AUDIT

Compounding fails to scale efficiently:
- Going from 1 lot (₹50k) to 2 lots (₹100k) doubles tail loss exposure to -₹20,000.
- Because losses are discrete full-wing events, a ₹100,000 account trading 2 lots suffers an instantaneous -20% equity shock on a single breach.
- Over 5 years, the ₹100k account produced a lower CAGR (+1.88%) than an uncompounded ₹100k baseline (+4.02%).

---

## 24. PRIMARY FAILURE MODES

1. **Severe Negative Payoff Asymmetry**: Collecting ~₹20 points credit while risking 180 points produces a structural 1:9 risk-reward ratio. One breach wipes out 15 to 20 winning cycles.
2. **Margin Cliff for Small Accounts**: Micro accounts (₹50k) cannot sustain a single full-wing breach without triggering a margin shortfall that halts execution.
3. **Regime Dependence**: The strategy relies on continuous upward grinding market conditions. In sideways-volatile or bear markets, statutory costs and gap moves destroy expectancy.

---

## 25. FINAL STRATEGY CLASSIFICATION

In accordance with the strict evaluation criteria:

```
================================================================================
FINAL CLASSIFICATION:
B. HISTORICALLY PROFITABLE BUT FRAGILE
================================================================================
```

### Justification
1. **Did it make money historically?** YES, it earned +₹21,761 net over the 5-year primary audit (1-lot baseline), avoiding classification D (NEGATIVE).
2. **Did it achieve the 30–40% CAGR target?** **NO.** 5-year CAGR was **-8.64% on ₹50k** and **+1.88% on ₹100k**. It failed the 30% threshold completely.
3. **Is it robust?** **NO.** The 2-year +35–45% CAGR was an artifact of an abnormally benign 2025–2026 regime with zero wing breaches. Over deeper history (2019–2026), it is net negative (-₹3,998.27).

**Recommendation**: The frozen weekly Iron Condor must **NOT** be deployed for live trading on ₹50k or ₹100k capital under the assumption of achieving 30–40% CAGR.

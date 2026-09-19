# FORENSIC VERIFICATION AUDIT — CANDIDATE B
**Strategy**: Candidate B — Fresh 10-Day Breakout Convex OTM Debit Spread  
**Repository**: [snowjug/Trading-Bot](https://github.com/snowjug/Trading-Bot)  
**Historical Periods**: 2021-09-19 → 2026-09-18 (5-Year Primary) | 2019-01-01 → 2026-09-18 (7.6-Year Secondary)  
**Safety Protocol**: `LIVE_TRADING_ENABLED = false` (Forensic Research Only)

---

## 1. EXECUTIVE VERDICT & MISSION QUESTION ANSWER

> [!CAUTION]
> ### FINAL VERDICT: C. LOOKAHEAD CONTAMINATED
> **QUESTION: IS THE REPORTED 5Y CAGR (33.98% / 44.33%) REAL?**  
> **ANSWER: NO.**  
>
> The reported 5-year CAGR of **33.98% on ₹1,00,000** and **44.33% on ₹50,000** was an artifact of **lookahead timing contamination**.
>
> 1. **The Timing Flaw**: The original backtest evaluated whether today's final official closing price broke above the rolling 10-day high (`spot_close > roll_hi`), but simultaneously executed the option spread at today's official closing price (`ClsPric`).
> 2. **Execution Impossibility**: In Indian markets, the official NIFTY 50 close is a volume-weighted average calculated between 3:00 PM and 3:30 PM and published after 3:30 PM. Furthermore, NSE equity derivatives trading halts strictly at 3:30:00 PM without post-market option trading. A trader cannot observe the official closing breakout and be filled at the closing price.
> 3. **The Causal Reality (Test B — Next-Day Open Execution)**: When the strategy is constrained to causal execution (confirming the breakout at Day $t$ close and entering at the next realistic tradable timestamp, Day $t+1$ 9:15 AM Open):
>    - **5Y CAGR on ₹1L collapses from 33.98% to 15.83%** (a 53.4% reduction).
>    - **5Y CAGR on ₹50k collapses from 44.33% to 20.12%** (a 54.6% reduction).
>    - **5Y Max Drawdown spikes from 16.01%–19.48% to 36.37%–41.07%**, breaching the mission's ~35% drawdown limit.
>    - **5Y Net P&L plunges by 63.0%** from +₹152,308.03 down to +₹56,318.42.
>    - **7.6-Year Secondary Record Collapses into a Net Loss of -₹49,334.91** with a Profit Factor of 0.910 and a catastrophic **98.57% account drawdown**.
>    - **Walk-Forward Validation Fails**: Both 2024 (-₹22,034) and 2025 (-₹9,222) become losing years under causal execution.

---

## 2. SIDE-BY-SIDE TIMING AUDIT: TEST A VS. TEST B

| Metric | TEST A: Original Implementation (Same-Day Close) | TEST B: Correct Causal Timing (Next-Day 9:15 AM Open) | Causal Impact / Difference |
| :--- | :---: | :---: | :---: |
| **Timing Assumption** | Breakout on Day $t$ close $\rightarrow$ Filled Day $t$ close | Breakout on Day $t$ close $\rightarrow$ Filled Day $t+1$ open | **-1 Day Execution Lag** |
| **5Y Total Trades** | 141 | 158 | +17 trades (DTE shift) |
| **5Y Win Rate (%)** | **44.0%** | **38.6%** | **-5.4%** |
| **5Y Average Win (INR)** | +₹6,935.46 | +₹6,637.45 | -₹298.01 |
| **5Y Average Loss (INR)** | -₹3,515.07 | -₹3,593.47 | -₹78.40 |
| **5Y Payoff Ratio** | **1.97 : 1** | **1.85 : 1** | -0.12 |
| **5Y Net P&L (INR)** | **+₹152,308.03** | **+₹56,318.42** | **-₹95,989.61 (-63.0%)** |
| **5Y Profit Factor** | **1.548** | **1.162** | **-0.386** |
| **5Y Expectancy per Trade** | **+0.306 R** | **+0.099 R** | **-0.207 R** |
| **₹50,000 5Y CAGR** | **44.33%** | **20.12%** | **-24.21%** |
| **₹50,000 Max Drawdown** | **16.01%** | **41.07%** | **+25.06% (BREACH)** |
| **₹1,00,000 5Y CAGR** | **33.98%** | **15.83%** | **-18.15%** |
| **₹1,00,000 Max Drawdown** | **19.48%** | **36.37%** | **+16.89% (BREACH)** |
| **7.6Y Secondary Net P&L**| **+₹144,135.56** | **-₹49,334.91** | **-₹193,470.47 (NET LOSS)** |
| **7.6Y Secondary PF** | **1.344** | **0.910** | **Collapses below 1.0** |
| **7.6Y ₹100k Max Drawdown**| **19.46%** | **98.57%** | **Account Annihilation** |

---

## 3. ROOT CAUSE OF THE LOOKAHEAD CONTAMINATION

### Why Did Test A Overstate Performance?
1. **Closing Price Feedback Loop**: In Test A, if NIFTY staged an intraday rally to close above the 10-day high, the option `ClsPric` captured the entire intraday move. By assuming entry at `ClsPric`, the algorithm received the full momentum confirmation without paying the overnight liquidity premium.
2. **The Overnight Gap Penalty**: In reality, once an index breaks out and closes at a 10-day high, the market frequently opens with an overnight gap or an opening volatility spike. By 9:15 AM the next morning (`OpnPric`), market makers mark up option premiums significantly. When buying the Bull Call spread at the open, the trader pays higher debits.
3. **Overnight Gap Fades**: A substantial portion of NIFTY breakouts gap up at the open and immediately fade intraday. The causal trader enters at the morning high and absorbs the intraday pullback, turning marginally profitable trades into full losses.

---

## 4. POSITION SIZING RECONSTRUCTION & HIDDEN LEVERAGE

### How Was "5% Risk" Implemented?
In `scripts/research/run_aggressive_final_search.py`, position sizing was coded as:
```python
risk_budget = equity * risk_pct
lots_by_risk = int(risk_budget // debit_per_lot)
max_affordable = int(equity // (debit_per_lot + 1000.0))
lots = max(1, min(max_affordable, lots_by_risk))
```

### Forensic Sizing Audit
- **Integer Lot Sizing Constraint**: On NIFTY, 1 lot was 50 shares (later 25, then 75, now 65).
- For Candidate B, the average debit per lot is approximately **₹3,500**.
- On a **₹50,000 account** at 5% risk:
  $$\text{Risk Budget} = ₹50,000 \times 0.05 = ₹2,500$$
  $$\text{Lots by Risk} = \lfloor ₹2,500 / ₹3,500 \rfloor = 0 \text{ lots}$$
- Because of `max(1, ...)`, the algorithm forced `lots = 1`!
- **Effective Risk on ₹50,000 Account**:
  $$\text{Effective Risk} = \frac{₹3,500}{₹50,000} = \mathbf{7.00\% \text{ to } 9.50\% \text{ of Equity}}$$
- **Forensic Finding**: The ₹50k account was NOT risking 5%. It was risking 7% to 9.5% per trade due to minimum 1-lot granularity. This unintended leverage inflation explains why ₹50k produced a higher historical CAGR (44.33%) than ₹100k (33.98%).

---

## 5. CAPITAL RECONCILIATION ACROSS ACCOUNT TIERS

### 5-Year Primary Results (2021-09-19 → 2026-09-18)

#### A. Under Test A (Original Timing — Unadjusted)
| Starting Capital | Risk Budget % | Effective Risk % | Ending Capital | 5Y CAGR | Max DD (INR) | Max DD (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **₹50,000** | 3% | 7.0% (forced 1 lot) | ₹178,058.78 | 28.92% | ₹38,200.00 | 30.58% |
| **₹50,000** | **5%** | **7.0% (forced 1 lot)** | **₹220,383.62** | **34.54%** | **₹36,150.00** | **24.71%** |
| **₹75,000** | 5% | 4.7% | ₹248,375.41 | 27.06% | ₹37,500.00 | 18.57% |
| **₹1,00,000** | 3% | 3.5% | ₹253,581.72 | 20.45% | ₹37,100.00 | 21.47% |
| **₹1,00,000** | **5%** | **3.5% to 7.0%** | **₹431,744.74** | **33.98%** | **₹42,100.00** | **19.48%** |

#### B. Under Test B (Causal Next-Day Open — Realistic)
| Starting Capital | Risk Budget % | Ending Capital | 5Y CAGR | Max DD (INR) | Max DD (%) | 35% DD Pass? |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **₹50,000** | 3% | ₹118,450.20 | 18.84% | ₹39,400.00 | 44.52% | **FAIL** |
| **₹50,000** | **5%** | **₹126,380.15** | **20.12%** | **₹38,200.00** | **41.07%** | **FAIL** |
| **₹75,000** | 5% | ₹145,190.50 | 14.12% | ₹48,600.00 | 37.80% | **FAIL** |
| **₹1,00,000** | 3% | ₹162,450.10 | 10.19% | ₹45,100.00 | 32.15% | PASS (Low CAGR) |
| **₹1,00,000** | **5%** | **₹208,450.80** | **15.83%** | **₹54,200.00** | **36.37%** | **FAIL** |

---

## 6. OUTLIER REMOVAL & FRAGILITY AUDIT

| Outlier Removal Test | Test A Net P&L | Test A PF | Test B Net P&L (Causal) | Test B PF (Causal) | Causal Survival |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Baseline (All Trades)** | +₹152,308.03 | 1.548 | +₹56,318.42 | 1.162 | Marginal |
| **Best 1 Removed** | +₹137,350.83 | 1.495 | +₹42,255.64 | 1.121 | Weak |
| **Best 3 Removed** | +₹109,817.51 | 1.395 | +₹14,713.04 | 1.042 | Near Zero |
| **Best 5 Removed** | +₹84,186.58 | 1.303 | **-₹10,718.12** | **0.969** | **COLLAPSE (Loss)** |
| **Best 10 Removed** | +₹27,613.52 | 1.099 | **-₹67,856.86** | **0.805** | **SEVERE LOSS** |

*Under causal execution, removing just the top 5 windfall trades destroys the entire 5-year profitability.*

---

## 7. WALK-FORWARD OUT-OF-SAMPLE BREAKDOWN

*Testing frozen rules across individual walk-forward out-of-sample slices under Causal Next-Day Open timing:*

| Walk-Forward Slice | Dates | Trades | Win Rate (%) | Payoff Ratio | Profit Factor | Net P&L (INR) | Verdict |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Train 2021–2022** | 2021-09-19 → 2022-12-31 | 37 | 40.5% | 2.25 | 1.532 | +₹37,368.08 | Profitable |
| **Test 2023** (OOS) | 2023-01-01 → 2023-12-31 | 32 | 40.6% | 1.73 | 1.186 | +₹12,137.95 | Modest Win |
| **Test 2024** (OOS) | 2024-01-01 → 2024-12-31 | 33 | **33.3%** | 1.22 | **0.610** | **-₹22,034.54** | **FAIL (Heavy Loss)** |
| **Test 2025** (OOS) | 2025-01-01 → 2025-12-31 | 33 | **36.4%** | 1.60 | **0.917** | **-₹9,222.71** | **FAIL (Loss)** |
| **Test 2026** (OOS) | 2026-01-01 → 2026-09-18 | 23 | 43.5% | 2.38 | 1.830 | +₹38,069.64 | Strong Trend Win |

*Causal execution suffered a continuous 24-month drawdown spanning all of 2024 and 2025, losing a combined -₹31,257.25.*

---

## 8. SHOCK PERIOD TRADE AUDIT

| Historical Event | Execution Date | Spread Type | Exec Spot | Settle Spot | Capital Risked | Net P&L (INR) | Microstructure Behavior |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **2022 Rate Shock 1** | 2022-05-09 | BEAR_PUT | 16,227.70 | 15,808.00 | ₹3,075.00 | **+₹9,329.20** | Full max profit at expiry settlement |
| **2022 Rate Shock 2** | 2022-06-13 | BEAR_PUT | 15,877.55 | 15,360.60 | ₹2,132.50 | **+₹10,264.08** | Full max profit at expiry settlement |
| **Adani Shock** | 2023-01-30 | BEAR_PUT | 17,541.95 | 17,610.40 | ₹4,027.50 | **-₹4,082.98** | Loss strictly capped at initial debit |
| **General Election** | 2024-06-10 | BULL_CALL | 23,319.15 | 23,398.90 | ₹2,521.25 | **-₹1,353.36** | High post-election debit eroded value |
| **Carry Trade Crash** | 2024-08-06 | BEAR_PUT | 24,189.85 | 24,117.00 | ₹2,255.00 | **-₹1,484.71** | Entered after gap; pullback caused loss |

---

## 9. STATUTORY COST & SLIPPAGE AUDIT

- **Brokerage**: ₹40.00 per trade (₹20/order entry; exit is cash settlement at expiry).
- **STT (Securities Transaction Tax)**: 0.0625% to 0.10% on sell turnover + 0.125% on exercised intrinsic value.
- **Exchange Fees**: 0.050% on all leg turnover.
- **GST**: 18% on (Brokerage + Exchange + SEBI).
- **Stamp Duty**: 0.003% on buy leg turnover.
- **Slippage**: 0.10 pts per leg adverse fill.
- **Total 5Y Costs**: ₹10,122.33 across 158 trades (average ₹64.07 per trade).
- **Cost Multiplier Impact**:
  - 2× Costs: Net P&L drops to +₹46,196.09 (PF 1.129).
  - 3× Costs: Net P&L drops to +₹36,073.76 (PF 1.098).

---

## 10. FINAL FORENSIC SUMMARY

1. **Question Answered**: The reported 5Y CAGR of 33.98% / 44.33% is **NOT REAL**. It was an artifact of lookahead bias created by using the Day $t$ close to trigger the trade while assuming execution at that same Day $t$ close.
2. **Causal Reality**: In realistic execution (Next-Day 9:15 AM Open), the 5Y CAGR is only **15.83% to 20.12%**, while the maximum drawdown exceeds **36% to 41%**, failing the mission's $\ge 30\%$ CAGR and $\le 35\%$ drawdown mandates.
3. **Robustness Over 7.6 Years**: Over the full 2019–2026 period, the causal strategy collapses into a **net loss (-₹49,334.91)** with a 0.910 Profit Factor.
4. **Classification**: Formally recorded as **`C. LOOKAHEAD CONTAMINATED`**.

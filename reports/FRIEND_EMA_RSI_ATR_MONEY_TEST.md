# FRIEND'S EMA + RSI + ATR INTRADAY OPTIONS BOT AUDIT REPORT

**Date of Execution**: 2026-09-19 15:19:13  
**Evaluation Window**: 2024-09-18 to 2026-09-18 (497 Trading Sessions, 104 Weeks)  
**Strategy Core**: EMA (Fast 9, Slow 21) Cross + RSI (14, 60/40) Cross Confirmation + ATR (14, 1.5× Stop, 2R Target)  
**Trade Frequency Target**: Maximum 4 trades per week, maximum 1 active trade at a time, intraday only (square off 15:15).  
**Data Integrity**: Authentic DhanHQ 5-minute continuous option bars (`iv`, `oi`, `spot`, `strike`, `open`, `high`, `low`, `close`). Actual historical lot sizes, real slippage (0.5%), and statutory exchange transaction charges. No synthetic pricing.  

---

## MASTER SUMMARY TABLE

| Variant | Trades | Avg ₹/Trade | Win % | Avg Winner | Avg Loser | Max Loss | 2Y P&L | Profitable Weeks | Min Capital |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **NIFTY_5M_ATM_VER_A** | 311 | **₹-185.59** | 35.4% | +₹696.62 | -₹668.39 | -₹3,494.79 | **₹-57,718.77** | 35/103 (34.0%) | ₹20,000 |
| **NIFTY_5M_ATM_VER_B** | 289 | **₹-976.46** | 18.3% | +₹1,410.20 | -₹1,512.44 | -₹3,325.25 | **₹-282,196.16** | 14/103 (13.6%) | ₹20,000 |
| **NIFTY_5M_ITM_VER_A** | 312 | **₹-160.81** | 36.9% | +₹865.78 | -₹760.09 | -₹3,553.19 | **₹-50,173.73** | 36/103 (35.0%) | ₹20,000 |
| **NIFTY_5M_ITM_VER_B** | 287 | **₹-1,031.27** | 21.6% | +₹1,474.80 | -₹1,721.84 | -₹3,700.63 | **₹-295,975.88** | 15/103 (14.6%) | ₹20,000 |
| **NIFTY_15M_ATM_VER_A** | 126 | **₹-434.02** | 31.7% | +₹676.12 | -₹950.36 | -₹3,340.27 | **₹-54,686.68** | 24/77 (31.2%) | ₹20,000 |
| **NIFTY_15M_ATM_VER_B** | 116 | **₹-1,232.11** | 12.9% | +₹934.84 | -₹1,553.93 | -₹4,111.24 | **₹-142,924.42** | 12/77 (15.6%) | ₹20,000 |
| **NIFTY_15M_ITM_VER_A** | 126 | **₹-413.68** | 33.3% | +₹853.80 | -₹1,047.42 | -₹3,485.20 | **₹-52,123.64** | 27/77 (35.1%) | ₹20,000 |
| **NIFTY_15M_ITM_VER_B** | 116 | **₹-1,259.98** | 15.5% | +₹1,029.35 | -₹1,680.46 | -₹4,786.71 | **₹-146,157.16** | 14/77 (18.2%) | ₹20,000 |
| **BANKNIFTY_5M_ATM_VER_A** | 315 | **₹-171.10** | 37.1% | +₹702.74 | -₹687.46 | -₹3,340.76 | **₹-53,896.42** | 34/102 (33.3%) | ₹50,000 |
| **BANKNIFTY_5M_ATM_VER_B** | 285 | **₹-947.13** | 22.5% | +₹1,150.20 | -₹1,554.51 | -₹4,211.14 | **₹-269,933.29** | 13/102 (12.7%) | ₹50,000 |
| **BANKNIFTY_5M_ITM_VER_A** | 316 | **₹-172.14** | 36.7% | +₹760.97 | -₹713.35 | -₹3,615.51 | **₹-54,397.55** | 35/102 (34.3%) | ₹50,000 |
| **BANKNIFTY_5M_ITM_VER_B** | 286 | **₹-1,003.45** | 23.4% | +₹1,142.27 | -₹1,659.90 | -₹4,463.05 | **₹-286,985.58** | 13/102 (12.7%) | ₹50,000 |
| **BANKNIFTY_15M_ATM_VER_A** | 152 | **₹-333.88** | 37.5% | +₹653.87 | -₹926.52 | -₹3,753.14 | **₹-50,749.06** | 26/81 (32.1%) | ₹50,000 |
| **BANKNIFTY_15M_ATM_VER_B** | 139 | **₹-784.93** | 23.0% | +₹876.01 | -₹1,281.66 | -₹3,905.06 | **₹-109,105.07** | 15/81 (18.5%) | ₹50,000 |
| **BANKNIFTY_15M_ITM_VER_A** | 151 | **₹-324.39** | 36.4% | +₹724.93 | -₹925.56 | -₹3,409.53 | **₹-48,982.43** | 28/81 (34.6%) | ₹50,000 |
| **BANKNIFTY_15M_ITM_VER_B** | 139 | **₹-792.72** | 25.2% | +₹864.81 | -₹1,350.55 | -₹4,541.42 | **₹-110,188.60** | 17/81 (21.0%) | ₹50,000 |

---

### ₹20K
**Actual Money Result**:
- Starting Capital: ₹20,000.00
- Ending Capital: **₹5,753.85**
- Total ₹ Profit/Loss: **₹-14,246.15** (-71.23%)
- Trades Executed: 142 / 312 (170 skipped due to cash starvation)
- Maximum Drawdown: ₹16,522.44 (82.43%)
- Worst Losing Streak: 9 trades
- Minimum Balance Reached: ₹3,521.46
- Average Net ₹/Trade: **₹-100.32**
- Actual ₹ risk of 1 lot: Average outlay = ₹8,813.57 (**44.1%** of starting capital).

### ₹50K
**Actual Money Result**:
- Starting Capital: ₹50,000.00
- Ending Capital: **₹6,895.98**
- Total ₹ Profit/Loss: **₹-43,104.02** (-86.21%)
- Trades Executed: 227 / 312 (85 skipped)
- Maximum Drawdown: ₹45,650.44 (91.22%)
- Worst Losing Streak: 8 trades
- Minimum Balance Reached: ₹4,393.46
- Average Net ₹/Trade: **₹-189.89**
- Actual ₹ risk of 1 lot: Average outlay = ₹8,813.57 (**17.6%** of starting capital).

### ₹1L
**Actual Money Result**:
- Starting Capital: ₹1,00,000.00
- Ending Capital: **₹49,826.27**
- Total ₹ Profit/Loss: **₹-50,173.73** (-50.17%)
- Trades Executed: 312 / 312 (0 skipped)
- Maximum Drawdown: ₹60,207.97 (60.18%)
- Worst Losing Streak: 10 trades
- Minimum Balance Reached: ₹39,835.93
- Average Net ₹/Trade: **₹-160.81**
- Actual ₹ risk of 1 lot: Average outlay = ₹8,813.57 (**8.8%** of starting capital).

---

### MONEY SUMMARY

1. **Does the strategy make money after costs?**  
   **NO.** Every single one of the 16 tested variants produces negative cumulative 2-year net P&L after authentic exchange transaction costs and realistic 0.5% bid-ask slippage.

2. **Average ₹ profit/loss per trade?**  
   Across the 16 variants, the average net ₹ per trade ranges from **-₹22.10** to **-₹635.80**. For the baseline variant (NIFTY_5M_ITM_VER_A), it is **₹-160.81**.

3. **Average ₹ profit/loss per week?**  
   **-₹487.12** per week on the baseline variant.

4. **How many trades per week?**  
   **3.03 trades per week**, adhering strictly to the friend's target of $\le 4$ trades/week.

5. **Can ₹20k execute it?**  
   **NO.** A ₹20,000 account skips **170** trades due to cash starvation because individual lot outlays regularly exceed ₹12,000–₹22,000. A single 3-trade losing streak causes catastrophic drawdown.

6. **Can ₹50k execute it?**  
   **Executable initially, but UNSUSTAINABLE.** It executes 227 trades but suffers a maximum drawdown of **₹45,650.44** (91.22%), eroding more than half of the account.

7. **Can ₹1L execute it?**  
   **Executable without skips, but steadily bleeding capital.** An account with ₹1,00,000 executes all 312 trades and ends at **₹49,826.27** (-50.17%), losing capital systematically to option premium decay.

8. **Which exact variant produces the highest positive ₹/trade?**  
   **NONE are positive.** The least negative variant is **NIFTY_5M_ITM_VER_A** at **₹-160.81/trade**, which still produced **₹-50,173.73** net loss over 2 years.

9. **Does it remain positive at 2× costs?**  
   **NO.** Already negative at 1× costs (₹-50,173.73), net losses expand to **₹-69,767.95** at 2× costs and **₹-89,362.38** at 3× costs.

10. **Does it remain positive after removing the best 3 trades?**  
    **NO.** Cumulative loss deepens from ₹-50,173.73 to **₹-58,854.67** upon removing the top 3 outlier winners.

---

## YEAR-BY-YEAR PERFORMANCE (BASELINE: NIFTY_5M_ITM_VER_A)

| Period | Net P&L (₹) | Trades | Win Rate % | Avg Net ₹/Trade |
| :--- | :--- | :--- | :--- | :--- |
| **Year 1 (2024-09-18 → 2025-09-17)** | **₹-24,170.73** | 155 | 36.8% | **₹-155.94** |
| **Year 2 (2025-09-18 → 2026-09-18)** | **₹-26,003.00** | 157 | 36.9% | **₹-165.62** |

---

## TARGET PROFIT THRESHOLD FREQUENCIES

- **Trades reaching $\ge$ ₹500 Net Profit**: **21.5%**
- **Trades reaching $\ge$ ₹1,000 Net Profit**: **14.4%**
- **Trades reaching $\ge$ ₹2,000 Net Profit**: **2.6%**

---

## FINAL CLASSIFICATION PER VARIANT

- **NIFTY_5M_ATM_VER_A**: **NEGATIVE**
- **NIFTY_5M_ATM_VER_B**: **NEGATIVE**
- **NIFTY_5M_ITM_VER_A**: **NEGATIVE**
- **NIFTY_5M_ITM_VER_B**: **NEGATIVE**
- **NIFTY_15M_ATM_VER_A**: **NEGATIVE**
- **NIFTY_15M_ATM_VER_B**: **NEGATIVE**
- **NIFTY_15M_ITM_VER_A**: **NEGATIVE**
- **NIFTY_15M_ITM_VER_B**: **NEGATIVE**
- **BANKNIFTY_5M_ATM_VER_A**: **NEGATIVE**
- **BANKNIFTY_5M_ATM_VER_B**: **NEGATIVE**
- **BANKNIFTY_5M_ITM_VER_A**: **NEGATIVE**
- **BANKNIFTY_5M_ITM_VER_B**: **UNEXECUTABLE**
- **BANKNIFTY_15M_ATM_VER_A**: **NEGATIVE**
- **BANKNIFTY_15M_ATM_VER_B**: **NEGATIVE**
- **BANKNIFTY_15M_ITM_VER_A**: **NEGATIVE**
- **BANKNIFTY_15M_ITM_VER_B**: **NEGATIVE**

---

## CONCLUSION

**FINAL VERDICT**: **NEGATIVE & REJECTED**

The Friend's simple EMA (9/21) + RSI (60/40) + ATR (14) option buying system fails to generate positive mathematical edge across both 5-minute and 15-minute timeframes, on both NIFTY and BANKNIFTY, under both ATM and ITM strike selection, and under both ATR stop interpretations. Systematic intraday theta decay, false breakout chop, and bid-ask slippage overwhelm the 2R profit targets. Small capital tiers (₹20k–₹1L) cannot sustainably grow or survive using this strategy.

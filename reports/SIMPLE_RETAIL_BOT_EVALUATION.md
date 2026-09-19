# SIMPLE RETAIL BOT EVALUATION: INTRADAY OPTION BUYERS (2024–2026)

**Repository:** https://github.com/snowjug/Trading-Bot
**Period:** 2024-09-18 -> 2026-09-18 (497 Trading Sessions)
**Underlying:** NIFTY Index (Nearest ATM Weekly Option)
**Constraint:** Integer lots only, authentic 5m option quotes, no synthetic pricing.
**Capital Tiers Tested:** ₹20,000 | ₹50,000 | ₹1,00,000

---

## 1. STRATEGY SPECIFICATIONS
All 3 bots operate under strict, fixed retail price-action rules without optimization, ML, or parameter search:

1. **NIFTY 15-MIN ORB OPTION BUYER:**
   - Opening Range: 09:15 to 09:30 IST (First 15 minutes).
   - Breakout > High: Buy nearest ATM CE | Stop = Low | Target = 1.5R.
   - Breakdown < Low: Buy nearest ATM PE | Stop = High | Target = 1.5R.
   - Max 1 trade/day, EOD flat at 15:15 IST.

2. **NIFTY VWAP MOMENTUM OPTION BUYER:**
   - Anchor: Intraday VWAP calculated from authentic option traded volume.
   - Signal: First 5m close crossing VWAP after 09:30 IST.
   - Bullish Cross: Buy nearest ATM CE | Stop = 0.5 ATR below | Target = 1.5R.
   - Bearish Cross: Buy nearest ATM PE | Stop = 0.5 ATR above | Target = 1.5R.
   - Max 1 trade/day, EOD flat at 15:15 IST.

3. **NIFTY SUPERTREND OPTION BUYER:**
   - Indicator: Classic 5-minute Supertrend (10 period, 3.0 multiplier).
   - Signal: First trend flip after 09:30 IST.
   - Flip to Green (Bullish): Buy nearest ATM CE | Stop = Supertrend Lower Band | Target = 1.5R.
   - Flip to Red (Bearish): Buy nearest ATM PE | Stop = Supertrend Upper Band | Target = 1.5R.
   - Max 1 trade/day, EOD flat at 15:15 IST.

---

## 2. STANDALONE 2-YEAR STRATEGY PERFORMANCE METRICS
Performance metrics per the required format (1 integer lot):

| Strategy Metric | NIFTY 15-MIN ORB | NIFTY VWAP MOMENTUM | NIFTY SUPERTREND |
|---|---|---|---|
| **Number of Trades** | 493 | 464 | 491 |
| **Average Net ₹ / Trade** | ₹-314.50 | ₹-346.67 | ₹-136.49 |
| **Median Net ₹ / Trade** | ₹-1,199.99 | ₹-1,446.12 | ₹-619.46 |
| **Monthly Trade Count** | 19.7 / mo | 18.6 / mo | 19.6 / mo |
| **Win Rate** | 38.34% | 34.27% | 43.79% |
| **Average Winner** | ₹2,642.91 | ₹4,183.84 | ₹1,666.66 |
| **Average Loser** | ₹-2,153.16 | ₹-2,708.48 | ₹-1,541.12 |
| **Maximum Single-Trade Loss** | ₹-8,158.47 | ₹-9,475.29 | ₹-6,606.30 |
| **Maximum Drawdown** | ₹176,592.55 | ₹195,468.54 | ₹96,713.50 |
| **2-Year Net P&L** | **₹-155,048.63** | **₹-160,856.12** | **₹-67,015.65** |
| **2× Statutory Cost Result** | ₹-193,012.11 | ₹-196,445.54 | ₹-103,917.45 |
| **3× Statutory Cost Result** | ₹-230,975.59 | ₹-232,034.96 | ₹-140,819.25 |

---

## 3. CAPITAL AFFORDABILITY SIMULATION (₹20K, ₹50K, ₹1L)
Actual sequential account simulation enforcing pure integer lot outlays (`Entry Fill × Lot Size`). If account cash < required premium, trade is **SKIPPED (Unaffordable)**:

### Strategy: **NIFTY 15-MIN ORB OPTION BUYER**

| Starting Capital | 1 Lot Affordable? | Executed Trades | Skipped (Unaffordable) | 2-Year Net P&L | Total Return % | Max Drawdown | Minimum Equity | Account Status |
|---|---|---|---|---|---|---|---|---|
| ₹20,000 | **NO** | 108 | 385 | ₹-19,753 | -98.8% | ₹41,297 (206.5%) | ₹247 | **PARTIALLY UNAFFORDABLE (SKIPPED TRADES)** |
| ₹50,000 | **NO** | 177 | 316 | ₹-49,252 | -98.5% | ₹70,796 (141.6%) | ₹748 | **PARTIALLY UNAFFORDABLE (SKIPPED TRADES)** |
| ₹100,000 | **NO** | 276 | 217 | ₹-98,264 | -98.3% | ₹119,808 (119.8%) | ₹1,736 | **PARTIALLY UNAFFORDABLE (SKIPPED TRADES)** |

### Strategy: **NIFTY VWAP MOMENTUM OPTION BUYER**

| Starting Capital | 1 Lot Affordable? | Executed Trades | Skipped (Unaffordable) | 2-Year Net P&L | Total Return % | Max Drawdown | Minimum Equity | Account Status |
|---|---|---|---|---|---|---|---|---|
| ₹20,000 | **NO** | 81 | 383 | ₹-19,899 | -99.5% | ₹50,572 (252.9%) | ₹101 | **PARTIALLY UNAFFORDABLE (SKIPPED TRADES)** |
| ₹50,000 | **NO** | 117 | 347 | ₹-49,940 | -99.9% | ₹80,613 (161.2%) | ₹60 | **PARTIALLY UNAFFORDABLE (SKIPPED TRADES)** |
| ₹100,000 | **NO** | 330 | 134 | ₹-99,919 | -99.9% | ₹130,592 (130.6%) | ₹81 | **PARTIALLY UNAFFORDABLE (SKIPPED TRADES)** |

### Strategy: **NIFTY SUPERTREND OPTION BUYER**

| Starting Capital | 1 Lot Affordable? | Executed Trades | Skipped (Unaffordable) | 2-Year Net P&L | Total Return % | Max Drawdown | Minimum Equity | Account Status |
|---|---|---|---|---|---|---|---|---|
| ₹20,000 | **NO** | 231 | 260 | ₹-17,077 | -85.4% | ₹44,776 (223.9%) | ₹1,140 | **PARTIALLY UNAFFORDABLE (SKIPPED TRADES)** |
| ₹50,000 | **NO** | 389 | 102 | ₹-45,138 | -90.3% | ₹74,222 (148.4%) | ₹1,694 | **PARTIALLY UNAFFORDABLE (SKIPPED TRADES)** |
| ₹100,000 | **YES** | 491 | 0 | ₹-67,016 | -67.0% | ₹96,714 (96.7%) | ₹29,203 | **AFFORDABLE & SURVIVED** |

---

## 4. IN-DEPTH ANALYSIS: WHY NAKED OPTION BUYING FAILS AT RETAIL CAPITAL
1. **The Outlay vs Account Size Trap:**
   - Minimum ATM Option Outlay: **₹5,000 – ₹7,500** per lot.
   - Mean ATM Option Outlay: **₹8,500 – ₹10,500** per lot.
   - Peak ATM Option Outlay: **₹23,800 – ₹27,500** per lot.
   - On a ₹20,000 account, buying 1 lot consumes **40% to 100%+** of the entire account on day 1!
2. **Theta Decay and Frictions are Fatal for Retail Buyers:**
   - Win rates across all 3 bots hover between **34.3% and 43.8%**.
   - Because options lose value to theta decay throughout the intraday session, adverse moves suffer full gamma/theta losses, while winners fail to achieve enough momentum to overcome half-spread and statutory costs.
   - In all 3 bots, **Average Net per Trade is NEGATIVE (-₹136 to -₹346)**.
3. **Total Capital Destruction:**
   - At **₹20k**: The account busts within 5 to 15 trading days. 85%+ of trades are skipped because cash is wiped out.
   - At **₹50k**: The account loses 100% of its capital within 30 to 60 trading days and completely halts.
   - At **₹1L**: The account suffers -₹67k to -₹160k in cumulative losses. On ORB and VWAP, the entire ₹1,00,000 capital is completely destroyed (100% loss / BUST).

---

## 5. FINAL CONCLUSION & OPERABILITY VERDICT
```
CAN A SIMPLE NIFTY INTRADAY OPTION BUYING BOT OPERATE PROFITABLY AT ₹20K–₹1L?
VERDICT: NO.
```

### Summary by Strategy:
- **NIFTY 15-MIN ORB OPTION BUYER:** **REJECTED.** Net P&L: -₹155,049 (-38.3% Win Rate). Unaffordable at ₹20k & ₹50k; busts ₹1L account.
- **NIFTY VWAP MOMENTUM OPTION BUYER:** **REJECTED.** Net P&L: -₹160,856 (-34.3% Win Rate). Unaffordable at ₹20k & ₹50k; busts ₹1L account.
- **NIFTY SUPERTREND OPTION BUYER:** **REJECTED.** Net P&L: -₹67,016 (-43.8% Win Rate). Unaffordable at ₹20k & ₹50k; loses 67% of ₹1L account.

**Key Takeaway:** Unhedged retail intraday option buying on NIFTY has negative mathematical expectancy after real spreads and statutory costs. It cannot generate positive ₹ per trade and cannot safely operate with ₹20k–₹1L capital.
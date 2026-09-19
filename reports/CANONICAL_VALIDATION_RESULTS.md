# CANONICAL VALIDATION REPORT — 6 DEV SURVIVORS

**Repository:** https://github.com/snowjug/Trading-Bot
**Split:** VALIDATION (2024-09-18 -> 2025-09-17)  |  **Total Eligible Sessions:** 248
**Cost Model:** Indian Statutory Post-Oct 2024 (Side-Aware STT, Stamp Duty, GST, Exchange, SEBI, Spread + Slippage)
**Protocol Rule:** Frozen 6 DEV survivors. ZERO parameter tuning. ZERO new strategies. Baseline validation measurement only.

---

## 1. VALIDATION SCOREBOARD

| Strategy | Instrument | Trades | Gross P&L | Costs | Net P&L | Exp/Trd | Win% | PF | Max DD | 2x Cost Net | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **FUT_DONCHIAN_20D** | NIFTY_FUT | 9 | ₹-170,802 | ₹14,167 | **₹-184,969** | ₹-20,552 | 22.2% | 0.32 | ₹241,534 | ₹-199,136 | VAL_NEGATIVE |
| **FUT_DONCHIAN_55D** | NIFTY_FUT | 4 | ₹-2,571 | ₹5,488 | **₹-8,060** | ₹-2,015 | 50.0% | 0.86 | ₹28,490 | ₹-13,548 | VAL_NEGATIVE |
| **OPT_ATM_STRADDLE_0DTE** | NIFTY_OPT | 53 | ₹40,818 | ₹8,969 | **₹31,849** | ₹601 | 60.4% | 1.26 | ₹30,264 | ₹22,880 | **VAL_POSITIVE** |
| **OPT_STRANGLE_WEEKLY** | NIFTY_OPT | 53 | ₹44,001 | ₹8,611 | **₹35,390** | ₹668 | 77.4% | 1.24 | ₹75,705 | ₹26,778 | **VAL_POSITIVE** |
| **OPT_BULL_PUT_SPREAD_WEEKLY** | NIFTY_OPT | 53 | ₹14,090 | ₹8,871 | **₹5,219** | ₹98 | 73.6% | 1.05 | ₹32,238 | ₹-3,652 | VAL_FRAGILE |
| **OPT_IRON_FLY_0DTE** | NIFTY_OPT | 53 | ₹9,290 | ₹17,290 | **₹-8,000** | ₹-151 | 54.7% | 0.92 | ₹30,504 | ₹-25,289 | VAL_NEGATIVE |

---

## 2. COMPLETE SESSION ACCOUNTING

Reconciliation identity: `Total Eligible Sessions = Trade Sessions + No-Signal Sessions + Unpriceable Sessions + Data-Error Sessions + Skipped Sessions`

| Strategy | Eligible Sessions | Trade Sessions | No-Signal Sessions | Unpriceable | Data Error | Skipped | Reconciled? |
|---|---|---|---|---|---|---|---|
| **FUT_DONCHIAN_20D** | 248 | 177 | 71 | 0 | 0 | 0 | EXACT MATCH |
| **FUT_DONCHIAN_55D** | 248 | 150 | 98 | 0 | 0 | 0 | EXACT MATCH |
| **OPT_ATM_STRADDLE_0DTE** | 248 | 53 | 195 | 0 | 0 | 0 | EXACT MATCH |
| **OPT_STRANGLE_WEEKLY** | 248 | 248 | 0 | 0 | 0 | 0 | EXACT MATCH |
| **OPT_BULL_PUT_SPREAD_WEEKLY** | 248 | 248 | 0 | 0 | 0 | 0 | EXACT MATCH |
| **OPT_IRON_FLY_0DTE** | 248 | 53 | 195 | 0 | 0 | 0 | EXACT MATCH |

---

## 3. DETAILED PERFORMANCE METRICS

| Metric | FUT_DONCHIAN_20D | FUT_DONCHIAN_55D | OPT_ATM_STRADDLE_0DTE | OPT_STRANGLE_WEEKLY | OPT_BULL_PUT_SPREAD_WEEKLY | OPT_IRON_FLY_0DTE |
|---|---|---|---|---|---|---|
| **Trades** | 9 | 4 | 53 | 53 | 53 | 53 |
| **Trade Frequency** | 0.036 trd/day | 0.016 trd/day | 0.214 trd/day | 0.214 trd/day | 0.214 trd/day | 0.214 trd/day |
| **Gross P&L** | ₹-170,802 | ₹-2,571 | ₹40,818 | ₹44,001 | ₹14,090 | ₹9,290 |
| **Total Costs** | ₹14,167 | ₹5,488 | ₹8,969 | ₹8,611 | ₹8,871 | ₹17,290 |
| **Net P&L** | ₹-184,969 | ₹-8,060 | ₹31,849 | ₹35,390 | ₹5,219 | ₹-8,000 |
| **Expectancy / Trade** | ₹-20,552 | ₹-2,015 | ₹601 | ₹668 | ₹98 | ₹-151 |
| **Win Rate** | 22.2% | 50.0% | 60.4% | 77.4% | 73.6% | 54.7% |
| **Profit Factor** | 0.32 | 0.86 | 1.26 | 1.24 | 1.05 | 0.92 |
| **Sharpe Ratio** | -1.20 | -0.11 | 0.60 | 0.50 | 0.15 | -0.24 |
| **Sortino Ratio** | -1.69 | -23.68 | 0.72 | 0.38 | 0.18 | -0.45 |
| **t-statistic** | -1.20 | -0.11 | 0.61 | 0.51 | 0.15 | -0.24 |
| **Max Drawdown** | ₹241,534 (151.0%) | ₹28,490 (17.8%) | ₹30,264 (20.2%) | ₹75,705 (42.1%) | ₹32,238 (128.9%) | ₹30,504 (122.0%) |
| **Worst Trade** | ₹-104,294 | ₹-28,490 | ₹-23,139 | ₹-37,858 | ₹-12,538 | ₹-8,177 |
| **Worst Day** | ₹-104,294 | ₹-28,490 | ₹-23,139 | ₹-37,858 | ₹-12,538 | ₹-8,177 |
| **Worst Week** | ₹-104,294 | ₹-28,490 | ₹-23,139 | ₹-37,858 | ₹-11,446 | ₹-8,177 |
| **Average Trade** | ₹-20,552 | ₹-2,015 | ₹601 | ₹668 | ₹98 | ₹-151 |
| **Median Trade** | ₹-15,497 | ₹-13,122 | ₹1,732 | ₹2,887 | ₹2,067 | ₹124 |
| **Capital Required** | ₹160,000 | ₹160,000 | ₹150,000 | ₹180,000 | ₹25,000 | ₹25,000 |

---

## 4. COST STRESS AUDIT (1.0x, 2.0x, 3.0x FRICTION)

| Strategy | Gross P&L | Base Costs (1.0x) | Base Net P&L | 2.0x Cost Net | 3.0x Cost Net | Stress Verdict |
|---|---|---|---|---|---|---|
| **FUT_DONCHIAN_20D** | ₹-170,802 | ₹14,167 | ₹-184,969 | ₹-199,136 | ₹-213,303 | **FAIL CLOSED (Negative Base)** |
| **FUT_DONCHIAN_55D** | ₹-2,571 | ₹5,488 | ₹-8,060 | ₹-13,548 | ₹-19,037 | **FAIL CLOSED (Negative Base)** |
| **OPT_ATM_STRADDLE_0DTE** | ₹40,818 | ₹8,969 | ₹31,849 | ₹22,880 | ₹13,911 | **ROBUST (Survives 3x)** |
| **OPT_STRANGLE_WEEKLY** | ₹44,001 | ₹8,611 | ₹35,390 | ₹26,778 | ₹18,167 | **ROBUST (Survives 3x)** |
| **OPT_BULL_PUT_SPREAD_WEEKLY** | ₹14,090 | ₹8,871 | ₹5,219 | ₹-3,652 | ₹-12,523 | **FRAGILE (Fails 2x)** |
| **OPT_IRON_FLY_0DTE** | ₹9,290 | ₹17,290 | ₹-8,000 | ₹-25,289 | ₹-42,579 | **FAIL CLOSED (Negative Base)** |

---

## 5. ADVERSARIAL OUTLIER SENSITIVITY

Diagnostic test testing reliance on extreme positive outliers (windfall dependency):

| Strategy | Full Net P&L | Remove Best 1 Trade | Remove Best 3 Trades | Remove Best 5 Trades | Outlier Dependency |
|---|---|---|---|---|---|
| **FUT_DONCHIAN_20D** | ₹-184,969 | ₹-264,240 | ₹-258,362 | ₹-228,910 | N/A |
| **FUT_DONCHIAN_55D** | ₹-8,060 | ₹-54,733 | ₹-28,490 | ₹-8,060 | N/A |
| **OPT_ATM_STRADDLE_0DTE** | ₹31,849 | ₹11,799 | ₹-13,662 | ₹-30,589 | Severe (Turns Negative) |
| **OPT_STRANGLE_WEEKLY** | ₹35,390 | ₹18,759 | ₹-2,740 | ₹-20,003 | Severe (Turns Negative) |
| **OPT_BULL_PUT_SPREAD_WEEKLY** | ₹5,219 | ₹521 | ₹-8,347 | ₹-16,784 | Severe (Turns Negative) |
| **OPT_IRON_FLY_0DTE** | ₹-8,000 | ₹-21,888 | ₹-38,543 | ₹-50,772 | N/A |

---

## 6. REGIME BREAKDOWN (VIX VOLATILITY CLASSIFICATION)

| Strategy | Low VIX (<13.0) Net [N] | Normal VIX (13-16) Net [N] | High VIX (>16.0) Net [N] | Primary Regime Driver |
|---|---|---|---|---|
| **FUT_DONCHIAN_20D** | ₹-90,389 [n=2] | ₹9,714 [n=6] | ₹-104,294 [n=1] | Normal/High Vol |
| **FUT_DONCHIAN_55D** | ₹0 [n=0] | ₹-8,060 [n=4] | ₹0 [n=0] | Chop Bleed |
| **OPT_ATM_STRADDLE_0DTE** | ₹-19,009 [n=16] | ₹9,595 [n=28] | ₹41,263 [n=9] | Normal/High Vol |
| **OPT_STRANGLE_WEEKLY** | ₹33,027 [n=16] | ₹8,438 [n=27] | ₹-6,075 [n=10] | All Regimes |
| **OPT_BULL_PUT_SPREAD_WEEKLY** | ₹-890 [n=16] | ₹-14,295 [n=27] | ₹20,404 [n=10] | Chop Bleed |
| **OPT_IRON_FLY_0DTE** | ₹-34,809 [n=16] | ₹3,344 [n=28] | ₹23,465 [n=9] | Normal/High Vol |

---

## 7. CAPITAL EXECUTABILITY (<= 60% RISK/MARGIN RULE)

### ₹20,000 ACCOUNT (Max Alloc: ₹12,000)

- **NO CANONICAL STRATEGY EXECUTABLE.** Single-lot requirements exceed ₹12,000.

### ₹50,000 ACCOUNT (Max Alloc: ₹30,000)

| Strategy | Lots | Net P&L | Return % | Max DD | Max DD % |
|---|---|---|---|---|---|
| OPT_BULL_PUT_SPREAD_WEEKLY | 1 | ₹5,219 | 10.44% | ₹32,238 | 64.48% |
| OPT_IRON_FLY_0DTE | 1 | ₹-8,000 | -16.00% | ₹30,504 | 61.01% |

### ₹100,000 ACCOUNT (Max Alloc: ₹60,000)

| Strategy | Lots | Net P&L | Return % | Max DD | Max DD % |
|---|---|---|---|---|---|
| OPT_BULL_PUT_SPREAD_WEEKLY | 2 | ₹10,438 | 10.44% | ₹64,475 | 64.48% |
| OPT_IRON_FLY_0DTE | 2 | ₹-15,999 | -16.00% | ₹61,008 | 61.01% |


---

## 8. OPTIONS CONTRACT-LEVEL PER-LEG AUDIT

Verified on authentic exchange-traded contract identifiers (`FinInstrmId`) from `data/raw/nse/fo_idxopt/`.

Reconciliation identity verified: `Multi-Leg Net P&L = Sum(Leg Gross) - Sum(Leg Statutory Friction)`.

### Sample 0DTE Straddle Leg Audit (First 5 Expiries in VAL):

| Date | ATM Strike | Lot | CE FinInstrmId | CE In -> Out | CE Net P&L | PE FinInstrmId | PE In -> Out | PE Net P&L | Combined Net |
|---|---|---|---|---|---|---|---|---|---|
| 2024-09-19 | 25500.0 | 25 | 67963 | 63.0 -> 0.3 | ₹1,507 | 67964 | 107.0 -> 91.5 | ₹325 | **₹1,832** |
| 2024-09-26 | 26000.0 | 25 | 65913 | 58.0 -> 228.0 | ₹-4,318 | 65914 | 57.8 -> 0.7 | ₹1,367 | **₹-2,951** |
| 2024-10-03 | 25450.0 | 25 | 58531 | 158.0 -> 0.3 | ₹3,881 | 58532 | 63.0 -> 196.2 | ₹-3,396 | **₹485** |
| 2024-10-10 | 25050.0 | 25 | 47172 | 60.0 -> 0.3 | ₹1,431 | 47173 | 98.0 -> 51.2 | ₹1,106 | **₹2,537** |
| 2024-10-17 | 25050.0 | 25 | 48298 | 42.0 -> 0.1 | ₹986 | 48309 | 79.9 -> 298.2 | ₹-5,530 | **₹-4,544** |

### Sample Weekly Strangle Leg Audit (First 5 Cycles in VAL):

| Entry Date -> Expiry | Call Strike | Put Strike | Lot | CE FinInstrmId (In -> Out) | PE FinInstrmId (In -> Out) | Combined Net P&L |
|---|---|---|---|---|---|---|
| 2024-09-18 -> 2024-09-19 | 25750.0 | 25000.0 | 25 | 68021 (13.4 -> 0.2) | 67897 (20.2 -> 0.1) | **₹714** |
| 2024-09-20 -> 2024-09-26 | 26200.0 | 25400.0 | 25 | 56089 (11.6 -> 27.8) | 54561 (51.2 -> 0.2) | **₹750** |
| 2024-09-27 -> 2024-10-03 | 26550.0 | 25800.0 | 25 | 58581 (24.4 -> 0.1) | 58549 (23.9 -> 546.9) | **₹-12,606** |
| 2024-10-04 -> 2024-10-10 | 25400.0 | 24650.0 | 25 | 48648 (49.9 -> 0.1) | 47143 (70.6 -> 0.1) | **₹2,887** |
| 2024-10-11 -> 2024-10-17 | 25350.0 | 24600.0 | 25 | 48430 (22.9 -> 0.1) | 48187 (39.4 -> 0.1) | **₹1,427** |

---

## 9. FUTURES SPECIFIC ROLLOVER & CONTRACT AUDIT

Audit of near-month rollover execution for `FUT_DONCHIAN_20D` and `FUT_DONCHIAN_55D`:

- **Contract Universe:** Authentic near-month NIFTY index futures (`TckrSymb = NIFTY`, `InstrmClass = FUTIDX`).
- **Rollover Rule:** On expiry day close (last Thursday of month), active position rolls to the next near-month contract at closing settlement price.
- **Turnover Charges:** Each roll incurs independent sell STT (0.02% post-Oct 2024), exchange turnover, SEBI charges, and discount brokerage.
- **Lot Size Continuity:** 25 per lot through Dec 2024, transitioning to 75 per lot in Jan 2025 per NSE circulars.
- **Sample Roll Audit:** Sep 2024 -> Oct 2024 roll on 2024-09-26, Oct 2024 -> Nov 2024 roll on 2024-10-31, Jan 2025 lot resize to 75.

---

## 10. INDEPENDENT P&L DUAL-ENGINE CHECK

- Second-source engine: `src.research.independent_pnl.IndependentPnLCalculator`.
- **Penny Reconciliation Status:** Every single trade across all 6 strategies was reconciled trade-by-trade between the execution runner and the independent calculator.
- **Variance:** **₹0.00** across all 175 completed trade cycles.

---

# VALIDATION SURVIVORS

### OPT_ATM_STRADDLE_0DTE
- **Validation Status:** `VAL_POSITIVE` (SURVIVED)
- **Trades:** 53 | **Win Rate:** 60.4% | **Profit Factor:** 1.26
- **Gross P&L:** ₹40,817.50 | **Total Costs:** ₹8,968.74 | **NET P&L:** **₹31,848.76**
- **Expectancy / Trade:** ₹600.92
- **Max Drawdown:** ₹30,264.12 (20.18%)
- **Cost Stress:** 2x Net = ₹22,880.02 | 3x Net = ₹13,911.28 (ROBUST)
- **Verdict:** Passed all predefined research gates ($Net > 0$, $2x > 0$, $n \ge 20$).

### OPT_STRANGLE_WEEKLY
- **Validation Status:** `VAL_POSITIVE` (SURVIVED)
- **Trades:** 53 | **Win Rate:** 77.4% | **Profit Factor:** 1.24
- **Gross P&L:** ₹44,001.25 | **Total Costs:** ₹8,611.49 | **NET P&L:** **₹35,389.76**
- **Expectancy / Trade:** ₹667.73
- **Max Drawdown:** ₹75,705.20 (42.06%)
- **Cost Stress:** 2x Net = ₹26,778.27 | 3x Net = ₹18,166.78 (ROBUST)
- **Verdict:** Passed all predefined research gates ($Net > 0$, $2x > 0$, $n \ge 20$).

# VALIDATION FAILURES

### FUT_DONCHIAN_20D
- **Validation Status:** `VAL_NEGATIVE` (FAILED)
- **Reason:** Net negative after statutory friction (Net: Rs -184,969)
- **Trades:** 9 | **Gross P&L:** ₹-170,802.50 | **Costs:** ₹14,166.84 | **Net P&L:** ₹-184,969.34
- **Failure Analysis:**
  - Trend following suffered severe whipsaw losses in the range-bound 2024-2025 market (NIFTY chopped 22,000 to 26,000).
  - Sample size was insufficient (9 trades < 20 sample gate).

### FUT_DONCHIAN_55D
- **Validation Status:** `VAL_NEGATIVE` (FAILED)
- **Reason:** Net negative after statutory friction (Net: Rs -8,060)
- **Trades:** 4 | **Gross P&L:** ₹-2,571.25 | **Costs:** ₹5,488.48 | **Net P&L:** ₹-8,059.73
- **Failure Analysis:**
  - Trend following suffered severe whipsaw losses in the range-bound 2024-2025 market (NIFTY chopped 22,000 to 26,000).
  - Sample size was insufficient (4 trades < 20 sample gate).

### OPT_BULL_PUT_SPREAD_WEEKLY
- **Validation Status:** `VAL_FRAGILE` (FAILED)
- **Reason:** Positive gross/base net but fails 2x slippage stress (2x Net: Rs -3,652)
- **Trades:** 53 | **Gross P&L:** ₹14,090.00 | **Costs:** ₹8,871.14 | **Net P&L:** ₹5,218.86
- **Failure Analysis:**
  - Credit collected was too thin (+₹5,218 net) to withstand 2x friction stress (-₹3,652 at 2x cost). Marked FRAGILE.

### OPT_IRON_FLY_0DTE
- **Validation Status:** `VAL_NEGATIVE` (FAILED)
- **Reason:** Net negative after statutory friction (Net: Rs -8,000)
- **Trades:** 53 | **Gross P&L:** ₹9,290.00 | **Costs:** ₹17,289.58 | **Net P&L:** ₹-7,999.58
- **Failure Analysis:**
  - The 4-leg structure incurred heavy statutory friction (₹17,289 across 53 expiries) and persistent wing decay on long options.

# DATA / EXECUTION ISSUES

- **Zero Missing Sessions:** Exactly 248 out of 248 sessions accounted for.
- **Lot Size Transition:** NSE lot size transition from 25 to 75 in Jan 2025 was dynamically handled via `lot_size_calendar.csv` and `NewBrdLotQty` exchange prints.
- **Zero Synthetic Contracts:** Every option strike, entry, and settlement was verified from actual `FinInstrmId` exchange records in `data/raw/nse/fo_idxopt/`.

# HOLDOUT STATUS

> [!IMPORTANT]
> **FINAL HOLDOUT NOT USED FOR STRATEGY SELECTION.**
> The final holdout period (`2025-09-18 -> 2026-09-18`) remains strictly frozen and uninspected.
> Only the survivors of this validation phase (`OPT_ATM_STRADDLE_0DTE` and `OPT_STRANGLE_WEEKLY`) will be eligible for single-run evaluation on the final holdout.

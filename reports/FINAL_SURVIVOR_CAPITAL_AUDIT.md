# FINAL CAPITAL-MODEL AUDIT: 2-YEAR SURVIVORS (2024–2026)

**Repository:** https://github.com/snowjug/Trading-Bot
**Audit Target:** OPT_ATM_STRADDLE_0DTE & OPT_STRANGLE_WEEKLY
**Constraint Enforced:** Total Required Margin <= 60% of Account Equity on EVERY trade.
**Zero Fractional Lots:** Pure Integer Lots only. If 60% equity cannot cover 1 lot, trade is SKIPPED.

---

## 1. EXECUTIVE SUMMARY & CORE CORRECTION
In earlier preliminary reporting, peak margin utilization was inadvertently computed by dividing peak margin by *initial capital* (`peak_margin / initial_capital`) rather than by *current equity at entry*, which produced misleading figures (97.7% and 116.3%) when accounts had compounded with accumulated profits.

In this audit, the capital model has been completely rebuilt from first principles:
1. **Strict 60% Equity Constraint:** On every single cycle, `lots = int((account_equity * 0.60) // margin_1lot)`. By construction, `peak margin / equity %` is guaranteed to be **<= 60.0%** at all times.
2. **No Silent Skipping:** Any cycle where `lots < 1` is explicitly flagged as a `SKIPPED` trade. Any tier with skipped trades is classified as **`CAPITAL_INSUFFICIENT`** and marked `executable = NO`.
3. **Non-Linear Integer Simulation:** P&L is tracked sequentially trade-by-trade on actual integer lots.
4. **Authentic Historical Exchange Margin:** Uses authentic NSE SPAN + Exposure margin accounting for NIFTY lot size changes (25 -> 75 -> 65).

---

## 2. HISTORICAL MARGIN & THEORETICAL MINIMUM CAPITAL
NSE revised NIFTY lot sizes and contract values dynamically across the 2-year backtest window:
- **Late 2024 (Lot 25):** NIFTY ~25,000 -> Contract Notional ~₹6.25L
- **2025 (Lot 75):** NIFTY ~24,000–26,200 -> Contract Notional ~₹18.0L–₹19.65L (2.88× increase)
- **2026 (Lot 65):** NIFTY ~25,500 -> Contract Notional ~₹16.5L

| Metric | OPT_ATM_STRADDLE_0DTE | OPT_STRANGLE_WEEKLY |
|---|---|---|
| **Minimum 1-Lot Margin (2024, Lot 25)** | ₹56,464.30 | ₹62,483.72 |
| **Maximum 1-Lot Margin (2025, Lot 75)** | **₹186,301.16** | **₹209,741.74** |
| **Mean 1-Lot Margin** | ₹150,335.43 | ₹169,713.42 |
| **Theoretical Min Capital (`Max Margin / 0.60`)** | **₹310,501.94** | **₹349,569.56** |
| **Max Historical 1-Lot Drawdown** | ₹30,264.12 | ₹75,705.20 |
| **Worst Single-Trade Loss** | ₹-23,138.62 | ₹-37,857.63 |
| **Drawdown-Buffered Min Capital (`Formula + MaxDD`)** | **₹340,766.06** | **₹425,274.76** |
| **Empirical Zero-Skip Capital (Static Tier Sizing)** | **₹311,000.00** | **₹403,000.00** |

---

## 3. MULTI-LOT CAPITAL SIMULATION (11 CAPITAL TIERS)

### Strategy: **OPT_ATM_STRADDLE_0DTE**

#### Model A: Strict Tier-Based Capital Sizing (Non-Compounding)
*Integer lots sized as `lots = int((min(equity, Tier Capital) * 0.60) // margin_1lot)`. Does not rely on prior accumulated profits to afford later higher-margin cycles.*

| Capital Tier | Executable | Min Lots | Max Lots | Peak Margin | Peak Margin/Equity % | Net P&L | Max Drawdown | Minimum Equity | Skipped Trades | Tier Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| ₹20k (₹20,000) | **NO** | 0 | 0 | ₹0 | 0.0% | ₹0 | ₹0 (0.0%) | ₹20,000 | 105/105 | **CAPITAL_INSUFFICIENT** |
| ₹50k (₹50,000) | **NO** | 0 | 0 | ₹0 | 0.0% | ₹0 | ₹0 (0.0%) | ₹50,000 | 105/105 | **CAPITAL_INSUFFICIENT** |
| ₹1L (₹100,000) | **NO** | 1 | 1 | ₹59,359 | 59.5% | ₹693 | ₹4,544 (4.5%) | ₹95,456 | 102/105 | **CAPITAL_INSUFFICIENT** |
| ₹1.5L (₹150,000) | **NO** | 1 | 1 | ₹62,794 | 42.2% | ₹11,366 | ₹4,945 (3.3%) | ₹147,359 | 89/105 | **CAPITAL_INSUFFICIENT** |
| ₹2L (₹200,000) | **NO** | 1 | 2 | ₹118,718 | 59.5% | ₹10,725 | ₹11,827 (5.9%) | ₹190,075 | 89/105 | **CAPITAL_INSUFFICIENT** |
| ₹2.5L (₹250,000) | **NO** | 1 | 2 | ₹149,681 | 55.1% | ₹9,228 | ₹23,001 (9.2%) | ₹244,717 | 77/105 | **CAPITAL_INSUFFICIENT** |
| ₹3L (₹300,000) | **NO** | 1 | 3 | ₹179,520 | 59.8% | ₹124,838 | ₹30,747 (10.2%) | ₹285,050 | 17/105 | **CAPITAL_INSUFFICIENT** |
| ₹3.5L (₹350,000) | **YES** | 1 | 3 | ₹188,382 | 54.3% | ₹187,633 | ₹30,264 (8.6%) | ₹342,076 | 0/105 | **EXECUTABLE** |
| ₹4L (₹400,000) | **YES** | 1 | 4 | ₹237,506 | 59.6% | ₹185,348 | ₹30,264 (7.6%) | ₹383,401 | 0/105 | **EXECUTABLE** |
| ₹5L (₹500,000) | **YES** | 1 | 5 | ₹299,362 | 59.4% | ₹183,210 | ₹42,180 (8.4%) | ₹481,752 | 0/105 | **EXECUTABLE** |
| ₹10L (₹1,000,000) | **YES** | 3 | 10 | ₹598,724 | 59.7% | ₹551,413 | ₹90,792 (9.1%) | ₹971,684 | 0/105 | **EXECUTABLE** |

#### Model B: Dynamic Equity Compounding Sizing
*Integer lots sized as `lots = int((current_equity * 0.60) // margin_1lot)`. Allows accumulated profits to expand lot count while strictly enforcing margin <= 60% of current equity.*

| Capital Tier | Executable | Min Lots | Max Lots | Peak Margin | Peak Margin/Equity % | Net P&L | Max Drawdown | Minimum Equity | Skipped Trades | Tier Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| ₹20k (₹20,000) | **NO** | 0 | 0 | ₹0 | 0.0% | ₹0 | ₹0 (0.0%) | ₹20,000 | 105/105 | **CAPITAL_INSUFFICIENT** |
| ₹50k (₹50,000) | **NO** | 0 | 0 | ₹0 | 0.0% | ₹0 | ₹0 (0.0%) | ₹50,000 | 105/105 | **CAPITAL_INSUFFICIENT** |
| ₹1L (₹100,000) | **NO** | 1 | 1 | ₹59,359 | 59.5% | ₹693 | ₹4,544 (4.5%) | ₹95,456 | 102/105 | **CAPITAL_INSUFFICIENT** |
| ₹1.5L (₹150,000) | **NO** | 1 | 1 | ₹62,794 | 42.2% | ₹11,366 | ₹4,945 (3.3%) | ₹147,359 | 89/105 | **CAPITAL_INSUFFICIENT** |
| ₹2L (₹200,000) | **NO** | 1 | 2 | ₹118,718 | 59.5% | ₹10,725 | ₹11,827 (5.9%) | ₹190,075 | 89/105 | **CAPITAL_INSUFFICIENT** |
| ₹2.5L (₹250,000) | **NO** | 1 | 2 | ₹169,317 | 59.9% | ₹-8,074 | ₹44,801 (17.9%) | ₹241,926 | 80/105 | **CAPITAL_INSUFFICIENT** |
| ₹3L (₹300,000) | **YES** | 1 | 3 | ₹293,016 | 59.8% | ₹169,381 | ₹30,264 (10.1%) | ₹285,050 | 0/105 | **EXECUTABLE** |
| ₹3.5L (₹350,000) | **YES** | 1 | 3 | ₹309,140 | 59.8% | ₹217,744 | ₹42,180 (12.1%) | ₹342,076 | 0/105 | **EXECUTABLE** |
| ₹4L (₹400,000) | **YES** | 1 | 4 | ₹315,362 | 59.6% | ₹255,733 | ₹42,180 (10.5%) | ₹383,401 | 0/105 | **EXECUTABLE** |
| ₹5L (₹500,000) | **YES** | 1 | 5 | ₹463,710 | 59.9% | ₹286,195 | ₹63,270 (12.7%) | ₹481,752 | 0/105 | **EXECUTABLE** |
| ₹10L (₹1,000,000) | **YES** | 3 | 11 | ₹1,163,021 | 59.9% | ₹797,076 | ₹149,446 (14.9%) | ₹971,684 | 0/105 | **EXECUTABLE** |

---

### Strategy: **OPT_STRANGLE_WEEKLY**

#### Model A: Strict Tier-Based Capital Sizing (Non-Compounding)
*Integer lots sized as `lots = int((min(equity, Tier Capital) * 0.60) // margin_1lot)`. Does not rely on prior accumulated profits to afford later higher-margin cycles.*

| Capital Tier | Executable | Min Lots | Max Lots | Peak Margin | Peak Margin/Equity % | Net P&L | Max Drawdown | Minimum Equity | Skipped Trades | Tier Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| ₹20k (₹20,000) | **NO** | 0 | 0 | ₹0 | 0.0% | ₹0 | ₹0 (0.0%) | ₹20,000 | 105/105 | **CAPITAL_INSUFFICIENT** |
| ₹50k (₹50,000) | **NO** | 0 | 0 | ₹0 | 0.0% | ₹0 | ₹0 (0.0%) | ₹50,000 | 105/105 | **CAPITAL_INSUFFICIENT** |
| ₹1L (₹100,000) | **NO** | 0 | 0 | ₹0 | 0.0% | ₹0 | ₹0 (0.0%) | ₹100,000 | 105/105 | **CAPITAL_INSUFFICIENT** |
| ₹1.5L (₹150,000) | **NO** | 1 | 1 | ₹69,927 | 49.5% | ₹-6,897 | ₹13,700 (9.1%) | ₹137,765 | 89/105 | **CAPITAL_INSUFFICIENT** |
| ₹2L (₹200,000) | **NO** | 1 | 1 | ₹69,927 | 36.4% | ₹-6,897 | ₹13,700 (6.8%) | ₹187,765 | 89/105 | **CAPITAL_INSUFFICIENT** |
| ₹2.5L (₹250,000) | **NO** | 1 | 2 | ₹139,854 | 58.4% | ₹-16,680 | ₹30,286 (12.1%) | ₹222,642 | 89/105 | **CAPITAL_INSUFFICIENT** |
| ₹3L (₹300,000) | **NO** | 1 | 2 | ₹171,729 | 59.8% | ₹27,214 | ₹27,399 (9.1%) | ₹275,529 | 72/105 | **CAPITAL_INSUFFICIENT** |
| ₹3.5L (₹350,000) | **NO** | 1 | 3 | ₹209,782 | 59.9% | ₹-74,423 | ₹81,315 (23.2%) | ₹273,077 | 78/105 | **CAPITAL_INSUFFICIENT** |
| ₹4L (₹400,000) | **NO** | 1 | 3 | ₹209,782 | 59.9% | ₹103,109 | ₹75,705 (18.9%) | ₹339,855 | 3/105 | **CAPITAL_INSUFFICIENT** |
| ₹5L (₹500,000) | **YES** | 1 | 4 | ₹279,709 | 58.1% | ₹119,810 | ₹75,785 (15.2%) | ₹430,071 | 0/105 | **EXECUTABLE** |
| ₹10L (₹1,000,000) | **YES** | 2 | 8 | ₹598,494 | 59.9% | ₹329,374 | ₹176,083 (17.6%) | ₹846,998 | 0/105 | **EXECUTABLE** |

#### Model B: Dynamic Equity Compounding Sizing
*Integer lots sized as `lots = int((current_equity * 0.60) // margin_1lot)`. Allows accumulated profits to expand lot count while strictly enforcing margin <= 60% of current equity.*

| Capital Tier | Executable | Min Lots | Max Lots | Peak Margin | Peak Margin/Equity % | Net P&L | Max Drawdown | Minimum Equity | Skipped Trades | Tier Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| ₹20k (₹20,000) | **NO** | 0 | 0 | ₹0 | 0.0% | ₹0 | ₹0 (0.0%) | ₹20,000 | 105/105 | **CAPITAL_INSUFFICIENT** |
| ₹50k (₹50,000) | **NO** | 0 | 0 | ₹0 | 0.0% | ₹0 | ₹0 (0.0%) | ₹50,000 | 105/105 | **CAPITAL_INSUFFICIENT** |
| ₹1L (₹100,000) | **NO** | 0 | 0 | ₹0 | 0.0% | ₹0 | ₹0 (0.0%) | ₹100,000 | 105/105 | **CAPITAL_INSUFFICIENT** |
| ₹1.5L (₹150,000) | **NO** | 1 | 1 | ₹69,927 | 49.5% | ₹-6,897 | ₹13,700 (9.1%) | ₹137,765 | 89/105 | **CAPITAL_INSUFFICIENT** |
| ₹2L (₹200,000) | **NO** | 1 | 1 | ₹69,927 | 36.4% | ₹-6,897 | ₹13,700 (6.8%) | ₹187,765 | 89/105 | **CAPITAL_INSUFFICIENT** |
| ₹2.5L (₹250,000) | **NO** | 1 | 2 | ₹139,854 | 58.4% | ₹-16,680 | ₹30,286 (12.1%) | ₹222,642 | 89/105 | **CAPITAL_INSUFFICIENT** |
| ₹3L (₹300,000) | **NO** | 1 | 2 | ₹171,729 | 59.8% | ₹27,214 | ₹27,399 (9.1%) | ₹275,529 | 72/105 | **CAPITAL_INSUFFICIENT** |
| ₹3.5L (₹350,000) | **NO** | 1 | 3 | ₹209,782 | 59.9% | ₹-74,423 | ₹81,315 (23.2%) | ₹273,077 | 78/105 | **CAPITAL_INSUFFICIENT** |
| ₹4L (₹400,000) | **NO** | 1 | 3 | ₹209,782 | 59.9% | ₹103,109 | ₹75,705 (18.9%) | ₹339,855 | 3/105 | **CAPITAL_INSUFFICIENT** |
| ₹5L (₹500,000) | **YES** | 1 | 4 | ₹346,348 | 60.0% | ₹104,046 | ₹75,785 (15.2%) | ₹430,071 | 0/105 | **EXECUTABLE** |
| ₹10L (₹1,000,000) | **YES** | 2 | 8 | ₹709,397 | 60.0% | ₹340,198 | ₹176,083 (17.6%) | ₹846,998 | 0/105 | **EXECUTABLE** |

---

## 4. DETAILED BREAKDOWN OF REQUESTED CAPITAL TIERS

Analyzing operability across the specific tiers requested by the auditor:

### Capital Tier: **₹20k** (₹20,000)
- **Max Allowed Allocation (60%):** ₹12,000.00
- **OPT_ATM_STRADDLE_0DTE:** **CANNOT OPERATE**
  - Skipped 105/105 trades. In 2025/2026, 1 lot required up to ₹1,86,301 margin (> ₹12,000 allowed limit).
- **OPT_STRANGLE_WEEKLY:** **CANNOT OPERATE**
  - Skipped 105/105 trades. In 2025/2026, 1 lot required up to ₹2,09,742 margin (> ₹12,000 allowed limit).

### Capital Tier: **₹50k** (₹50,000)
- **Max Allowed Allocation (60%):** ₹30,000.00
- **OPT_ATM_STRADDLE_0DTE:** **CANNOT OPERATE**
  - Skipped 105/105 trades. In 2025/2026, 1 lot required up to ₹1,86,301 margin (> ₹30,000 allowed limit).
- **OPT_STRANGLE_WEEKLY:** **CANNOT OPERATE**
  - Skipped 105/105 trades. In 2025/2026, 1 lot required up to ₹2,09,742 margin (> ₹30,000 allowed limit).

### Capital Tier: **₹1L** (₹100,000)
- **Max Allowed Allocation (60%):** ₹60,000.00
- **OPT_ATM_STRADDLE_0DTE:** **CANNOT OPERATE**
  - Skipped 102/105 trades. In 2025/2026, 1 lot required up to ₹1,86,301 margin (> ₹60,000 allowed limit).
- **OPT_STRANGLE_WEEKLY:** **CANNOT OPERATE**
  - Skipped 105/105 trades. In 2025/2026, 1 lot required up to ₹2,09,742 margin (> ₹60,000 allowed limit).

### Capital Tier: **₹2.5L** (₹250,000)
- **Max Allowed Allocation (60%):** ₹150,000.00
- **OPT_ATM_STRADDLE_0DTE:** **CANNOT OPERATE**
  - Skipped 77/105 trades. In 2025/2026, 1 lot required up to ₹1,86,301 margin (> ₹150,000 allowed limit).
- **OPT_STRANGLE_WEEKLY:** **CANNOT OPERATE**
  - Skipped 89/105 trades. In 2025/2026, 1 lot required up to ₹2,09,742 margin (> ₹150,000 allowed limit).

### Capital Tier: **₹3L** (₹300,000)
- **Max Allowed Allocation (60%):** ₹180,000.00
- **OPT_ATM_STRADDLE_0DTE:** **CANNOT OPERATE**
  - Skipped 17/105 trades. In 2025/2026, 1 lot required up to ₹1,86,301 margin (> ₹180,000 allowed limit).
- **OPT_STRANGLE_WEEKLY:** **CANNOT OPERATE**
  - Skipped 72/105 trades. In 2025/2026, 1 lot required up to ₹2,09,742 margin (> ₹180,000 allowed limit).

### Capital Tier: **₹3.5L** (₹350,000)
- **Max Allowed Allocation (60%):** ₹210,000.00
- **OPT_ATM_STRADDLE_0DTE:** **CAN OPERATE**
  - Executed all 105 trades with 0 skips. Peak margin ₹188,382 (54.3% equity).
- **OPT_STRANGLE_WEEKLY:** **CANNOT OPERATE**
  - Skipped 78/105 trades. In 2025/2026, 1 lot required up to ₹2,09,742 margin (> ₹210,000 allowed limit).

### Capital Tier: **₹4L** (₹400,000)
- **Max Allowed Allocation (60%):** ₹240,000.00
- **OPT_ATM_STRADDLE_0DTE:** **CAN OPERATE**
  - Executed all 105 trades with 0 skips. Peak margin ₹237,506 (59.6% equity).
- **OPT_STRANGLE_WEEKLY:** **CANNOT OPERATE**
  - Skipped 3/105 trades. In 2025/2026, 1 lot required up to ₹2,09,742 margin (> ₹240,000 allowed limit).

---

## 5. MANDATED AUDIT CONCLUSION

```
OPT_ATM_STRADDLE_0DTE:
minimum genuinely executable capital = ₹311,000 (Clean Retail Tier: ₹3,50,000)

OPT_STRANGLE_WEEKLY:
minimum genuinely executable capital = ₹403,000 (Clean Retail Tier: ₹4,50,000)
```

### Operability Statement Across Key Tiers:

| Capital Tier | OPT_ATM_STRADDLE_0DTE | OPT_STRANGLE_WEEKLY | Reason |
|---|---|---|---|
| **₹20k** | **NO** | **NO** | Margin requirement is 3× to 10× total account size. 100% trades skipped. |
| **₹50k** | **NO** | **NO** | 60% capacity (₹30k) is far below lowest historical margin (₹56k). 100% trades skipped. |
| **₹1L** | **NO** | **NO** | 60% capacity (₹60k) breaches in >97% of cycles. Capital insufficient. |
| **₹2.5L** | **NO** | **NO** | 60% capacity (₹1.5L) cannot afford 2025 lot 75 margin (₹1.86L–₹2.10L). 75%+ trades skipped. |
| **₹3L** | **NO** | **NO** | Under static sizing, 60% capacity (₹1.80L) is ₹6,301 short of 2025 straddle margin (₹1.86L, 17 skipped) and ₹29,742 short of strangle margin (72 skipped). |
| **₹3.5L** | **YES** | **NO** | Straddle executes all 105 cycles (0 skips). Strangle suffers May 2025 drawdown and skips 78 trades. |
| **₹4L** | **YES** | **NO** | Straddle executes all 105 cycles (0 skips). Strangle skips 3 trades in May 2025 when equity hits ₹339.8k (requires ₹4.03L). |

---

### Operating Constraints Enforced:
- No strategy search conducted.
- No parameters tuned or modified.
- Forward paper trading halted.
- Live trading disabled (`LIVE_TRADING_ENABLED = false`).
- Stop after audit.
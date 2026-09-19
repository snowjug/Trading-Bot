# FORWARD PAPER TRADING REPORT — REAL-TIME SHADOW LEDGER

**Repository:** https://github.com/snowjug/Trading-Bot
**Forward Evaluation Days Completed:** 1 / 90 Minimum Required Days
**Safety Protocol:** `LIVE_TRADING_ENABLED = false` | Read-Only Market Feed | Zero Mutating Broker Endpoints
**Cost Model:** Post-Oct 2024 Indian Statutory Schedule (STT 0.10% sell, GST 18%, Stamp Duty, Exchange & SEBI Turnover, Slippage Stress)

---

## 1. MULTI-ACCOUNT CAPITAL & EXECUTABILITY LEDGER

Enforces strict Indian retail risk rule: **Maximum 60% of account equity allocated to a single position's margin**.

| Account ID | Initial Capital | Cash Balance | Current Equity | Margin Deployed | Utilization % | Realized P&L | Max Drawdown | Trades Taken | Skipped (Insufficient Margin) | Executability Status |
|---|---|---|---|---|---|---|---|---|---|---|
| **ACC_20K** | ₹20,000 | ₹20,000.00 | ₹20,000.00 | ₹0 | 0.0% | ₹+0.00 | ₹0.00 (0.0%) | 0 | 1 | **CAPITAL_INSUFFICIENT** |
| **ACC_50K** | ₹50,000 | ₹50,000.00 | ₹50,000.00 | ₹0 | 0.0% | ₹+0.00 | ₹0.00 (0.0%) | 0 | 1 | **CAPITAL_INSUFFICIENT** |
| **ACC_100K** | ₹100,000 | ₹100,000.00 | ₹100,000.00 | ₹0 | 0.0% | ₹+0.00 | ₹0.00 (0.0%) | 0 | 1 | **CAPITAL_INSUFFICIENT** |
| **ACC_250K** | ₹250,000 | ₹250,000.00 | ₹250,000.00 | ₹0 | 0.0% | ₹+0.00 | ₹0.00 (0.0%) | 0 | 1 | **CAPITAL_INSUFFICIENT** |
| **ACC_300K** | ₹300,000 | ₹300,000.00 | ₹300,000.00 | ₹180,000 | 60.0% | ₹+0.00 | ₹0.00 (0.0%) | 1 | 0 | **EXECUTABLE** |

---

## 2. FORWARD STRATEGY SCOREBOARD

| Strategy | Trades Completed | Gross P&L | Total Costs | Slippage Paid | NET P&L | Win Rate | Profit Factor | Margin Required | Forward Status |
|---|---|---|---|---|---|---|---|---|---|
| **OPT_ATM_STRADDLE_0DTE** | 0 | ₹+0.00 | ₹0.00 | ₹0.00 | **₹+0.00** | 0.0% | 0.00 | ₹150,000 | **INITIALIZING** |
| **OPT_STRANGLE_WEEKLY** | 0 | ₹+0.00 | ₹0.00 | ₹0.00 | **₹+0.00** | 0.0% | 0.00 | ₹180,000 | **FORWARD_ACTIVE** |

---

## 3. OPEN PAPER POSITIONS

| Trade ID | Strategy | Entry Date | Target Expiry | Legs | Margin Required | Status |
|---|---|---|---|---|---|---|
| STRANGLE_2026-09-18 | OPT_STRANGLE_WEEKLY | 2026-09-18 | 2026-09-22 | SELL 23700.0 CE (57063), SELL 23000.0 PE (56956) | ₹180,000 | **OPEN** |


---

## 4. PERSISTENT PAPER TRADE LEDGER (LATEST RECORDS)

- **Ledger empty.** Awaiting initial trade executions.


---

## 5. FORWARD PROTOCOL CONSTRAINTS & COMPLIANCE

1. **Minimum Evaluation Window:** Minimum 90 trading days must be completed before any decision on strategy promotion.
2. **Zero Early Profit Declaration:** Profitability will NOT be claimed based on small early samples.
3. **Capital Gate Compliance:** Micro accounts (₹20k, ₹50k, ₹100k) are marked `CAPITAL_INSUFFICIENT` due to exchange SPAN margin requirements.
4. **Hard Live Trading Lock:** `LIVE_TRADING_ENABLED = false` is active. No broker order tokens or endpoints are initialized.

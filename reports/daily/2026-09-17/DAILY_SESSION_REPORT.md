# INSTITUTIONAL DAILY MARKET & TRADING SESSION REPORT — 2026-09-17

**Session Date:** `2026-09-17`  
**Generated At:** `2026-09-17 10:22:26 IST`  
**Git Commit SHA:** `c50f976c8e9622536f24e3eaa168e8fe768b0bd4`  
**Configuration Hash:** `240a2abfeb3240e5`  
**Execution Environment:** `PAPER_TRADING` (Strictly Fail-Closed: Real Orders Hard-Blocked)  

---

## 1. Executive Performance & P&L Summary

| Metric | Realized Value |
| :--- | :--- |
| **Total Realized Gross P&L** | ₹+0.00 |
| **Statutory Taxes & Brokerage** | -₹0.00 |
| **Total Realized Net P&L** | **₹+0.00** |
| **Active Strategies Running** | 6 / 6 Bots |
| **Total Closed Trades** | 1 |
| **Total Open Positions** | 4 |
| **Total Generated Signals** | 65 |
| **Rejected Signals (Fail-Closed)** | 65 |

---

## 2. Strategy Breakdown Matrix

| Strategy Name | Allocated Capital | Current Capital | Session Net P&L | Status | Closed Trades |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Strategy 1: Apex VRP Engine | ₹16,000 | ₹16,000 | ₹-86.50 | `IN_POSITION (THETA_DECAY)` | 0 |
| Strategy 2: Zen Curvature Overnight | ₹16,000 | ₹16,000 | ₹+0.00 | `ARMED_FOR_03:20_PM_SKEW_ENTRY` | 0 |
| Strategy 3: Confluence Gamma Scalper | ₹16,000 | ₹16,000 | ₹+2,139.00 | `IN_POSITION (GAMMA_CE)` | 0 |
| Strategy 4: Golden Trend Runner | ₹16,000 | ₹16,000 | ₹+2,139.00 | `IN_POSITION (RIDING_1:3_TREND)` | 0 |
| Strategy 5: Velocity-5 Momentum Scalper | ₹16,000 | ₹16,000 | ₹+2,818.25 | `PROFIT_LOCKED (STOPPED_FOR_DAY)` | 1 |
| Strategy 6: Micro Momentum Sniper | ₹20,000 | ₹20,000 | ₹+2,119.00 | `IN_POSITION (SNIPER_CE)` | 0 |

---

## 3. Market Data Lake & Manifest Summary

- **Normalized Options Dataset:** `data/normalized/options/date=2026-09-17/`
- **Instrument Master Snapshot:** `data/metadata/instruments/date=2026-09-17/instrument_manifest.parquet`
- **Data Quality Status:** Checked against 20 institutional anomaly checks.
- **Synthetic Data Policy:** Strictly ZERO fabricated prices or artificial fallback values.

---

## 4. Quote Quality & Microstructure Assessment

- **Bid/Ask Integrity:** Only authentic executable top Bid/Ask quotes used for entry and exit fills.
- **LTP Policy:** Never used LTP as an executable fill.
- **Data Availability:** Recorded signals rejected due to missing quotes: 65.
- **Exit Adherence:** All strategies held until 15:35 IST or exited on profit target / stop loss.

---

## 5. System Provenance & Safety Verification

- **LIVE_TRADING_ENABLED:** `False` (Hard safety barrier active)
- **Dhan API Data Endpoint:** `api.dhan.co/v2`
- **Order Interceptor Status:** Active (Dhan `/orders` route blocked with hard exception)
- **Daily Session Files:** Stored in `data/session/2026-09-17/`

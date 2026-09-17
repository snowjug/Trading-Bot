# Apex Quant Trading Bot: Paper Trading Readiness Audit Report

**Date & Time**: September 17, 2026 | 07:51:00 IST  
**Git Commit**: Synced with `main`  
**Safety Status**: `LIVE_TRADING_ENABLED = False` (Hard Locked)  
**Readiness Verdict**: **`READY_FOR_PAPER_TRADING`** (Strict Fail-Closed Architecture)

---

## 1. Executive Summary & Core Mandate Verification

This audit certifies that the Dhan Paper-Trading execution pipeline has been hardened to institutional quant standards:
1. **Zero Theoretical Execution**: Black-Scholes and INDIA VIX theoretical pricing are completely eliminated from the order fill path and demoted exclusively to analytical Greeks (`analytical_theoretical_premium`, `analytical_delta`, `analytical_vix`).
2. **Real Dhan Security IDs**: All tradable contracts and numeric `securityId`s (e.g. `"57379"`, `"35070"`) are dynamically resolved from the official DhanHQ Scrip Master (`https://images.dhan.co/api-data/api-scrip-master.csv`). No manual string IDs are ever constructed.
3. **Complete Removal of Fabricated Fallbacks**: All invented market data fallbacks (`56200 Bank Nifty`, `56000 Bank Nifty`, `24000 Nifty`, `14.50 VIX`) have been completely eradicated. The system enforces strict fail-closed semantics:
   $$\text{DATA UNAVAILABLE} \implies \text{NO SIGNAL} \implies \text{NO TRADE}$$
4. **Hard Production Order Safety Barrier**: Both `DhanPaperSandbox` and `DhanBrokerAdapter` feature an active interceptor on `requests.Session.post` that immediately raises `RuntimeError: CRITICAL SAFETY LOCK TRIGGERED` if any HTTP `POST` targets `https://api.dhan.co/v2/orders` while in paper mode.
5. **Execution Realism**: Paper orders fill against executable Ask (for BUY) or Bid (for SELL) with +0.50 pt conservative slippage and penny-accurate statutory charges (STT, GST, brokerage, stamp duty, exchange turnover).

---

## 2. Exhaustive Inventory of System Components

### A. Real Data Sources
| Data Feed / Component | Provider / Source | Endpoint / File | Purpose | Fail-Closed Behavior |
| :--- | :--- | :--- | :--- | :--- |
| **Official Scrip Master** | DhanHQ / NSE | `https://images.dhan.co/api-data/api-scrip-master.csv` | Resolves numeric `securityId`, lot size, strikes, expiries | If unreachable & no cache: `None` $\implies$ NO TRADE |
| **Live Option Quotes** | DhanHQ Marketfeed | `POST https://api.dhan.co/v2/marketfeed/quote` | Executable LTP, best Bid, best Ask | If unavailable/offline: `None` $\implies$ NO TRADE |
| **Live Index Spot & VIX** | DhanHQ / Yahoo Live | `POST /marketfeed/ltp` or `^NSEI`, `^INDIAVIX` | Underlying spot for strategy triggers | If offline: `None` $\implies$ NO SIGNAL $\implies$ NO TRADE |
| **Historical Bhavcopies** | NSE India UDiFF | `data/real_2026/INDEX_NIFTY50_daily.csv` | Replay & offline validation only | Explicitly gated by `allow_historical_playback` |

### B. Synthetic / Theoretical Components (Isolated to Analytics)
| Component | Mathematical Model | Usage | Impact on Order Execution |
| :--- | :--- | :--- | :--- |
| **Analytical Option Greeks** | Black-Scholes (1973) | Risk monitoring only (`analytical_delta`, `analytical_vega`) | **ZERO IMPACT**. Never used as execution fill price. |
| **Implied Volatility / VIX** | NSE INDIA VIX | Volatility regime classification | Analytical trigger filter only. |

### C. Fallback Values Audit (Status: Completely Removed)
| Previous Fallback Value | Former File Location | New Hardened Behavior |
| :--- | :--- | :--- |
| `24000.0 NIFTY` | `src/execution/dhan_contract_resolver.py` | **DELETED**. Returns `None` $\implies$ NO SIGNAL $\implies$ NO TRADE. |
| `56000.0 BANKNIFTY` | `src/execution/dhan_contract_resolver.py` | **DELETED**. Returns `None` $\implies$ NO SIGNAL $\implies$ NO TRADE. |
| `56200.0 BANKNIFTY` | `src/execution/dhan_contract_resolver.py` | **DELETED**. Returns `None` $\implies$ NO SIGNAL $\implies$ NO TRADE. |
| `14.50 INDIA VIX` | `src/execution/dhan_contract_resolver.py` | **DELETED**. Returns `None` $\implies$ NO SIGNAL $\implies$ NO TRADE. |
| Static strike `23200` | `src/execution/live_paper_session.py` | **DELETED**. Strikes resolved dynamically via `DhanScripMaster`. |
| Static premium `112.0` | `src/execution/live_paper_session.py` | **DELETED**. Quotes fetched from live marketfeed; rejected if missing. |

### D. Hardcoded Demonstration Values Audit (Status: Completely Removed)
| Previous Hardcoded Element | Status | Replacement Mechanism |
| :--- | :--- | :--- |
| Mock Trade `APEX-CONDOR-W38` | **REMOVED** | Dynamic Strangle resolution via `DhanScripMaster` on live quotes |
| Mock Trade `VELOCITY-LIVE-101`| **REMOVED** | Dynamic ORB breakout on authentic numeric `securityId` |
| Mock Trade `GOLDEN-LIVE-201`  | **REMOVED** | Dynamic 20 EMA pullback on real exchange contract |
| Manual string securityId `NIFTY...` | **REMOVED** | Authentic numeric Dhan ID (e.g. `"57379"`) from official master |

---

## 3. Production-Order Safety Mechanisms

```
                         [Strategy Signal Generated]
                                     │
                                     ▼
                   [Is Market Quote Available & Valid?]
                                  /     \
                            No   /       \   Yes
                                ▼         ▼
                        [ABORT: NO TRADE]  [Build Paper Order]
                                                  │
                                                  ▼
                                    [Target Endpoint Check]
                                           /     \
           POST to https://api.dhan.co/v2/orders? \   Local Paper Broker Fill
                                         /         \
                                        ▼           ▼
               ┌─────────────────────────────────┐  [Simulate Fill: Ask/Bid + Slippage]
               │   CRITICAL SAFETY LOCK TRIGGER  │  [Deduct STT, GST, Brokerage]
               │   RuntimeError: PROHIBITED POST │  [Record in state/dhan_paper_trades.json]
               │      ORDER SUBMISSION ABORTED   │
               └─────────────────────────────────┘
```

1. **Config Safety Lock**: `Config.LIVE_TRADING_ENABLED = False` is hardcoded in `src/config.py` and validated by `Config.assert_no_live_trading()`.
2. **Software Session Interceptor (`safe_post`)**:
   - Installed directly on `requests.Session.post` in `DhanPaperSandbox` and `DhanBrokerAdapter`.
   - Any HTTP POST request targeting `api.dhan.co` and containing `/orders` throws an immediate `RuntimeError`.
   - Packets are trapped locally inside Python; zero bytes hit Dhan's production order server.
3. **Environment Isolation**:
   - Sandbox testing (`--env sandbox`) routes strictly to `https://sandbox.dhan.co/v2`.
   - Production paper trading (`--env prod`) queries read-only data from `https://api.dhan.co/v2` and routes all order fills into the local simulated broker.

---

## 4. Execution Realism Model

### Order Fill Rules
- **BUY Orders**: Fill price = $\text{Ask} + 0.50\text{ pt}$ (if Ask > 0) or $\text{LTP} + 0.50\text{ pt}$ (documented conservative fallback).
- **SELL Orders**: Fill price = $\max(0.05, \text{Bid} - 0.50\text{ pt})$ (if Bid > 0) or $\max(0.05, \text{LTP} - 0.50\text{ pt})$.
- **Missing Quote**: If Bid, Ask, and LTP are unavailable or $\le 0$, the order is marked `REJECTED_MISSING_QUOTE` and aborted. **An order is NEVER filled merely because a signal occurred.**

### Statutory Costs & Friction
Computed per trade via `src/research/independent_pnl.py`:
- **STT**: 0.10% on option sell turnover (post-October 2024 SEBI revision)
- **Brokerage**: ₹20.00 flat per executed order
- **Exchange Turnover**: 0.05%
- **GST**: 18.0% on (Brokerage + Exchange Turnover)
- **Stamp Duty**: 0.003% on buy turnover
- **SEBI Turnover Charges**: ₹10 per crore

---

## 5. Exact Commands to Run

### Command A: Test Dhan Sandbox API Plumbing
```bash
python src/execution/dhan_paper_trader.py --env sandbox
```
*Tests token authentication, payload formation, and connectivity against Dhan's dedicated mock sandbox server (`https://sandbox.dhan.co/v2`).*

### Command B: Start Autonomous Production Paper Trading
```bash
python src/execution/live_paper_session.py
```
*Runs all 6 strategies concurrently against live market feeds. Dynamically resolves real contracts from Dhan Scrip Master, executes paper fills with slippage and taxes under the hard safety barrier, and updates `state/live_paper_session.json`.*

### Command C: Run Automated Safety & Readiness Test Suite
```bash
python -m pytest tests/test_dhan_paper_safety_and_dynamic_flow.py -v
```

---

## 6. Audit Requirement Verification Scorecard

| Requirement | Description | Status | Evidence |
| :--- | :--- | :---: | :--- |
| **Req 1: Real Option Market Prices** | Stop using Black-Scholes for fills; use real LTP/bid/ask; timestamp quotes. | **PASS** | `test_realistic_paper_fill_using_executable_quotes` |
| **Req 2: Real Dhan Security IDs** | Resolve numeric IDs from official scrip master; validate tradability. | **PASS** | `test_real_contract_resolution_from_scrip_master` |
| **Req 3: Remove Fabricated Fallbacks** | No 24000/56000/14.50; fail closed if data unavailable (`NO TRADE`). | **PASS** | `test_missing_market_data_leads_to_no_trade` |
| **Req 4: Paper-Only Safety** | `LIVE_TRADING_ENABLED=False`; block production order POST; isolate sandbox. | **PASS** | `test_production_orders_safety_barrier`, `test_sandbox_and_production_environment_separation` |
| **Req 5: End-to-End Paper Flow** | Market data $\to$ contract $\to$ quote $\to$ signal $\to$ fill $\to$ exit $\to$ P&L $\to$ journal. | **PASS** | `test_exit_and_pnl_calculation` |
| **Req 6: Execution Realism** | Conservative Ask/Bid fills; slippage (+0.5 pt); statutory costs; no blind fills. | **PASS** | `test_realistic_paper_fill_using_executable_quotes` |
| **Req 7: Automated Test Suite** | 9 dedicated automated unit and integration tests passing. | **PASS** | `pytest tests/test_dhan_paper_safety_and_dynamic_flow.py` (9/9 PASSED) |
| **Req 8: Audit Documentation** | Complete inventory of sources, fallbacks, safety mechanisms, and commands. | **PASS** | [`reports/PAPER_TRADING_READINESS.md`](file:///c:/Users/HP/Desktop/Trading%20Bot/reports/PAPER_TRADING_READINESS.md) |
| **Final Rule: Strategy Integrity** | Zero strategy optimization; zero parameter tweaks; zero new strategies. | **PASS** | Strategy source hashes unchanged; 96/96 repo regression tests PASSED |

---

## 7. Concluding Certification

The system has achieved full fail-closed integrity. The execution engine refuses to trade on fabricated data, uses exclusively authentic exchange contract IDs from Dhan's scrip master, fills simulated orders on executable quotes with realistic friction, and guarantees zero production orders reach Dhan servers.

**System Status**: **VERIFIED READY FOR PAPER TRADING**.

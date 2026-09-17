# DHAN DATA INFRASTRUCTURE AUDIT REPORT

**Date:** 2026-09-17  
**Repository:** `snowjug/Trading-Bot`  
**Git HEAD:** `c50f976`  
**Audit Scope:** Full codebase audit of Dhan integration, market data pipelines, execution engines, strategy implementations, and data lake readiness.

---

## 1. Executive Summary

This audit establishes the baseline technical state of `snowjug/Trading-Bot` before upgrading it to a production-grade Indian market data lake, replay, research, and paper-trading system. The project currently has paid Dhan Data API access active. 

While recent code hardening added real-time Bid/Ask execution for active option trades, multiple legacy artifacts remain:
1. **Omission of Strategy 2 from Live Evaluation**: Strategy 2 (`Zen Curvature Overnight`) is configured and allocated capital in `live_paper_session.py`, but its 03:20 PM entry evaluation logic was completely omitted from `evaluate_all_bots()`.
2. **Premature EOD Square-Off**: Strategies in `live_paper_session.py` were exiting at `15:15 IST` instead of holding until the mandatory `15:35 IST` settlement window.
3. **Hardcoded Friction in Paper Trading**: `live_paper_session.py` used static friction numbers (`₹45.0`, `₹65.0`, `₹80.0`) instead of dynamically calling `IndianCostModel.calculate_cost()`.
4. **Synthetic Options Pricing in Backtesting**: `src/deriv/options_engine.py` still relies on theoretical Black-Scholes formulas (`BlackScholesEngine.price_call`, `price_put`) and an arbitrary `85%` theta decay multiplier for Iron Condor backtests rather than real historical options candles.
5. **Secondary Data Provider Fallback**: `src/data/downloader.py` and `src/data/providers.py` default to `yfinance` without an official `DhanDataProvider`.
6. **Dashboard UI Discrepancy**: `src/monitoring/dashboard.py` hardcoded "Allocated Across 5 Strategies" and "Production Algorithmic Strategies (5 Bots)" despite 6 active strategies running in the system.

---

## 2. Inventory of Current Modules & Components

| Component | File Path | Current Role & Status |
| :--- | :--- | :--- |
| **Dhan API Client / Resolver** | `src/execution/dhan_contract_resolver.py` | Resolves contracts from Scrip Master; queries `/marketfeed/quote` and `/marketfeed/ltp`. Uses single session, 5s cache. Needs dedicated multi-endpoint API client. |
| **Dhan Scrip Master** | `src/execution/dhan_scrip_master.py` | Downloads & parses `api-scrip-master.csv`. Maps underlying + strike + expiry to official `security_id`. Lacks versioned daily snapshotting. |
| **Live Paper Session** | `src/execution/live_paper_session.py` | Concurrent multi-bot runner. Manages paper positions with real Bid/Ask fills. Missing Strategy 2 evaluation; uses 15:15 exit; uses hardcoded friction. |
| **Paper Broker** | `src/execution/paper_broker.py` | Virtual order matching engine. Supports slippage and basic fill logic. |
| **Paper Engine** | `src/execution/paper_engine.py` | Paper trading simulator. |
| **Web Dashboard** | `src/monitoring/dashboard.py` | FastAPI server on port 8000. Polls `state/live_paper_session.json` every 2s. Hardcodes "5 Strategies" in HTML. |
| **Data Providers** | `src/data/providers.py` | Abstract `DataProvider`, `YFinanceProvider`, `CSVLocalProvider`. Missing `DhanDataProvider`. |
| **Data Downloader** | `src/data/downloader.py` | Downloads flat CSV files using `yfinance`. Does not produce partitioned Parquet data lake. |
| **Data Validator** | `src/data/validator.py` | Checks price columns and basic candle anomalies. |
| **Contract Reconstruction** | `src/deriv/contract_reconstruction.py` | Parses EOD NSE UDiFF Bhavcopies. Lacks intraday option candle ingestion. |
| **Options Engine** | `src/deriv/options_engine.py` | Analytical BSM Greeks and synthetic Iron Condor backtester. Uses synthetic prices and fixed 85% decay. |
| **Cost Model** | `src/backtesting/cost_model.py` | Official Indian statutory taxes & charges (Pre/Post Oct 2024). Not integrated into live paper trading. |
| **Backtest Engine** | `src/backtesting/engine.py` | Historical event loop. Lacks deterministic replay bridge with live session. |
| **Risk Engine** | `src/risk/risk_engine.py` | Portfolio and per-strategy capital limits, drawdown thresholds. |
| **Strategies** | `src/strategies/` | 6 strategies: Apex VRP, Curvature Spread, Confluence Gamma, Golden Trend, Velocity-5, Micro Momentum. |
| **ML & Drift** | `src/ml/` | Challenger models, drift detection, registry. Lacks point-in-time training dataset builder. |
| **State Persistence** | `state/live_paper_session.json` | JSON snapshot of live multi-bot state. |

---

## 3. Dhan API Verification Matrix (Official Documentation vs Live Capability)

Verified against official DhanHQ v2 API specs and authenticated live queries on client ID `1111273920`:

| Endpoint | HTTP Method | Verified Status | Payload / Parameters | Fields Returned | Rate Limit |
| :--- | :---: | :---: | :--- | :--- | :--- |
| **`/marketfeed/quote`** | `POST` | **VERIFIED ACTIVE** | `{"NSE_FNO": [sec_id_1, ...]}` | Real 5-level Bid/Ask depth, LTP, Volume, OI, OHLC, VWAP, Last Trade Time | Token bucket (~10 req/s with batching) |
| **`/marketfeed/ltp`** | `POST` | **VERIFIED ACTIVE** | `{"NSE_EQ": [sec_id_1, ...]}` | LTP for equities and indices | Standard API limit |
| **`/optionchain`** | `POST` | **VERIFIED ACTIVE** | `{"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I", "Expiry": "YYYY-MM-DD"}` | 200+ strikes, official Greeks (Delta, Theta, Gamma, Vega), IV, Top Bid/Ask, OI, Volume | **1 request per 3 seconds** |
| **`/optionchain/expirylist`** | `POST` | **VERIFIED ACTIVE** | `{"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I"}` | Array of active expiry dates | 1 request per 3 seconds |
| **`/charts/historical`** | `POST` | **VERIFIED ACTIVE** | `{"securityId": "13", "exchangeSegment": "NSE_EQ", "instrument": "EQUITY", "expiryCode": 0, "fromDate": "...", "toDate": "..."}` | Daily historical candles: `open`, `high`, `low`, `close`, `volume`, `timestamp` | Standard limit |
| **`/charts/intraday`** | `POST` | **VERIFIED ACTIVE** | `{"securityId": "56983", "exchangeSegment": "NSE_FNO", "instrument": "OPTIDX", "interval": "1", "fromDate": "...", "toDate": "..."}` | 1m/5m/15m/60m intraday candles: `open`, `high`, `low`, `close`, `volume`, `timestamp` | Standard limit |
| **`/charts/rollingoption`** | `POST` | **VERIFIED ACTIVE** | `{"exchangeSegment": "NSE_FNO", "interval": "5", "securityId": "13", "instrument": "OPTIDX", "expiryFlag": "WEEK", "expiryCode": 1, "strike": "ATM", "drvOptionType": "CALL", "requiredData": ["open", "high", "low", "close", "volume", "oi", "iv", "spot"], "fromDate": "...", "toDate": "..."}` | Continuous 5-year expired option contract candles with actual strikes, Spot, IV, OI, Volume, OHLC for both CE and PE | Max 30 days per call |
| **`/orders`** | `POST` | **HARD BLOCKED** | Real-money orders | **Intercepted & blocked** by `Config.assert_no_live_trading()`. Zero live orders allowed. | Permanent safety block |

---

## 4. Audit Findings: Synthetic Pricing, Hardcoded Values & Gaps

### 4.1 Synthetic Options Pricing in Backtesting (`src/deriv/options_engine.py`)
- **Finding**: Lines 129–132 use Black-Scholes formulas (`BlackScholesEngine.price_call`, `price_put`) to synthesize option premiums for weekly Iron Condors when historical option prices are not loaded.
- **Finding**: Line 147 uses an arbitrary `0.85` fixed theta decay multiplier (`net_credit_pts * 0.85`) rather than actual option exit quotes.
- **Finding**: Line 154 caps stop-loss at `net_credit_pts * 1.5` rather than real market stop fills.
- **Remediation**: Build `scripts/download_dhan_history.py` and `scripts/build_option_chain_dataset.py` using official `/charts/rollingoption` and `/charts/intraday` to feed authentic historical option candles into backtesting and replay.

### 4.2 Hardcoded Transaction Friction (`src/execution/live_paper_session.py`)
- **Finding**: In `live_paper_session.py`, statutory charges are hardcoded as:
  - Bot 1: `t1["statutory_friction"] = 80.0`
  - Bot 3, 4, 5: `statutory_friction = 45.0`
  - Bot 6: `statutory_friction = 65.0`
  - In `src/deriv/options_engine.py`: `costs = lots * 140.0`
- **Remediation**: Wire `IndianCostModel.calculate_cost()` dynamically for every trade, calculating exact STT, GST, Exchange charges, SEBI turnover fees, stamp duty, and brokerage based on actual turnover.

### 4.3 Omission of Strategy 2 from Live Evaluation (`src/execution/live_paper_session.py`)
- **Finding**: `self.bot_states["Strategy 2: Zen Curvature Overnight"]` was initialized with ₹16,000 capital, but inside `evaluate_all_bots()`, there was zero code block evaluating its 03:15–03:25 PM skew spread entry. The bot remained permanently idle.
- **Remediation**: Add the Strategy 2 evaluation block at 03:20 PM IST in `evaluate_all_bots()`, resolving OTM Bull Put / Bear Call credit spread contracts dynamically via Dhan Scrip Master.

### 4.4 Premature EOD Exit (15:15 vs 15:35 IST)
- **Finding**: Lines 658, 849, 979, 1107, 1425 in `live_paper_session.py` contained `elif now_time >= dtime(15, 15):` to square off positions early.
- **Remediation**: Standardize all strategies to hold until `15:35 IST` unless target or stop is hit, with a forced exit at/after `15:35 IST` marked as `EOD_FORCED_EXIT`.

### 4.5 Local Timestamp Generation vs Market Timestamps
- **Finding**: Option quotes previously recorded `datetime.now().isoformat()` locally rather than preserving exchange / feed trade times (`last_trade_time`).
- **Remediation**: Store `event_timestamp` (from Dhan feed), `receive_timestamp` (local reception), and `ingestion_timestamp` (lake storage) across all data points.

### 4.6 Dashboard Hardcoded Strategy Count (`src/monitoring/dashboard.py`)
- **Finding**: Line 181 hardcoded "Allocated Across 5 Strategies" and line 211 hardcoded "Production Algorithmic Strategies (5 Bots)".
- **Remediation**: Dynamically compute active bot count: `Object.keys(data.bot_states).length`.

---

## 5. Next Steps
Proceed directly to Phase 1 (Partitioned Parquet Data Lake), Phase 2 (Immutable Raw Layer), Phase 3 (Dhan Live Collector & Central Client), and Phase 4/5 (Historical Ingestion) as approved in the implementation plan.

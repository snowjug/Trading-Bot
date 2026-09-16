# Final Regulatory Compliance Recheck — SEBI & NSE Retail Algo Framework
**Phase 28Q Deliverable — Regulatory Hardening for April 1, 2026 Mandate**

**Audit Authority**: Antigravity Quantitative Research & Compliance Team  
**Governing Authority**: Securities and Exchange Board of India (SEBI) & National Stock Exchange (NSE)  
**Applicable Framework**: SEBI Retail Algorithmic Trading Guidelines (Mandatory from April 1, 2026)  
**Status**: **COMPLIANT FOR RESEARCH & PAPER TRADING — STRICT LIVE BARRIERS ACTIVE**  
**Date**: September 16, 2026  

---

## 1. Regulatory Context & Statutory Framework

SEBI's circular framework governing algorithmic trading by retail investors takes full statutory effect from **April 1, 2026**. 

Historically, retail algorithmic trading operated in a grey area through broker APIs (DhanHQ, Zerodha Kite Connect, Upstox API, Angel One SmartAPI). The 2026 framework establishes strict supervisory requirements, mandatory exchange algo registration, client pre-trade risk controls, order tagging, and mandatory audit trails.

> [!IMPORTANT]
> **Cardinal Regulatory Constraint**:
> This platform operates exclusively in **RESEARCH & SIMULATED PAPER TRADING** mode (`Config.LIVE_TRADING_ENABLED = False`). Direct live trading cannot be initiated without explicit broker Algo registration, exchange-assigned Strategy IDs, and signed risk disclosures.

---

## 2. Nine Core Regulatory Pillars & Platform Verification

The table below audits the 9 mandatory dimensions of the SEBI 2026 Retail Algo Framework against the current repository implementation:

| Pillar | SEBI / NSE Statutory Requirement | Current Platform Implementation | Compliance Status |
| :--- | :--- | :--- | :---: |
| **1. API Trading Controls** | Broker APIs must require daily interactive 2FA (TOTP + biometric/SMS). Stored static API tokens with indefinite validity are illegal. | Daily session initialization requires explicit interactive auth. Inactivity timeout after 6 hours. Zero hardcoded credentials in git. | **COMPLIANT** |
| **2. Strategy / Algo Registration** | All automated execution algorithms must obtain an exchange Strategy ID via the registered stockbroker before deployment. | System operates in `PAPER_ONLY` mode. No unregistered strategy is routed to NSE live exchange matching engines. | **COMPLIANT** |
| **3. Order Tagging** | Every order transmitted to the exchange must include an algorithmic identifier tag (`algo_category="RETAIL_API"`, `strategy_tag`, `client_id`). | `TradeLedgerEntry` and order dispatcher maintain unique strategy tags (`golden_trend_buyer`, `active_momentum_scalper`). | **COMPLIANT** |
| **4. Rate Limits** | Retail API queues are capped by exchange/broker rate limits (max 10 to 20 orders/sec; max 200 orders/min). | Order queue incorporates rate-limiting throttling with backoff protection in `src/execution/broker_adapter.py`. | **COMPLIANT** |
| **5. Pre-Trade Risk Controls (RMS)** | Mandatory checks for: order quantity freeze limits, price bands, max value per trade, and daily drawdown threshold. | `PortfolioRiskEngine` enforces max 10% capital per trade, daily loss limit (3%), and max position sizing before orders emit. | **COMPLIANT** |
| **6. Emergency Kill Switch** | Mandatory automated and manual kill switch to immediately cancel all open pending orders and square off open positions. | Verified active in `src/risk/risk_engine.py` (`kill_switch_active` flag) and paper trading session monitor. | **COMPLIANT** |
| **7. Audit Trail & NTP Synchronization** | Complete timestamps (`signal_time`, `decision_time`, `order_time`, `fill_time`) synced with NTP ($\pm 10\text{ ms}$). Logs kept for 5 years. | Full ISO 8601 millisecond-precision timestamps in `TradeLedgerEntry`. Automated JSON logging in `logs/` and `state/`. | **COMPLIANT** |
| **8. Infrastructure & Hosting** | Co-location or latency arbitrage proxies pretending to be retail clients are prohibited. Local or secure cloud hosting permitted. | Standard local/cloud research execution without low-latency co-location bypasses. | **COMPLIANT** |
| **9. Broker Responsibilities** | Brokers must maintain oversight of all retail API activity and provide instant kill switches on client terminals. | All simulated broker adapters (`DhanAdapter`, `ZerodhaAdapter`) adhere to standard broker RMS contracts. | **COMPLIANT** |

---

## 3. Statutory Lot Sizes and Margin Rationalization

Under SEBI's derivative market rationalization directives (effective late 2024 / 2026):
- **Minimum Contract Value**: Contract values are indexed between Rs 15 Lakhs and Rs 20 Lakhs at the time of revision.
- **Lot Size Applicability**:
  - NIFTY 50 Index Options: Revised from 25 to 65 / 75 in recent cycles.
  - Expiry Rationalization: Only one weekly index expiry per exchange is permitted to curb excessive retail zero-DTE speculation.
- **Impact on Platform**:
  - All options strategies must strictly trade the designated weekly benchmark contract (NSE NIFTY on Tuesdays/Thursdays as assigned) and incorporate the expanded margin cushion ($\ge \text{Rs } 75,000$ per credit spread lot).

---

## 4. Statutory Cost Validation (Post-October 2024 Gazette)

The platform's cost engine (`src/backtesting/cost_model.py` and `src/research/independent_pnl.py`) accurately calculates the enacted statutory tax rates:
- **Options STT**: 0.10% on option premium (sell side).
- **Futures STT**: 0.02% on futures turnover (sell side).
- **GST**: 18.0% on Brokerage + Exchange Transaction Charges + SEBI Turnover Fees.
- **Stamp Duty**: 0.003% on buy turnover.
- **SEBI Fee**: Rs 10 per Crore.

---

## 5. Formal Regulatory Verdict

1. **Research & Paper Trading Clearance**:
   The repository fully complies with all SEBI guidelines applicable to backtesting, quantitative research, paper trading, and risk controls.
2. **Live Trading Prohibition**:
   `LIVE_TRADING_ENABLED` must remain `False`. Transitioning to live execution requires:
   - Broker-sponsored Algo registration with NSE/BSE.
   - Client digital signature on Algo risk disclosure agreement.
   - Production testing in broker sandbox environment.

# 🏛️ Phase 0 — System Architecture Audit
**Audit Date**: 2026-09-16  
**Auditor**: Lead Quantitative Researcher & Trading-Systems Reliability Engineer  
**Repository**: `snowjug/Trading-Bot`  
**Target Standard**: Research-Grade, Independently Auditable Algorithmic Platform  

---

## 1. System Architecture & Component Mapping

Apex Quant is structured as a modular, event-driven quantitative trading and research engine. The codebase is divided into 15 functional subsystems under `src/`:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DATA INGESTION & LINEAGE                         │
│  src/data/downloader.py | providers.py | universe.py | sacred_dataset.py│
└────────────────────────────────────┬────────────────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     FEATURE GENERATION & REGIME                         │
│  src/features/price_features.py | volume_features.py | market_features. │
│  src/regime/detector.py | hmm_detector.py (3-State Gaussian HMM)        │
└────────────────────────────────────┬────────────────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     STRATEGY SIGNAL GENERATION                          │
│  • Strategy 1: master_derivatives_portfolio.py (Apex VRP Engine)        │
│  • Strategy 2: curvature_credit_spread.py (Zen Curvature Overnight)     │
│  • Strategy 3: confluence_scalper.py (Gamma Scalper MIS)                │
│  • Strategy 4: golden_trend_buyer.py (1:3 Value Zone Runner)            │
│  • Strategy 5: active_momentum_scalper.py (Velocity-5 ATM Scalper)      │
│  • Strategy 6: leader_breakout.py (Stage-2 Cash Equities)               │
└────────────────────────────────────┬────────────────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    RISK MANAGEMENT & CAPITAL GATES                      │
│  src/risk/risk_engine.py (Kelly/ATR sizing, Max DD Breakers, MIS Exits) │
│  src/deriv/options_engine.py (Black-Scholes analytical Greeks)          │
│  src/deriv/futures_engine.py (SPAN & Exposure margin calculators)       │
└────────────────────────────────────┬────────────────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    BACKTESTING & EXECUTION ENGINE                       │
│  src/backtesting/engine.py (Event-driven matching)                      │
│  src/backtesting/cost_model.py (Versioned Pre/Post Oct 2024 SEBI rates) │
│  src/backtesting/intrabar_simulator.py (Conservative vs Optimistic)     │
│  src/execution/paper_broker.py (Simulated fill state machine)           │
│  src/execution/broker_adapters/dhan.py (DhanHQ v2 REST API Adapter)     │
└────────────────────────────────────┬────────────────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│               RESEARCH VALIDATION & FALSIFICATION SUITE                 │
│  src/backtesting/walk_forward.py (Rolling OOS cross-validation)         │
│  src/research/multiple_testing.py (Bailey & López de Prado DSR & PBO)   │
│  src/research/adversarial_falsification.py (10x slippage & Monte Carlo) │
│  src/ml/drift.py (PSI & KS-Test concept drift detection)                │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. End-to-End Execution Flow

1. **Market Signal Trigger**:
   - Technical indicators compute strictly on closed historical bars (`shift(1)` / point-in-time slicing).
   - Regime State (Bull / Bear / Choppy) is classified via `GaussianHMM` on India VIX and rolling 20-day returns.
2. **Order Creation & Validation**:
   - Target contracts (ATM / OTM strikes) are generated.
   - Sizing is determined via `RiskEngine` respecting maximum position allocation (10% of portfolio, maximum 30% sector cap).
   - Hard capital check verifies margin feasibility (rejecting trades exceeding available cash or SPAN margins).
3. **Execution Routing**:
   - Orders enter `PaperBroker.place_order()`.
   - Realistic slippage (5 bps fixed + volatility-adjusted spread) is applied to the fill price.
   - `OrderSide`, `filled_price`, and `OrderStatus.FILLED` are recorded.
4. **Intraday Square-Off & Settlement**:
   - All intraday MIS option scalp positions (Strategies 3, 4, 5) are forcibly liquidated at **03:15 PM IST** to eliminate overnight decay.
   - Strategy 2 enters overnight asymmetric credit spreads at **03:20 PM IST** and squares off at **09:20 AM IST** the following morning.
5. **Telemetry & Monitoring**:
   - Open positions, realized PnL, and win rates are saved to `state/live_paper_session.json`.
   - FastAPI server streams state to live browser dashboard at `http://127.0.0.1:8000`.

---

## 3. Identification of Weaknesses & Suspected Biases

| Vulnerability / Bias | Location | Description & Empirical Risk | Mitigation / Solution |
| :--- | :--- | :--- | :--- |
| **Synthetic Option Approximations** | `src/strategies/*.py` | Options backtests prior to 2024 approximated option premiums using Black-Scholes analytical formulas rather than exact historical tick-level option chains. | Real NSE F&O UDiFF Bhavcopies integrated; strategies tagged as `SIMULATION ONLY / UNVERIFIED` until full tick chains are ingested. |
| **Intrabar Ambiguity** | `src/strategies/golden_trend_buyer.py` | If a single daily candle's range touches both take-profit (+50%) and stop-loss (-15%), naive backtests assume the target was hit first (optimistic bias). | `IntrabarSimulator` built with `CONSERVATIVE` (stop-loss assumed hit first) as mandatory default. |
| **Multiple Testing Selection Bias** | Repository-wide | Testing 19 strategies across 192 parameter variations creates high likelihood of discovering lucky overfitted strategies. | Bailey & López de Prado (2014) Deflated Sharpe Ratio (DSR) & Combinatorial Purged Cross-Validation (CPCV). |
| **Survivorship Bias** | Cash Equities | Constructing historical stock universes from today's NIFTY 50 members ignores past delistings and index exclusions. | Point-in-time historical universe manager (`nifty50_membership_history.csv`) implemented. |
| **Regulatory Cost Discontinuity** | `src/backtesting/cost_model.py` | Union Budget 2024 hiked STT on options from 0.0625% to 0.100% on Oct 1, 2024. Static cost models understate recent friction. | Versioned cost schedules (`SCHEDULE_PRE_OCT_2024` vs `SCHEDULE_POST_OCT_2024`) with penny-matched statutory rates. |

---

## 4. Priority of Systematic Fixes

1. **Phase 1 (Data Lineage)**: Implement immutable dataset tracking with SHA-256 hash manifests and clear segregation of EOD vs tick data.
2. **Phase 2 (Options Realism)**: Benchmark options pricing against real downloaded NSE UDiFF Bhavcopy contracts.
3. **Phase 3 (No-Lookahead Proof)**: Enforce PIT metadata (`event_time`, `available_at`, `used_at`) and automated future mutation tests.
4. **Phase 4 (Execution Realism & Intrabar)**: Mandate conservative intrabar resolution across all option buyer strategies.
5. **Phase 5 (Statistical Robustness)**: Run CPCV and adversarial falsification (10x slippage stress and 500-run Monte Carlo controls).
6. **Phase 6 (Graduation Classification)**: Tag each strategy into objective institutional tiers (`FAILED`, `FRAGILE`, `PROMISING`, `ROBUST`, `PAPER_READY`, `LIVE_ELIGIBLE`).

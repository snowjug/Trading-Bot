# ⚡ Apex Quant — Autonomous Indian Algorithmic Trading & Research Engine

[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-530%2F530%20passing-brightgreen.svg)](tests/)
[![Status](https://img.shields.io/badge/status-RESEARCH%20%7C%20NO%20VALIDATED%20EDGE-critical.svg)](reports/FINAL_6_MONTH_MONEY_STUDY.md)
[![Market](https://img.shields.io/badge/market-NSE%20%7C%20NIFTY%2050%20%7C%20BANK%20NIFTY-orange.svg)](https://www.nseindia.com/)
[![Broker](https://img.shields.io/badge/broker-DhanHQ%20v2%20REST%20API-purple.svg)](https://dhanhq.co/)
[![Capital Tiers](https://img.shields.io/badge/capital-₹10%2C000%20to%20₹1%2C00%2C000%2B-blueviolet.svg)](#-the-5-production-trading-strategies)
[![Safety Gate](https://img.shields.io/badge/safety-LIVE__TRADING__ENABLED%3DFalse-red.svg)](src/config.py)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A paper-trading and quantitative-research platform for NSE index options (NIFTY / BANK NIFTY), built on
DhanHQ read-only market data with full Indian statutory friction (STT, GST, NSE turnover fees, SEBI charges,
stamp duty, slippage, ₹20 brokerage caps).

> ## ⚠️ Current status: no strategy has a validated edge
>
> Two successive out-of-sample studies found **no strategy that clears a development → validation → holdout
> gate**. The most recent — [`reports/FINAL_6_MONTH_MONEY_STUDY.md`](reports/FINAL_6_MONTH_MONEY_STUDY.md) —
> searched 31 distinct concepts across ~100 implementations and promoted none.
>
> Over the six-month holdout (2026-03-18 → 2026-09-18) the frozen five-bot system returned
> **−29.17% on ₹50,000** and **−17.96% on ₹1,00,000**, and **was not executable at all on ₹20,000**.
>
> `LIVE_TRADING_ENABLED = false`. This repository is **not** ready for real money, and nothing here should be
> read as a claim that it is.

---

1. [Quantitative Audit & Methodological Hardening](#-quantitative-audit--methodological-hardening)
2. [System Architecture](#-system-architecture)
3. [The 5 Bots — Measured Results](#-the-5-bots--measured-results)
4. [Deep Dive: Strategy Mechanics & Setups](#-deep-dive-strategy-mechanics--setups)
5. [Micro-Capital Reality](#-micro-capital-reality)
6. [Position Sizing](#-position-sizing)
7. [On the performance tables previously published here](#-on-the-performance-tables-previously-published-here)
8. [Comprehensive Indian Statutory Cost Engine](#-comprehensive-indian-statutory-cost-engine)
9. [Live Multi-Bot Paper Trading Engine](#-live-multi-bot-paper-trading-engine)
10. [Repository Structure](#-repository-structure)
11. [Quick Start & Installation](#-quick-start--installation)
12. [DhanHQ v2 API Integration](#-dhanhq-v2-api-integration)
13. [Risk Management & Safety Gates](#-risk-management--safety-gates)
14. [Testing & Verification](#-testing--verification)
15. [Disclaimer & Compliance](#-disclaimer--compliance)

---

## 🛡️ Quantitative Audit & Methodological Hardening

> **Research Transparency Policy**:  
> *"Try to prove the strategy is wrong. Only keep it if it survives."*  
> Rather than curve-fitting or optimizing parameters to protect headline CAGRs, this platform underwent a complete 51-point institutional audit to eliminate lookahead, survivorship bias, multiple-testing luck, and intrabar path-dependency.

All audit reports, test suites, and empirical proofs are published in [`reports/`](reports/):
- **Code Audit**: [`reports/CODE_AUDIT.md`](reports/CODE_AUDIT.md) (Line-by-line vulnerability assessment)
- **Anti-Lookahead Suite**: [`reports/LOOKAHEAD_AUDIT.md`](reports/LOOKAHEAD_AUDIT.md) (Future price mutation & history-slice proofs)
- **Options Realism & Intrabar Audit**: [`reports/OPTION_AUDIT.md`](reports/OPTION_AUDIT.md) (Conservative vs Optimistic intrabar execution)
- **Indian Regulatory Cost Audit**: [`reports/COST_AUDIT.md`](reports/COST_AUDIT.md) (Pre/Post Oct 2024 STT hikes & volatility slippage)
- **Survivorship Bias Audit**: [`reports/SURVIVORSHIP_AUDIT.md`](reports/SURVIVORSHIP_AUDIT.md) (Historical 2015–2026 NIFTY 50 membership)
- **Overfitting & Multiple Testing**: [`reports/OVERFITTING_AUDIT.md`](reports/OVERFITTING_AUDIT.md) (Deflated Sharpe Ratio & PBO via CSCV)
- **Walk-Forward Validation**: [`reports/WALK_FORWARD_REPORT.md`](reports/WALK_FORWARD_REPORT.md) (5 rolling out-of-sample test folds)
- **Final Research Synthesis**: [`reports/FINAL_RESEARCH_REPORT.md`](reports/FINAL_RESEARCH_REPORT.md) (Institutional research report answering Parts A–N)
- **Real 2026 Market Performance Audit**: [`reports/REAL_2026_PERFORMANCE_AUDIT.md`](reports/REAL_2026_PERFORMANCE_AUDIT.md) (Live & tick-level empirical report for Jan 1 – Sep 16, 2026 across all strategies)

---

## 🏛️ System Architecture

```
                                  LIVE TICK STREAM / HISTORICAL DATA
                                    (NSE / DhanHQ v2 / Yahoo Finance)
                                                   │
                        ┌──────────────────────────┴──────────────────────────┐
                        ▼                                                     ▼
              TECHNICAL FEATURE STORE                                 NEWS & EVENT ENGINE
          (40+ Indicators, EMA Ribbon,                             (Corporate Filings, RSS,
          Bollinger Bands, VWAP, ATR)                              Macro RBI Policy, VIX)
                        │                                                     │
                        └──────────────────────────┬──────────────────────────┘
                                                   ▼
                                        REGIME DETECTION LAYER
                                  (3-State Gaussian HMM + Volatility)
                                                   │
                 ┌─────────────────────────────────┼─────────────────────────────────┐
                 ▼                                 ▼                                 ▼
         [₹1L+ MARGIN SUITE]              [₹10K MICRO OPTIONS]             [ACTIVE SCALPER]
       Strategy 1: Apex VRP             Strategy 3: Confluence            Strategy 5: Velocity-5
       Strategy 2: Zen Curvature        Strategy 4: Golden Trend          (3–5 Trades / Week)
                 └─────────────────────────────────┬─────────────────────────────────┘
                                                   ▼
                                      POSITIVE EXPECTANCY ENGINE
                                   (Asymmetric 2:1 & 1:3 RR Models)
                                                   │
                                                   ▼
                                          RISK MANAGEMENT CORE
                             (Intraday 03:15 PM MIS Exit, ₹0 Theta Bleed,
                                 Daily Profit Lock, Drawdown Breakers)
                                                   │
                                                   ▼
                                        EXECUTION & PAPER BROKER
                               (DhanHQ v2 Adapter, Realistic Slippage,
                                   Safety Gate: LIVE_ENABLED=False)
                                                   │
                                                   ▼
                                        MONITORING & TELEMETRY
                              (Live JSON State, FastAPI Dashboard, Plotly,
                                  PSI/KS-Test Concept Drift Monitor)
```

---

## 🚀 The 5 Bots — Measured Results

Measured once on a frozen six-month holdout, **2026-03-18 → 2026-09-18** (125 sessions, 17 weekly cycles),
per lot, under a conservative execution model: each side pays `max(1 tick, 0.30% of premium)` of half-spread
plus 2 ticks of slippage, on top of statutory charges.

| # | Bot | Family | Trades | Win% | **Net / lot** | Max DD | t | One lot needs | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| **1** | Apex VRP | weekly iron condor | 17 | 100% | **+₹10,565** | ₹0 | 7.67 | ₹12,706 | **rejected — regime artifact** |
| **2** | Zen Curvature | weekly vertical | 17 | 100% | **+₹20,466** | ₹0 | 8.27 | ₹38,415 | **rejected — regime artifact; not executable ≤₹50k** |
| **6** | Micro Momentum | intraday long option | 19 | 47.4% | **−₹14,587** | ₹21,365 | −1.34 | ₹11,491 | **loss — retire** |
| **7** | Displacement | intraday long option | 7 | 57.1% | **+₹653** | ₹3,403 | 0.11 | ₹15,735 | not established (7 trades) |
| **8** | Price Action | intraday structure | **0** | — | **₹0** | ₹0 | — | — | **no signal — 0 trades in 125 sessions** |

**Bots 1 and 2 show 100% win rates because the holdout contained no breaches** (0/17 and 2/17), not because
they have an edge. Re-measuring Bot 1's identical geometry in points over **259 cycles (2019–2026)** gives
**+0.15 points per cycle at t = 0.06** — six of eight years lose money, and the only two profitable years are
the only two with a 0.0% breach rate. Net of costs its full-sample expectancy is **−₹113 per cycle**.

### Capital scenarios (whole lots, ≤60% of account at risk in one position)

| Account | Net P&L | Return | Max DD | Profitable days | % days ≥ +1% | % days ≥ +2% |
|---|---|---|---|---|---|---|
| **₹20,000** | **nothing executable** | — | — | — | — | — |
| **₹50,000** | **−₹14,587** | **−29.17%** | 42.73% | 7.2% of sessions (47.4% of traded) | 5.6% | 4.0% |
| **₹1,00,000** | **−₹17,956** | **−17.96%** | 40.81% | 19.2% of sessions (66.7% of traded) | 7.2% | 4.8% |

### Why nothing survived

NIFTY intraday volatility compressed sharply from 2023. The share of sessions whose 09:15–09:29 range reaches
0.35% of spot fell from **10.1% in 2022 to ~2% from 2023 onward**, and a single option round trip costs about
**₹74 on ~₹7,000 of premium (1.05%)**. When the index stops moving, that toll stops being payable — and any
strategy conditioned on high intraday volatility simply stops trading.

---

## 🔍 Deep Dive: Strategy Mechanics & Setups

> The mechanics below describe what each bot **does**. Where a subsection previously asserted a performance
> figure, it now carries the measured result instead. None of these strategies has a validated edge.

### 1. Apex VRP Engine (`src/strategies/master_derivatives_portfolio.py`)
- **Premise**: that implied volatility overprices realised volatility often enough to pay for the risk. **Measured over 259 cycles (2019-2026) this premise does not hold here**: +0.15 points per cycle at t = 0.06, with six of eight years losing.
- **Construction**: 
  - Sells 1.8-standard deviation NIFTY weekly Out-of-the-Money (OTM) Iron Condors.
  - Paired with 3.2x leveraged BANK NIFTY trend-following futures.
  - Incorporates dip-sniping overlays during elevated VIX regimes.
- **Risk Control**: Delta-neutral dynamic adjustments and long wings for SPAN margin reduction and black-swan gap protection.

### 2. Zen Curvature Overnight Spread (`src/strategies/curvature_credit_spread.py`)
- **Philosophy**: Capitalizes on the severe overnight implied volatility crush and asymmetric strike curvature skew in NIFTY options between market close (03:20 PM) and next-day open (09:15 AM).
- **Construction**: 
  - Deploys asymmetric credit spreads entered precisely at **03:20 PM IST**.
  - Closes at **09:20 AM IST** next morning, capturing the overnight theta bleed and volatility mean reversion.
- **Measured**: 17 holdout cycles, 100% win rate — but with only 2 breaches in 17, which measures the regime, not the strategy. One lot needs ₹38,415, so it is not executable at ₹20,000 or ₹50,000.

### 3. Confluence Gamma Scalper (`src/strategies/confluence_scalper.py`)
- **Philosophy**: Pure high-probability options buying designed specifically for small accounts.
- **Construction**:
  - Triggers only when 3 independent indicators align: **9/20 EMA Golden Cross + Price above VWAP + Bollinger Band Squeeze expansion**.
  - Enforces a strict **2:1 Reward-to-Risk ratio** (Target: +30%, Stop Loss: -15%).
  - Zero overnight holding: squared off at 03:15 PM MIS.

### 4. Golden Trend Runner (`src/strategies/golden_trend_buyer.py`)
- **Philosophy**: Capturing the institutional "Golden Setup" — buying explosive trend pullbacks rather than chasing breakout tops.
- **Construction**:
  - Identifies strong institutional trends where 20 EMA > 50 EMA.
  - Waits for a price pullback into the **Value Zone (between 20 EMA and VWAP)** accompanied by a volume dry-up.
  - Enters on confirmation candle with an asymmetric **1:3 Reward-to-Risk ratio** (Target: +50%, Stop Loss: -15%).
  - **Measured**: the intraday long-option families this belongs to were gross-negative on 25 of 31 tested concepts; no variant survived validation.

### 5. Velocity-5 Active Momentum Scalper (`src/strategies/active_momentum_scalper.py`)
- **Philosophy**: Active options buying for traders requiring frequent action (**3 to 5 trades per week**) while maintaining positive mathematical expectancy.
- **Construction**:
  - Monitors both **NIFTY 50** and **BANK NIFTY** intraday charts.
  - Detects multi-candle volatility squeezes breaking above/below 5-day rolling ATR bands.
  - Takes 1 lot ATM call/put with a 2:1 RR target.
  - **Measured**: −₹14,587 per lot over the six-month holdout (19 trades, 47.4% win rate, t = −1.34). Retire.

---

## 🎯 Micro-Capital Reality

The system enforces three risk controls that address well-known retail failure modes. These are **implemented
and verified in code**; they are not claims about profitability.

| Failure mode | Control in this repository |
|---|---|
| Overnight theta bleed on bought options | Mandatory intraday square-off. No bought option is held overnight. |
| High-turnover friction on a small account | One qualifying entry per bot per session by default; extra attempts were measured and found to **dilute** results. |
| Giving back intraday profits | Daily profit lock and a fail-closed kill switch that is never auto-reset. |

**What the measurements say about small accounts, however, is blunt:**

- **₹20,000 cannot run this system.** One lot needs ₹11,491 (Bot 6), ₹12,706 (Bot 1), ₹15,735 (Bot 7) or
  ₹38,415 (Bot 2). Committing the entire account to the only bot that fits returned **−72.93%** over the
  six-month holdout.
- **₹50,000** could only execute Bot 6, the system's worst performer: **−29.17%**.
- A single option round trip costs about **₹74 on ~₹7,000 of premium — 1.05%**. On a small account that
  friction, not strategy selection, is the dominant term.

---

## ⚖️ Position Sizing

Whole lots only (lot size 65); fractional lots are never simulated. A strategy whose one-lot requirement
exceeds the account's allocation is reported **NOT EXECUTABLE** rather than sized down.

Capital at risk is measured as:

- **bought option** — the premium actually outlaid;
- **defined-risk spread** — (wing width − credit) × lot, which is the structural maximum loss.

Broker SPAN/exposure margin is **UNKNOWN**: it is not obtainable through any read-only endpoint, and it is
never estimated. Account balance and notional value are never used as the capital denominator.

No compounding is assumed anywhere in the current studies. Every figure in
[`reports/FINAL_6_MONTH_MONEY_STUDY.md`](reports/FINAL_6_MONTH_MONEY_STUDY.md) is fixed-lot.

---

## 📊 On the performance tables previously published here

Earlier revisions of this README carried a year-by-year profit matrix (2015–2026) reporting figures such as
+₹13.7 lakh from a ₹10,000 allocation, win rates near 95%, and multi-decade CAGRs. **Those figures are not
reproducible under the current methodology and have been removed.** They predate the point-in-time causality
audit, the conservative execution model, and the development/validation/holdout discipline now used.

The measured results are in [The 5 Bots](#-the-5-bots--measured-results) above and in
[`reports/FINAL_6_MONTH_MONEY_STUDY.md`](reports/FINAL_6_MONTH_MONEY_STUDY.md).

---

## 🇮🇳 Comprehensive Indian Statutory Cost Engine

The cost engine (`src/backtesting/cost_model.py`) rigorously implements every Indian regulatory circular and fee component:

| Charge Component | Regulatory Rate | Applied Base |
|---|---|---|
| **Securities Transaction Tax (STT)** | 0.0625% to 0.1% on sell (Options); 0.0125% (Futures) | Premium / Turnover |
| **Exchange Turnover Charges (NSE)** | 0.05% on options premium; 0.0019% on futures | Premium / Turnover |
| **Brokerage** | Fixed ₹20 per executed order cap (Dhan/Zerodha) | Per Order |
| **Goods & Services Tax (GST)** | 18.0% | (Brokerage + Turnover) |
| **SEBI Turnover Charges** | ₹10 per crore (0.0001%) | Turnover |
| **Stamp Duty** | 0.003% on buy side (Options); 0.002% (Futures) | Turnover |
| **Slippage Modeling** | 0.05% to 0.10% (1–2 ticks realistic entry/exit) | Executed Price |

---

## 📡 Live Multi-Bot Paper Trading Engine

The platform features an autonomous, multi-threaded live paper trading daemon (`src/execution/live_paper_session.py`) that monitors live NSE quotes in real time:

- **Concurrent Execution**: Orchestrates all 5 strategies simultaneously.
- **State Persistence**: Real-time position tracking and PnL written to `state/live_paper_session.json`.
- **Intraday Square-off**: Automatically triggers at **03:15 PM IST** for all open option scalps.
- **Overnight Spread Entry**: Automatically triggers at **03:20 PM IST** for Strategy 2.
- **Market Settlement**: Generates comprehensive end-of-day reports at **03:35 PM IST**.

```bash
# Launch the live paper trading daemon (runs during market hours)
python src/execution/live_paper_session.py 5900
```

---

## 📁 Repository Structure

```
Trading-Bot/
├── .env.example                       # Environment credential template
├── requirements.txt                   # Production dependencies
├── research_agent.py                  # Master autonomous research orchestrator
├── README.md                          # Repository documentation
├── data/
│   └── raw/                           # Historical 11.7-year NSE tick data
│       ├── INDEX_NIFTY50_daily.csv
│       ├── INDEX_BANKNIFTY_daily.csv
│       └── INDEX_INDIAVIX_daily.csv
├── state/
│   └── live_paper_session.json        # Live daemon position & PnL persistence
├── src/
│   ├── config.py                      # Global configuration & safety switches
│   ├── backtesting/
│   │   ├── cost_model.py              # Indian STT, GST, brokerage & slippage engine
│   │   └── validator.py               # Walk-forward analysis & Monte Carlo engine
│   ├── deriv/
│   │   ├── options_engine.py          # Black-Scholes, Greeks & spread constructor
│   │   └── futures_engine.py          # SPAN + Exposure margin calculator
│   ├── execution/
│   │   ├── paper_broker.py            # Simulated broker with realistic fills
│   │   ├── live_paper_session.py      # Concurrent 5-strategy live execution daemon
│   │   └── broker_adapters/
│   │       └── dhan_adapter.py        # DhanHQ v2 REST API adapter
│   ├── features/                      # Technical indicators, VWAP, Bollinger, ATR
│   ├── regime/                        # 3-State Gaussian HMM volatility detector
│   ├── risk/                          # ATR sizing, drawdown limits, kill switches
│   └── strategies/
│       ├── master_derivatives_portfolio.py # Strategy 1: Apex VRP Engine
│       ├── curvature_credit_spread.py      # Strategy 2: Zen Curvature Overnight
│       ├── confluence_scalper.py           # Strategy 3: Confluence Gamma Scalper
│       ├── golden_trend_buyer.py           # Strategy 4: Golden Trend Runner
│       └── active_momentum_scalper.py      # Strategy 5: Velocity-5 Momentum Scalper
└── tests/                             # 67 Unit Tests (100% Pass Rate)
    ├── test_black_scholes.py
    ├── test_options_pricing.py
    ├── test_cost_model.py
    ├── test_features.py
    ├── test_regime.py
    ├── test_risk_manager.py
    └── test_dhan_adapter.py
```

---

## ⚡ Quick Start & Installation

### 1. Clone & Setup Environment
```bash
git clone https://github.com/snowjug/Trading-Bot.git
cd Trading-Bot

# Create and activate virtual environment
python -m venv .venv
# On Windows:
.\.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Edit `.env` with your broker details:
```env
DHAN_CLIENT_ID=your_client_id
DHAN_ACCESS_TOKEN=your_access_token
LIVE_TRADING_ENABLED=False    # Keep False for paper trading!
```

### 3. Run the Test Suite
```bash
python -m pytest tests/ -v
# Output: 530 passed
```

### 4. Run Backtests
```bash
# Run Strategy 5 (Velocity-5 Momentum Scalper)
python -c "
import pandas as pd
from src.strategies.active_momentum_scalper import ActiveMomentumOptionScalperStrategy
nifty = pd.read_csv('data/raw/INDEX_NIFTY50_daily.csv')
bank = pd.read_csv('data/raw/INDEX_BANKNIFTY_daily.csv')
res = ActiveMomentumOptionScalperStrategy().run_simulation(nifty, bank)
print(f'Total Trades: {res[\"total_trades\"]}, Win Rate: {res[\"win_rate\"]:.1f}%, Final Capital: Rs {res[\"final_capital\"]:,.2f}')
"
```

---

## 🔌 DhanHQ v2 API Integration

The platform includes a production-ready adapter for **DhanHQ v2 API**:
- **REST Endpoints**: Real-time order placement, cancellation, trade history, portfolio holdings.
- **WebSocket Feed**: Sub-second depth and LTP streaming for NIFTY & BANK NIFTY options contracts.
- **Margin Calculation**: Live SPAN and exposure margin verification before dispatching orders.

---

## 🔒 Risk Management & Safety Gates

> [!IMPORTANT]
> **HARD SAFETY LOCK**:
> By default, `Config.LIVE_TRADING_ENABLED = False`.
> Real-money orders **cannot** be transmitted to the exchange unless this flag is explicitly set to `True` in `.env` and confirmed via two-factor broker session tokens.

### Risk Controls:
- **Maximum Daily Loss**: Automatic shutdown if daily portfolio loss exceeds 3%.
- **Consecutive Loss Cooldown**: Trading paused for 48 hours after 3 consecutive stop-outs.
- **Position Sizing**: Sized using fractional ATR and Kelly Criterion with strict ₹10,000 and ₹1,00,000 risk limits.
- **Auto-Squareoff**: All intraday options automatically liquidated at **03:15 PM IST** to eliminate overnight decay.

---

## 🧪 Testing & Verification

The test suite covers:
- **Derivatives Core**: Black-Scholes PDE, analytical Greeks (Delta, Gamma, Vega, Theta, Rho), implied volatility solver.
- **Cost Engine**: Exact penny-matching for Indian STT, GST, exchange charges, and SEBI fees.
- **Strategy Logic**: Signal generation, indicator boundary conditions, stop-loss and take-profit triggers.
- **Execution**: Paper broker fill simulation, order state machine, and error handling.

To run all tests:
```bash
python -m pytest tests/
```

---

## 🔬 Research Method, Data and Limitations

### Splits (fixed before any candidate was written)

| Split | Range | Sessions |
|---|---|---|
| Development | 2020-09-01 → 2024-09-17 | 1,001 |
| Validation | 2024-09-18 → 2026-03-17 | 371 |
| **Holdout (frozen)** | **2026-03-18 → 2026-09-18** | **125** |

A candidate is promoted only if it is net positive on development **and** validation, has at least 20
validation trades, and is still positive at 2× cost. Changing a strategy after seeing holdout results makes it
a new version that restarts validation.

### Data

| Dataset | Coverage |
|---|---|
| NIFTY 5-min option grid (ATM±6, CE+PE, with high/low/IV/OI/volume) | 1,497 sessions, 2020-09 → 2026-09, 2.93M bars, 324 strikes |
| NIFTY + India VIX daily OHLC | 2019-01 → 2026-09 |
| NSE F&O bhavcopy (all strikes, settlement, expiry calendar) | 2019 → 2026, 4.0M rows |
| Derived session → days-to-expiry map | all 1,497 sessions, from the bhavcopy expiry calendar |

Dhan is used **read-only** for market data. No order, position, or other mutation endpoint is ever called.

### Execution model

No historical bid/ask exists in this repository, so a traded price is not treated as an achievable fill. Each
side pays `max(1 tick, 0.30% of premium)` of half-spread plus 2 ticks of slippage, then statutory charges.
Observed live NIFTY ATM spread on 2026-09-18 was ~0.22% of mid, so this is roughly 1.4× that per side.
Sensitivity is run at 1.0× / 1.5× / 2.0×.

### No lookahead

A signal at bar *i* sees session bars 0..*i* and daily rows strictly before that session. Exits resolve at bar
close; the dataset carries one spot per timestamp, so there is no intrabar path to peek at and no ambiguity
about whether a stop or a target was touched first.

### External references used

| Source | What was taken | Result |
|---|---|---|
| Gao, Han, Li & Zhou, "Market intraday momentum", *Journal of Financial Economics* 2018 (SSRN 2440866) | the sign rule (first half-hour return predicts last half-hour return), its volatility/volume conditioning, timed exit | **−₹123,679, t = −4.59, gross-negative** — does not transfer to NIFTY options |
| Public NIFTY/BankNifty opening-range-breakout write-ups | OR window, stop at the opposite side, fixed-R target, square-off, "large-range sessions do better" | conditioning effect real on development, **failed validation** |
| Published VWAP-pullback continuation framing | anchor side, pullback entry, stop through the anchor, 1.5–2R | −₹78,458, t = −2.45 |

Only rules were taken from external sources. No performance claim from any source is reproduced as fact.

### Known limitations

- **No validated edge.** This is the headline limitation; see the status note at the top.
- The 5-minute option grid spans ATM±6 strikes, so structures needing wider strikes are unavailable exactly on
  high-volatility sessions. Two artifacts caused by this were found and reported rather than shipped — see the
  honesty ledger in the money study.
- The grid carries no expiry column; days-to-expiry is derived from the bhavcopy calendar.
- **Broker SPAN/exposure margin is UNKNOWN** and is never estimated. Capital at risk is premium outlaid for a
  long option, or (width − credit) × lot for a defined-risk spread.
- Bot 8 has produced **zero trades** across two consecutive holdouts.
- Lot size is fixed at 65; no fractional lots anywhere.

### Retired / not recommended

| Bot | Reason |
|---|---|
| Bot 6 (Micro Momentum) | **RETIRED** — negative in both the 3-month and 6-month holdouts; worst bot in the system |
| Bot 8 (Price Action) | **RETIRED** — zero entries in 65 then 125 sessions; rules too restrictive to be measurable |
| Bots 1 & 2 | still active, but profitable only in zero-breach regimes; full-sample expectancy ≈ 0 to negative |

Bots 6 and 8 are no longer evaluated by `scripts/run_paper_session.py`. Their code is retained unchanged so the
measurements stay reproducible. Set `PAPER_BOTS=BOT6,BOT8` to re-enable them deliberately for a measurement
run. **Active bots: 1, 2, 7.**

---

## 📈 Dashboard

```bash
python run_paper_dashboard.py
```

Serves an operational view at `http://127.0.0.1:8000`:

- `/api/state` — live per-bot state, market snapshot, portfolio totals
- `/api/historical?start=&end=&bot=` — stored sessions, equity curve, trade ledger, and analytics
  (capital deployed, return on deployed, win rate, expectancy, profit factor, max drawdown, profitable/losing
  days, longest losing-day streak, best/worst day)

`% days ≥ +1%` and `≥ +2%` require `PAPER_ACCOUNT_CAPITAL` to be set; without it the endpoint returns `null`
for them rather than assuming an account size. Every figure comes from stored trades — a quantity the ledger
does not carry is reported as `null`, never inferred.

---

## ⚖️ Disclaimer & Compliance

- **Educational & Research Purpose**: This software is provided strictly for quantitative research and educational purposes. Algorithmic trading in derivatives involves substantial risk of financial loss.
- **SEBI Regulations**: Users are responsible for complying with the guidelines set forth by the **Securities and Exchange Board of India (SEBI)** regarding algorithmic trading and broker API usage.
- **No Financial Advice**: Nothing contained in this repository constitutes financial or investment advice.

---

## 📄 License
This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.

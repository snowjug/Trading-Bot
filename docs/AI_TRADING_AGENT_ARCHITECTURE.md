# AI TRADING AGENT — ARCHITECTURE

**Base SHA:** `37412bb` · **Written:** 2026-09-20 · **Mode:** REPLAY (default)
**`LIVE_TRADING_ENABLED`:** `false`, and no code path in this design can change it.

---

## 0. SECURITY PASS — RESULT

Run before any other work, per the directive's Section 0.

| Check | Result |
|---|---|
| `.env` tracked by git? | **No**, and it is covered by `.gitignore:23` |
| Any `.env`/secret/credential file ever committed? | **No** — only `.env.example` |
| JWT-shaped strings in tracked files | 8 hits, **all in binary `.parquet`**; 0 of them decode as a JWT header, so all are false positives from compressed byte sequences |
| JWT-shaped strings in git history | same parquet files only |
| Hardcoded account ID | **FOUND** — `1111273920` in 19 places across 2 test files and 1 report, in a public repository. **Remediated** to the synthetic `1000000000` |
| Tokens in tests | already fake (`"test_token"`) |
| `LIVE_TRADING_ENABLED` at runtime | `False`, asserted |

**Residual risk the user must action:** the access token was pasted into a chat
transcript. It expires 2026-09-21 20:05:59 on its own, but rotating it in the Dhan
console after this session is the clean move. Tokens are never written anywhere but
`.env`, never logged, and never printed by any code added here.

---

## 1. WHAT THIS SYSTEM IS

A deterministic market-state pipeline with a **narrow AI decision seam** and a
**hard risk boundary** the AI cannot cross.

```
  DhanHQ read-only market data  /  historical replay store
                │
                ▼
  ┌─────────────────────────────┐
  │  MARKET-STATE ENGINE        │  deterministic, Python, no LLM
  │  src/market/                │  multi-timeframe OHLC -> MarketState
  └─────────────────────────────┘
                │  MarketState (frozen dataclass, ~60 scalars)
                ▼
  ┌─────────────────────────────┐
  │  CANDIDATE SETUP ENGINE     │  deterministic gate; most bars stop HERE
  │  src/market/setups.py       │  emits 0..n CandidateSetup or nothing
  └─────────────────────────────┘
                │  only if a candidate exists
                ▼
  ┌─────────────────────────────┐
  │  STATE COMPACTOR            │  MarketState -> ~40 line text + state_hash
  │  src/agent/state_compactor  │  raw bars NEVER reach the model
  └─────────────────────────────┘
                │
                ▼
  ┌─────────────────────────────┐
  │  AI TRADING AGENT           │  pluggable `Decider`
  │  src/agent/trading_agent.py │   - HeuristicDecider (no LLM, deterministic)
  │                             │   - LLMDecider (cached by state_hash)
  └─────────────────────────────┘
                │  AgentDecision (schema-validated; invalid => NO TRADE)
                ▼
  ┌─────────────────────────────┐
  │  STRUCTURE RISK BOUNDARY    │  DETERMINISTIC. The AI cannot pass this.
  │  src/risk/structure_risk.py │  wraps the existing src/risk/RiskEngine
  └─────────────────────────────┘
                │  RiskVerdict(approved, lots, reasons)
                ▼
  ┌─────────────────────────────┐
  │  EXECUTION                  │  one canonical path
  │  src/execution/agent_paper_executor.py  (PAPER)
  │  src/execution/dhan_executor.py         (SANDBOX, gated, not enabled)
  └─────────────────────────────┘
                │
                ▼
  POSITION MONITOR ──► deterministic hard exits ──► AI reassessment (event-driven)
```

### The AI seam is deliberately small

The AI receives a compacted state and a list of candidate setups. It returns one
JSON object. It can only ever cause a trade to be **considered**; every monetary and
safety question is answered after it, by code, in `structure_risk.py`.

---

## 2. COMPONENTS RETAINED, ADDED, REPLACED

### Retained unchanged (already audited, already tested)

| Component | Why kept |
|---|---|
| `src/risk/risk_engine.py` | kill switch with persisted state, portfolio drawdown, daily/weekly loss limits, position sizing. This is the monetary authority; the new structure layer delegates to it rather than reimplementing it |
| `src/execution/cost_model.py` | statutory Indian friction (STT side-aware, stamp, GST, exchange, SEBI, brokerage) |
| `src/execution/multileg_paper_broker.py` | per-leg paper fills, `LegSpec`, partial-fill and leg-mismatch handling |
| `src/execution/bot_signals.py` | kept for the legacy bots; **not** used by the agent |
| `src/data/dhan_client.py` | read-only client; order routes hard-blocked inside `_post` |
| `src/journal/trade_logger.py`, `src/accounting/`, `src/portfolio/` | journalling and P&L |
| `src/research/futures_panel.py`, `stock_futures_panel.py`, `zdte_premium.py` | authentic-price research engines from the clean-room cycle |

### Added (new, this build)

| Path | Role |
|---|---|
| `src/market/indicators.py` | EMA/SMA/RSI/ATR/ROC/VWAP/realized-vol — pure functions |
| `src/market/structure.py` | swings, HH/HL/LH/LL, breakout/breakdown/failed-breakout, S/R, opening range |
| `src/market/candles.py` | body/wick geometry as **quantitative features**, not named-pattern magic |
| `src/market/regime.py` | trend/range and volatility-bucket classification |
| `src/market/market_state.py` | `MarketState`, the single canonical multi-timeframe snapshot |
| `src/market/setups.py` | `CandidateSetup` detector — the token-efficiency gate |
| `src/agent/decision_schema.py` | `AgentDecision` + strict validation; invalid ⇒ NO TRADE |
| `src/agent/state_compactor.py` | `MarketState` ⇒ compact text + stable `state_hash` |
| `src/agent/deciders.py` | `HeuristicDecider` (deterministic baseline) and `LLMDecider` (cached) |
| `src/agent/trading_agent.py` | orchestration: state ⇒ candidates ⇒ decision |
| `src/options/chain.py` | authentic chain snapshot, spreads, liquidity screen |
| `src/options/structures.py` | the 8 allowed structures as leg builders; naked short vol **disabled** |
| `src/risk/structure_risk.py` | the deterministic boundary |
| `src/execution/agent_paper_executor.py` | paper execution on the canonical path |
| `src/research/agent_replay.py` | replay engine with decision cache |
| `configs/agent.yaml`, `risk.yaml`, `market.yaml` | all thresholds live here, not in code |

### Replaced / quarantined

| Component | Action |
|---|---|
| `scripts/research/run_canonical_benchmark.py::eval_options_structure_strategy` | **QUARANTINED — its output must not be cited.** It prices nothing: `row.get("atm_straddle", 120.0)` where that column does not exist, so a flat 120.0-point credit was used on all 398 expiry sessions 2019–2026; `credit = 65.0` / `75.0` hardcoded for spreads; `strangle_prem = prem * 0.45` invented; `lot_size = 50` "average"; weekly cycles were `range(0, n-5, 5)`, i.e. every fifth session rather than an expiry cycle; and `costs = 160.0 + gross*0.0015` is not the statutory model its report claims. Measured effect on its headline strategy is in §7 |
| `reports/CANONICAL_STRATEGY_BENCHMARK.md`, `CANONICAL_VALIDATION_RESULTS.md`, `FINAL_HOLDOUT_RESULTS.md`, `FINAL_SURVIVOR_CAPITAL_AUDIT.md` | option rows are **not evidence**; superseded, see §7 |

---

## 3. DATA FLOW AND CAUSALITY

Every `MarketState` carries three timestamps:

```
bar_time            the close of the decision bar
data_available_at   when that bar could first have been observed
source              "DHAN_5M" | "REPLAY_GRID" | "BHAVCOPY"
```

Hard rules, enforced in code and pinned by tests:

1. A state for `bar_time = T` is built only from bars with close `<= T`.
2. `data_available_at >= bar_time`; a decision at `T` may read only states with
   `data_available_at <= T`.
3. Forward columns are never in the state object. `MarketState` has no field whose
   name begins `fwd`, and the replay engine asserts this.
4. Option legs are resolved against contracts listed **on that session**, and a leg
   with no bar or zero volume makes the trade `UNPRICEABLE` — never a modelled fill.
5. Settlement values are used only for positions held to expiry, and only for the
   expiry date itself.

---

## 4. THE RISK BOUNDARY — WHAT THE AI CANNOT DO

`src/risk/structure_risk.py` is deterministic and runs **after** the AI. It rejects,
in this order, before any order is built:

| # | Gate | Source of truth |
|---|---|---|
| 1 | `LIVE_TRADING_ENABLED` is false ⇒ paper/replay only | `src/config.py` |
| 2 | schema-invalid or incomplete `AgentDecision` | `decision_schema.py` |
| 3 | structure not in the allowed set | `configs/risk.yaml` |
| 4 | naked short volatility | disabled by default in `risk.yaml` |
| 5 | stale data (`now - bar_time` over budget) | `market.yaml` |
| 6 | outside the NSE session window | `market.yaml` |
| 7 | leg illiquid: zero volume, or spread over budget | `options/chain.py` |
| 8 | max loss per trade over the account fraction | `RiskEngine` |
| 9 | margin or debit over the deployable fraction | `structure_risk.py` |
| 10 | duplicate or conflicting open position | `portfolio` |
| 11 | daily loss limit, weekly loss limit, drawdown limit, kill switch | `RiskEngine` |
| 12 | expected edge after modelled cost not positive | `structure_risk.py` |

Gate 12 matters as much as the others: a setup the AI likes but whose expected move
does not cover the spread plus statutory friction is rejected as a matter of code.

**The AI has no field in its output schema that can relax any of these.** There is no
"override", no "force", no size field the risk engine honours — the AI proposes a
structure and a direction; `lots` is computed by the risk engine alone.

---

## 5. TOKEN EFFICIENCY

| Mechanism | Effect |
|---|---|
| Candidate gate | the model is called only when a deterministic setup exists. On the 5-minute NIFTY grid that is a small minority of bars |
| Compaction | ~40 lines of text, never bars or datasets |
| `state_hash` cache | identical compacted state ⇒ cached decision, no call |
| Event-driven reassessment | open positions are re-evaluated by the model only on structure change, volatility-regime change, stop/target proximity, or invalidation — not every bar |
| `HeuristicDecider` | replay, benchmarks, and all tests run with **zero** LLM calls |

The deterministic 1-minute risk check never calls the model.

---

## 6. MODES

| Mode | Data | Orders | Default |
|---|---|---|---|
| `REPLAY` | historical store | none | **yes** |
| `PAPER` | live read-only Dhan | simulated, journalled | opt-in |
| `LIVE` | — | **hard disabled** | never |

`LIVE` requires an operator to change the environment outside this codebase. No
module added here writes `LIVE_TRADING_ENABLED`.

---

## 7. WHY THE EXISTING OPTION "SURVIVORS" ARE NOT EVIDENCE

The repository's only DEV→VAL→HOLDOUT survivors came from the quarantined function.
Re-measured with authentic 5-minute traded bars at 09:20, the authentic ATM strike,
the exchange's official settlement, and the authentic monthly lot size — 316 NIFTY
expiry sessions that have both a real quote and a real settlement:

| | mean pts/trade | median | win% | worst |
|---|---|---|---|---|
| **AUTHENTIC** | **+6.80** | +21.08 | 61.7% | −457.9 |
| SYNTHETIC (as shipped) | +13.05 | +37.78 | 65.8% | −460.5 |

The synthetic version overstated the edge by **6.25 points a trade**, about half of
it, from two compounding errors:

- assumed credit 120.00 points against an authentic mean of **106.92**
- used `|close − open|` (mean 106.95) where a straddle's terminal value is
  `|settle − K|` with `K` the ATM **strike** (mean 100.12)

The authentic effect is real and positive in 6 of 7 years (2020 +9.33, 2021 +3.72,
2022 −0.78, 2023 +1.24, 2024 +10.60, 2025 +15.54, 2026 +10.52) — but it is a **naked**
short straddle, so it is outside this agent's allowed structures by policy, and the
prior capital audit already showed it needs ₹310k–425k and skips 105 of 105 trades at
₹20k and ₹50k.

That is the honest starting point: **no validated, capital-feasible option edge
exists in this repository today.** This agent is built to search for one correctly,
not to inherit a claim.

---

## 8. SUCCESS CRITERIA FOR THIS BUILD

Not "the backtest made money". This build is complete when:

1. `MarketState` is causally correct and pinned by lookahead tests
2. decisions are reproducible from `(state_hash, prompt_version, model)`
3. invalid AI output cannot produce an order
4. every risk gate is individually tested
5. paper and replay share one execution path
6. the agent is measured against the six required baselines
7. limitations are stated plainly

Profitability is a later question and will not be claimed before evidence.

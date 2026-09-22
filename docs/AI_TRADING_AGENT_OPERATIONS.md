# AI TRADING AGENT — OPERATIONS

Companion to `AI_TRADING_AGENT_ARCHITECTURE.md`. How to run it, what the numbers mean,
and what will go wrong.

**Current mode: REPLAY. `LIVE_TRADING_ENABLED = false`. No broker order endpoint is
imported anywhere in the agent code path.**

---

## 1. FIRST THING TO RUN

```bash
python scripts/health_check.py
```

Read-only, exits non-zero on any FAIL. It checks, in order of importance:

| Check | Why it is first |
|---|---|
| `LIVE_TRADING_ENABLED` is false | the one invariant everything else assumes |
| `.env` not tracked by git | a token in history cannot be un-leaked |
| credentials present | reported as `len=N`, never as a value |
| every agent module imports | a broken import at 09:15 is not a plan |
| configs parse | all thresholds live in YAML |
| no allowed structure carries undefined risk | asserted against the real builders |
| the AI schema exposes no sizing field | structural, not a convention |
| replay data present | with sizes |

It prints no secret. That is deliberate and tested.

---

## 2. REPLAY

```bash
python scripts/replay_agent.py --start 2024-06-01 --end 2024-09-17 --equity 1500000 \
    --out reports/agent_replay.json
```

Zero model calls: the default decider is `HeuristicDecider`, which is deterministic.
`--decider llm` deliberately raises unless a model callable has been wired in.

Useful flags: `--cost-mult 2` for the cost stress, `--risk-pct 0.05` for the sizing
sensitivity, `--max-bars N` for a quick smoke run.

### Reading the output

The **session accounting** block is the part to read first. Every decision bar lands
in exactly one bucket and the engine asserts the buckets sum to the bars offered:

```
  NO_CANDIDATE              1,685   30.2%   deterministic gate said nothing here
  DECIDER_SKIP              1,569   28.1%   a candidate existed, the decider declined
  RISK_NO_EDGE_AFTER_COST   1,488   26.6%   the edge gate refused it
  POSITION_OPEN               428    7.7%   already in a trade
  ENTERED                      43    0.8%
  ...
  TOTAL                     5,585   offered 5,585   reconciles=True
```

**If `reconciles=False`, stop.** A lost bar means the run is not usable, and the
script says so rather than printing a P&L anyway.

`RISK_*` buckets name the gate that refused, so a run that trades too little or too
much can be diagnosed without a debugger.

### Splits

| Split | Window | Rule |
|---|---|---|
| DEV | 2020–2023 | develop freely |
| VALIDATION | 2024 | promote or reject, one pass |
| **OOS** | 2025–2026 | **frozen.** Run once. No tuning afterwards |

The live decision prompt and every threshold must be frozen before OOS is opened. A
change after seeing OOS makes a new version that restarts validation.

---

## 3. WHAT THE AGENT CURRENTLY DOES, MEASURED

On 2024-06-01 → 2024-09-17, ₹15 lakh equity, 1% risk per trade, deterministic decider:

| | Value |
|---|---|
| bars offered | 5,585 (reconciles exactly) |
| trades | 43 |
| win rate | 23.3% |
| net | **−₹131,883** |
| expectancy | **−₹3,067 / trade** |
| profit factor | 0.067 |
| max drawdown | ₹134,457 (8.96% of equity) |
| longest losing streak | 19 |
| t-stat | **−5.62** |

Baselines on the same window:

| Baseline | Result |
|---|---|
| no trade | 0 — **beats the agent** |
| buy and hold (index, no costs, not directly tradable) | +9.76% |
| EMA 5/31 crossover | −2,451 pts |
| EMA 9/21 crossover | −1,635 pts |
| random entry, 43 longs held 12 bars | +69 / −289 pts (two seeds) |

**The deterministic decider has no edge and is worse than doing nothing.** That is
the honest current state. It is reported, not tuned away.

The mechanical reason, from the per-structure breakdown: the decider's dominant
choice was a LONG_STRADDLE costing ~94–102 points of premium, entered to capture an
intraday move whose average best favourable excursion was **+10.6 points**. Buying a
hundred points of premium to catch ten is not a strategy, and no parameter change
fixes that shape.

---

## 4. TWO BUGS THE REPLAY FOUND, BOTH UNIT ERRORS

Recorded because the numbers above are only meaningful with them fixed, and because
both are the same mistake in different clothes.

### 4.1 Stop declared in index points, compared against premium points

`HeuristicDecider` sets `stop_type="UNDERLYING_STRUCTURE"` with a value of 1.2 × ATR
on the 5-minute bars — about **13 index points**. The exit check compared that number
directly against the position's **premium** P&L. On a 102-point straddle that is a
13% premium stop, so 38 of 55 trades stopped out on noise.

Fixed by `OpenPosition.stop_in_premium_pts`, which converts by declared type and
**refuses to convert** rather than guess when it cannot — a delta-neutral structure
carrying an underlying-distance stop simply gets no stop and is bounded by its max
loss and holding time instead. Exit mix moved from 44 STOP_HIT / 10 MAX_HOLD to
12 / 28.

### 4.2 Expected move measured over a day, used to justify a two-hour trade

`options_vol_setup` reports the **daily** ATR (~250 points) as its expected move.
Against a 94-point straddle that looked like +30 points of edge, so the gate approved
it — but `max_hold_minutes` was 120, so the position could only ever see a fraction of
a daily range. 47 of 66 trades were approved this way.

Fixed by making the horizon explicit. `expected_move_horizon_minutes` is now a
required field on any EXECUTE, and the risk gate scales the move to the actual hold by
`sqrt(hold / horizon)`, never upward. `RISK_NO_EDGE_AFTER_COST` rose from 928 to
1,488 bars and the straddle count fell from 47 to 22.

**Neither change was made to improve a result.** Both were incorrect comparisons
between different units, and the result got *worse* after the first fix.

---

## 5. THE RISK BOUNDARY IN OPERATION

12 gates, in `src/risk/structure_risk.evaluate`, each able to refuse alone. The order
is deliberate: absolute and cheap first.

```
 1 LIVE_DISABLED            7 LEG_UNPRICEABLE / LEG_ILLIQUID / LEG_SPREAD_TOO_WIDE
 2 NO_ENTRY_INTENT          8 NO_EDGE_AFTER_COST
 3 STRUCTURE_NOT_ALLOWED    9 DIRECTION_MISMATCH
 4 UNDEFINED_RISK          10 MAX_OPEN_POSITIONS / MAX_TRADES_PER_DAY / DAILY_LOSS_LIMIT
 5 STALE_DATA              11 RISK_ENGINE_BLOCK / RISK_ENGINE_ERROR
 6 OUT_OF_SESSION / TOO_EARLY / TOO_LATE    12 CAPITAL_INSUFFICIENT  (computes `lots`)
```

Things worth knowing operationally:

- **A broken risk engine fails CLOSED.** An exception from `RiskEngine.can_trade`
  becomes `RISK_ENGINE_ERROR` and refuses the trade. Unknown risk state is not a
  licence to proceed.
- **`lots` is computed only at gate 12**, from equity and the budget. No AI field
  influences it; a test asserts the schema has no such field.
- **STALE_DATA fires before the session gate**, so moving a clock in a test trips
  staleness first. That ordering is correct and is why the session tests widen the
  staleness budget to isolate their own gate.

### The capital reality

NIFTY's lot size rose to 75, so a 200-point defined-risk spread risks about
**₹12,439 per lot**:

| Account | 1% risk budget | Affordable? |
|---|---|---|
| ₹20,000 | ₹200 | no — one lot is 62% of the account |
| ₹50,000 | ₹500 | no |
| ₹1,00,000 | ₹1,000 | no |
| ~₹1,240,000 | ₹12,400 | one lot |

Raising `risk_per_trade_pct` is the only lever, and it is a policy decision with an
obvious consequence. At 5% per trade, ~₹250,000 carries one lot. The engine refuses
below that and states the arithmetic in rupees. This is pinned by a test at all three
of the ₹20k / ₹50k / ₹1L tiers.

---

## 6. COST OF RUNNING THE MODEL

| Mechanism | Effect |
|---|---|
| candidate gate | fires on ~10.8% of 5-minute bars; the other ~89% never reach a model |
| compaction | ~40 lines, capped by a test; no bars, no datasets |
| `state_hash` cache | identical rounded state ⇒ cached decision, no call |
| event-driven reassessment | open positions re-asked only on regime change, vol-regime change, structure change, or stop/target proximity, and never faster than `min_minutes_between_calls` |
| `HeuristicDecider` | replay, benchmarks and all 72 tests run with **zero** calls |

The 1-minute deterministic risk check never calls a model.

Before enabling `--decider llm`: set `agent.llm.max_calls` in `configs/agent.yaml`.
`LLMDecider` stops at that budget and returns NO_TRADE rather than spending past it.

---

## 7. PAPER MODE

`src/execution/agent_paper_executor.py` is the only place an agent order is
constructed, in both REPLAY and PAPER, which is what the parity claim rests on.

It refuses, by raising:

- `LiveTradingRefused` if constructed or called with live trading enabled
- `UnapprovedOrderRefused` if reached with an unapproved verdict or zero lots — that
  is a control-flow bug and must be loud, not silent
- a second position while one is open

An unmarkable position is **recorded, not priced**: equity does not move, the P&L is
left absent with `unresolved_reason`, and the failure stays visible in the journal.

Every order carries `client_order_id`, `strategy_id`, `decision_id` (the state hash),
`prompt_version`, timestamp, and per-leg identity with quantity, reference price and
fill price.

**Before any paper run is treated as evidence:** ≥100 paper trades, or a
statistically meaningful forward sample, using this same code path. There is no
separate backtest-only execution model.

---

## 8. WHAT WILL GO WRONG

| Symptom | Cause | What to do |
|---|---|---|
| `reconciles=False` | a bar was lost | do not use the run; the accounting bug comes first |
| all bars `NO_LOT_SIZE` | `lot_size_calendar.csv` missing the month | rebuild it; a rupee figure without an authentic lot is not a rupee figure |
| everything `RISK_CAPITAL_INSUFFICIENT` | equity too small for one lot | expected at retail capital; see §5 |
| everything `RISK_NO_EDGE_AFTER_COST` | working as designed | check `expected_move_horizon_minutes` is honest before suspecting the gate |
| many `UNPRICEABLE` | strikes outside the vendor's ATM±6 ladder | narrow `width_steps`; the missing sessions are the volatile ones, so never fill them in |
| Dhan 401 `DH-901` | token expired (24h life) | renew in the console, update `.env`. **A 401 is not "no data"** — that confusion has already cost this repo one wrong conclusion |
| `UnapprovedOrderRefused` | a caller ignored `verdict.approved` | a bug in the caller, never a reason to relax the gate |

---

## 9. LIMITATIONS, PLAINLY

1. **No historical bid/ask exists** anywhere in this repository, at any date, for any
   instrument. Replay models execution as traded price ± (0.30%/side + 2 ticks) and
   says so. Live paper uses real top bid/ask, so paper spreads are measured.
2. **The 5-minute option grid is ATM±6** — a vendor ceiling. A structure needing a
   wider strike is UNPRICEABLE, never approximated.
3. **No intraday futures history**: Dhan serves `/charts/intraday` only for currently
   listed contracts in ~90-day windows, and expired contract ids are not in the scrip
   master. UNTESTABLE, not absent.
4. **The agent has no edge yet.** §3 is the measurement. Nothing here is a strategy
   recommendation.
5. **`LLMDecider` has never been run against a real model** in this build. Its
   failure paths are tested with injected fakes; its cost and behaviour in practice
   are unmeasured.
6. **`multileg_paper_broker` and `dhan_contract_resolver`** remain classified UNKNOWN
   from the earlier clean-room audit and are not on the agent path.
7. **No sandbox executor exists.** The architecture leaves a slot behind the same
   `place` signature; nothing fills it, and nothing should be inferred about sandbox
   readiness.

---

## 10. SAFETY INVARIANTS — ALWAYS TRUE

- `LIVE_TRADING_ENABLED = false`, and no module added here writes it
- no AI component can enable live trading, bypass a gate, or set a position size
- no order without an approved deterministic verdict
- no trade on stale, future-dated, or unmarkable data
- no trade on invalid AI output — invalid JSON, a banned structure, a missing stop and
  a thrown exception all resolve to NO_TRADE
- naked short volatility has **no builder**, so it cannot be expressed
- an unknown risk state refuses rather than permits

Verified by `tests/test_agent_safety.py` (61) and
`tests/test_agent_paper_executor.py` (11).

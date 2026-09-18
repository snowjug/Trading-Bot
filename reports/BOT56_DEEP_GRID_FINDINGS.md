# Bots 5 & 6 — real option economics on six years of authentic intraday data

Branch `rebuild/bots-1-5-6-7`. `main` untouched. `LIVE_TRADING_ENABLED = false`.
Read-only Dhan chart endpoints only; no order, position or account endpoint called.

**Bottom line: neither bot has a usable edge. Bot 5 is negative before costs.
Bot 6 is positive before costs (+₹11,109) but negative after them (−₹2,838) —
transaction costs alone consume its entire gross edge. Neither strategy was
modified to reach this conclusion.**

---

## 1. The previous result rested on 10 sessions — and that was a caching artefact

The earlier "real option economics" for these bots used a 10-session cache, giving
n=8 and n=3. That was believed to be the data limit. With the token renewed it was
re-probed:

| Probe | Previous belief | Measured 2026-09-18 |
|---|---|---|
| `/charts/rollingoption` history | 10 sessions | **2020-09 → today (~6 years)** |
| Request window | — | one month; longer returns empty |
| Strike ceiling | ATM±10 | ATM±10 confirmed, stable across 2021/2023/2026 |
| Option side | both per call | CALL → `ce`, PUT → `pe`; two calls needed |

Ingested ATM±6 × CE/PE × 73 months = **1,898 chunks, 2.9M bars, 1,499 sessions,
324 distinct real strikes**, of which 1,495 sessions survive the
regular-session filter — a **150× larger** sample.

The whole ladder is pulled, not just "ATM", because the rolling-ATM series
**re-anchors as spot moves**: one session can contain many different strikes under
a single label. Following that label across bars silently swaps the contract
mid-trade. Stitching by REAL strike gives a per-contract history from which one
fixed contract can be held for the life of a trade.

---

## 2. Before and after

| | Legacy cache (10 sessions) | **Deep grid (1,495 sessions)** |
|---|---|---|
| **Bot 5** | 8 trades, −₹1,292, 37.5% win | **589 trades, −₹89,377, 37.5% win** |
| **Bot 6** | 3 trades, **+₹3,087, 100% win** | **187 trades, −₹2,838, 39.0% win** |

Bot 6's headline "100% win rate" was **three trades**. Bot 5's win rate was
already accurate at 37.5% — only its significance changed.

---

## 3. Bot 5 — Active Momentum (causal provider, unchanged)

| | value |
|---|---|
| trades | 589 over 589 sessions |
| gross | **−₹45,539** |
| costs | −₹43,838 |
| **net** | **−₹89,377** (−₹151.74/trade) |
| win rate | 37.52% |
| exits | STOP 280, EOD 195, TARGET 115 |
| t-stat | **−1.333**, p = 0.183, Bonferroni p = 0.732 |
| OOS 70/30 | IS −₹48,848 / OOS −₹41,159, sign agrees |
| walk-forward | **1/4 folds positive** |
| slippage | LOSS at every level tested |

### The defect is upstream of the options
Diagnostic on the spot path alone, ignoring option pricing entirely:

- the spot moved in the signalled direction on only **43.4%** of trades
- mean directional spot move captured: **−3.87 points**
- target/(target+stop) = 115/395 = **29.1%**, against a 2:1 reward:risk structure
  (0.5 ATR target, 0.25 ATR stop) that needs **33.3%** to break even on spot alone

**Bot 5's breakout signal has no directional edge over 2020–2026.** Options only
amplify a deficit that already exists in the underlying. The earlier positive
result came from same-bar leakage plus a synthetic 0.55-delta P&L model; removing
the leakage removed ~31% of the profit, and removing the synthetic pricing removes
the rest.

### Simulation was verified before this conclusion was drawn
- call P&L vs spot move: correlation **+0.916**
- put P&L vs spot move: correlation **−0.943**
- every entry and exit price traced back to the same fixed strike's own series

---

## 4. Bot 6 — Micro Momentum (PROTECTED BASELINE, frozen, unmodified)

| | value |
|---|---|
| trades | 187 |
| **gross** | **+₹11,109** |
| costs | **−₹13,946** |
| **net** | **−₹2,838** (−₹15.17/trade) |
| win rate | 39.04% |
| exits | EOD 137, STOP 48, **TARGET 3** |
| t-stat | **−0.051**, p = 0.960 |
| OOS 70/30 | IS −₹9,675 / OOS +₹6,208, **signs disagree** |
| walk-forward | 3/4 folds positive, one fold −₹15,653 |
| slippage | LOSS at every level |

### The finding that matters
Bot 6 is the only bot in this repository with a **positive gross edge on authentic
data**. It is nonetheless unprofitable, because **₹13,946 of costs exceed ₹11,109
of gross profit**. Expectancy is −₹15/trade against a ~₹75/trade cost load.

This is a cost problem, not a signal problem — but it is not one that can be fixed
by changing the strategy, and no change was made.

A second observation, reported without acting on it: the target was hit **3 times
in 187 trades**, while 137 exits were EOD. The specified target is effectively
unreachable within a session. Adjusting it would change the strategy, so it is
recorded as a **strategy-owner decision**, not a fix.

### Protected-baseline compliance
No Bot 6 parameter, entry rule, exit rule or threshold was altered. `max_vix` is
still 18.5, `min_data_points` still 35, the signal still comes from the class's own
`generate_signals` with no provider override, and the per-day trade cap is enforced.
Its causal properties (previous-bar indicators, current-bar high/low only) remain
test-pinned. **Bot 6 stays FROZEN.**

---

## 5. Execution model and what remains unverified

- Fills are at the traded price of the 5-minute bar. **There is no bid/ask history
  anywhere in this environment**, so every fill is an approximation and is labelled
  `TRADED_PRICE_NO_BIDASK` on every trade.
- Real fills would be worse by at least the half-spread. Both bots are already
  net-negative at zero extra slippage, so the missing spread can only deepen the
  loss — it cannot rescue either result.
- The contract is fixed at entry and held; no strike substitution occurs.
- **A data defect was found and fixed by these tests.** The feed also carries
  Muhurat (Diwali) trading — four evening-only sessions (2021-11-04, 2022-10-24,
  2023-11-12, 2024-11-01) running 18:00–19:15 with no regular-session bars at all.
  Left in, "entry at the first bar after 09:15" would have picked 18:15 and "exit
  after 15:15" would have picked 18:20, a five-minute hold the strategy never
  intended. Excluding them removed one trade from each bot and changed no
  conclusion: Bot 5 −₹90,007 → −₹89,377, Bot 6 −₹3,467 → −₹2,838.
- Lot size is held at the current 65 for comparability across the sample; NIFTY's
  lot size was not constant over 2020–2026, so these rupee figures compare variants
  rather than reconstruct an account statement.

---

## 6. Verdict

| | Bot 5 | Bot 6 |
|---|---|---|
| Research | causal, unchanged | frozen, unchanged |
| Data | **RESOLVED** — 1,495 sessions | **RESOLVED** — 1,495 sessions |
| Validation | OOS, walk-forward, slippage, Monte Carlo, Bonferroni | same |
| Economics | **authentic** | **authentic** |
| Gross edge | **negative** | **positive (+₹11,109)** |
| Net edge | **−₹89,377** | **−₹2,838** |
| Live parity | provider bound and test-pinned | own signal, test-pinned |
| **Paper readiness** | **NOT READY** | **NOT READY** |

**Bot 5's exact blocker:** the signal itself is directionally wrong — 43.4% correct
against a 33.3% break-even requirement that it fails to meet even before costs.
This is not a data problem; more data would not change it.

**Bot 6's exact blocker:** the gross edge (+₹11,109 over 187 trades, ≈₹59/trade) is
smaller than the round-trip cost load (≈₹75/trade). It needs either a materially
larger edge per trade or a materially lower cost base; neither is achievable by
tuning, and no tuning was attempted.

Neither bot is claimed profitable. Neither is ready for money.

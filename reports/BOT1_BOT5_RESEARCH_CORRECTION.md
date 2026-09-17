# Bot 1 & Bot 5 — Research Correction

Branch: `research/bot1-bot5-correction` (baseline `26c6711`). `main` untouched.
`LIVE_TRADING_ENABLED = false`. Neither bot is enabled for live/paper trading.

---

## BOT 1 — STOPPED AT STEP 3

### Specification completeness (from code/docs only)

| Item | Status | Evidence |
|---|---|---|
| Underlying | IMPLIED (NIFTY by name) | validated result is on **BAJFINANCE** |
| Entry time | **MISSING** | no timestamp anywhere |
| Entry information timing | IMPLIED completed daily bar | `options_theta.py:66-67` |
| Expiry | IMPLIED weekly (5-bar stride) | `options_theta.py:123` |
| Short call / put strike | EXPLICIT | `spot ± 1.8 × exp_move`, lines 126-129 |
| Long call / put wing | **MISSING from active path** | `wing_sd` never consumed |
| Strike methodology | EXPLICIT | `exp_move = close × vix/100 × sqrt(5/365)` |
| Position size | EXPLICIT but fabricated basis | `capital×0.65 / 55000` |
| Entry / exit pricing | **MISSING** | fixed `2500×(1.5/otm_sd)` credit |
| Holding period | IMPLIED 5 bars | `df.iloc[i+1:i+6]` |
| Stops / target / adjustments / EOD | **MISSING** | zero occurrences in file |
| Margin | **NOT VERIFIED** | `55000.0` hardcoded, no source |
| Costs | EXPLICIT | `lots × 140.0` |

### Four-leg verification — FAILS

The active research path builds **two** strikes. `wing_sd=2.4` is declared and
reported by `get_parameters()` but never consumed by signal generation or the
simulator.

**Research is a short strangle, not an Iron Condor.** It is not renamed.

A genuine four-leg Black-Scholes condor **does** exist —
`OptionsStructure.simulate_iron_condor` (`src/deriv/options_engine.py:101`) with
`long_call`/`long_put` at `wing_sd`, per-leg BS pricing and
`max_loss = wing_width − net_credit`. It is **orphaned**: called only by
`tests/test_derivatives_engine.py`. This corrects an earlier audit claim that the
wings were never implemented at all.

`simulate_weekly_condors` is **never called anywhere** in the repository.

### Historical data — INSUFFICIENT (the STOP)

Requirement: ~40+ weekly cycles × 4 legs priced at entry and exit. With
`exp_move ≈ 359`, shorts sit ≈ ATM±13 strikes and wings ≈ ATM±17.

| Source | Coverage | Verdict |
|---|---|---|
| Full option chains (bhavcopy) | **4 days** (03-19, 06-18, 08-27, 09-15), 133-164 strikes | insufficient |
| Normalised chain snapshots | **1 day** (2026-09-17) | insufficient |
| Rolling intraday options | 2026-09-01..09-15, strikes **ATM to ATM±3 only** | wrong strikes |
| IV / OI / per-leg bid-ask history | absent | missing |

**Bot 1 implementation STOPPED.** Two independent blockers: the strategy is
underspecified *and* the data to validate a condor does not exist.

### Contaminated evidence — preserved, labelled

The only reported Bot 1 result in the repository is
`nifty_weekly_iron_condor_BAJFINANCE` (`reports/FINAL_REPORT.md:34`): a
**cash-equity** backtest of a VIX/RSI regime flag on a single stock via
`research_agent.py:294-313` → `BacktestEngine`. No options, no strikes, no legs.
Not deleted; labelled contaminated.

In fairness: the equity engine is correctly lagged (`engine.py:159-161`,
`signal = prev["signal"]`, execute at `curr["open"]`), so Bot 1 has **no
lookahead defect** — its problem is the wrong instrument entirely.

---

## BOT 5 — CORRECTED

### Same-bar leakage map

| Field | Original | Known during bar i? | Verdict |
|---|---|---|---|
| `prev["close"] > prev["ema_9"]` | prev | yes | causal |
| `row["open"]` | current open | yes (09:15) | causal |
| `row["high"] > prev["high"]×(1+buf)` | current | yes — live crossing | causal |
| **`row["ema_20"]`** | current | **no** (needs today's close) | **LEAK** |
| **`row["rsi_14"]`** | current | **no** | **LEAK** |
| **`row["atr_14"]`** (sizing) | current | **no** | **LEAK** |
| intrabar high/low for exit | current | yes — position already open | causal |

### Correction and its justification

Implemented additively in `src/research/bot5_point_in_time.py`; the original is
untouched so the contaminated result stays reproducible.

* `ema_20` → `prev` — **restores the strategy's own documentation**: *"Today's
  Open > 20 EMA"*. At today's open the only 20-EMA in existence is the prior
  close's. (Justification A: existing explicit specification.)
* `rsi_14` → `prev` — bar unspecified in the doc; prev is the only causal option.
  (Justification B: leakage removal.)
* `atr_14` → `prev` — target/stop are sized at entry. (Justification B.)

Deliberately unchanged: the breakout trigger stays on the current bar (a live
crossing event), the strategy remains intraday per docstring rule 4, and **no
parameter, threshold, buffer, multiple or cost was altered**.

### Leakage proof

Moving bar i's close to the opposite end of its own high/low range (open/high/low
untouched, so the breakout cannot move):

| Implementation | Own-bar signals flipped by own close |
|---|---|
| Original | **17 / 393 (4.3%)** |
| Point-in-time | **0 / 393 (0.0%)** |

Future-bar mutation: both pass.

### Original vs corrected (NIFTY + BANKNIFTY, 2025-01-01 -> 2026-09-16)

| Metric | ORIGINAL (leaky) | POINT-IN-TIME | Delta |
|---|---|---|---|
| Trades | 299 | 283 | −16 |
| Win rate | 61.20% | 54.77% | **−6.43 pp** |
| Net profit | 251,818 | 173,029 | **−78,789 (−31.3%)** |
| Max drawdown | 14.35% | **22.35%** | **+8.00 pp** |
| Trades/week | 3.56 | 3.37 | −0.19 |

**Removing the leakage removes ~31% of the profit and worsens drawdown by 8
points.** That is the expected signature of same-bar leakage, reported honestly.

### Validation (no tuning, no period selection)

* **OOS** (a-priori 70/30 split at 2026-03-11): IS 133,544 -> 79,806; OOS 59,891
  -> 43,145. The corrected version degrades in both, consistently.
* **Cost sensitivity**: net 173,029 / 160,294 / 147,559 at ₹45 / ₹90 / ₹135
  friction; trade count unchanged, so the result is not friction-driven.
* **Placebo** (resampled P&L pool, 20 draws): real 173,029 vs placebo mean
  158,152 (sd 38,753). The real result is **within one standard deviation** —
  this control constrains sequencing only and provides **no evidence of edge**.

### Critical caveat

P&L remains a **spot-delta proxy**, inherited unchanged: flat ₹100 premium, fixed
0.55 delta, no strike, no expiry, no bid/ask (`pricing_basis` is recorded on every
trade). Absolute figures — ₹10,000 -> ₹183,029 in 20 months — are **not credible
as option P&L** and must not be read as a performance claim.

---

## Parity assessment

| | **Bot 1** | **Bot 5** |
|---|---|---|
| Research signal | strangle, fixed credit | causal breakout |
| Live signal | `generate_signals` regime flag | `generate_signals` (**still leaky**) |
| Feature timing | completed bar | live uses the leaky variant |
| Contract selection | **unspecified** | ATM proxy vs live ATM |
| Entry / Exit | **unspecified** | intraday vs live % rules |
| Risk / Costs / EOD | fabricated / unspecified | proxy vs live cost model |
| **Parity** | **FAIL** | **FAIL** |

Both **fail closed**. `src/execution/` is untouched and both remain gated.

---

## Unresolved specification gaps — STRATEGY-OWNER DECISION REQUIRED

**Bot 1:** canonical structure (strangle vs condor); entry timestamp; option
pricing source; exit/stop/target/roll rules; margin basis; expiry alignment.
Far-OTM option-chain history must also be acquired before any backtest.

**Bot 5:** whether the live path should adopt the corrected causal signal (it
currently uses the leaky one); and whether a spot-delta proxy is acceptable as
research evidence at all.

## Classification

**BOT 1** — RESEARCH = **FAIL** · VALIDATION = **NOT VERIFIABLE** · LIVE PARITY = **FAIL** · PAPER STATUS = **NOT READY**

**BOT 5** — RESEARCH = **PARTIAL** (causal, but proxy-priced) · VALIDATION = **PARTIAL** (no evidence of edge) · LIVE PARITY = **FAIL** · PAPER STATUS = **NOT READY**

Neither bot is claimed profitable. Neither is ready for the next stage.

# AI MASTER STATUS

**Updated:** 2026-09-18
**Branch:** `rebuild/bots-1-5-6-7`
**Baseline tag:** `pre-master-bots-1-5-6-7` → `749db3e1ef7a4c8d88711490719dc82c56cd3880`
**`main` modified:** NO
**`LIVE_TRADING_ENABLED`:** `false`
**Dhan endpoints used:** read-only only — `/charts/historical`, `/charts/intraday`,
`/charts/rollingoption`. **No order, trade, position, super-order, forever-order or
any other mutation endpoint was called at any point.**

---

## HEADLINE

Four bots were taken as far as authentic data allows. **None is paper-ready, and
none is close.** Every conclusion rests on real exchange prices over multi-year
samples, not on synthetic premiums or delta proxies.

| Bot | Sample | Gross | Net | Verdict |
|---|---|---|---|---|
| **1** Iron Condor | 158 weekly cycles, 2019–2026 | +4.51 pts/cycle | **+2.90 pts, t=+1.40** | no demonstrable edge |
| **5** Active Momentum | 589 trades, 2020–2026 | −₹45,539 | **−₹89,377, t=−1.33** | signal is directionally wrong |
| **6** Micro Momentum | 187 trades, 2020–2026 | **+₹11,109** | **−₹2,838, t=−0.05** | costs exceed the edge |
| **7** Discovery | 7 candidates | — | — | **NO VALIDATED EDGE** |

---

## WHAT CHANGED THE ANSWERS: data, not parameters

No strategy parameter was altered anywhere in this work. What changed is that the
data blockers turned out to be vendor-endpoint limits, not real ones.

| Blocker as previously recorded | What it actually was |
|---|---|
| "Bot 1 cannot be backtested — 0.0% of 420 sessions feasible" | A DhanHQ `/charts/rollingoption` ATM±10 ceiling. NSE's **public** F&O bhavcopy carries strikes 12000–34500 against a ~23200 spot, with 360k–650k daily volume at exactly the specified legs. |
| "Bots 5/6 have only 10 sessions of option data" | A caching artefact. The same endpoint serves 5-minute bars back to **2020-09**. |
| "Dhan token expired" | Renewed by the user mid-session; every token-blocked probe was re-measured. |

### Data now held (all authentic, all read-only)
| Dataset | Coverage |
|---|---|
| NIFTY + India VIX daily OHLC | 1,901 sessions, 2019-01 → 2026-09 |
| NIFTY option chains, daily, **all strikes** | 1,903 sessions, **4.0M rows** |
| NIFTY options, 5-minute, ATM±6, CE+PE | 1,495 sessions, **2.9M bars**, 324 real strikes |

The index history was cross-checked against the repository's own files
independently: 422 overlapping sessions, max difference **0.0008 points**.

### Dhan re-probe, measured 2026-09-18
| Probe | Result |
|---|---|
| `/charts/rollingoption` history floor | 2020-09 (2019-09 empty) |
| Request window | one month; longer returns empty |
| Strike ceiling | **ATM±10**, stable across 2021 / 2023 / 2026 |
| Option side | CALL → `ce`, PUT → `pe`; two separate calls |
| `/charts/intraday` with an option securityId | **works, reaches ATM+17** |
| Expired contracts via `/charts/intraday` | **0 rows — listed contracts only** |
| bhavcopy `FinInstrmId` vs Dhan `securityId` | **identical, 1694/1694** |

---

## PER-BOT DETAIL

### BOT 1 — see `reports/BOT1_REAL_CONDOR_FINDINGS.md`
Four real legs, real prices, exact cash settlement. Net **+2.90 points/cycle at
t=+1.40** — indistinguishable from zero before any slippage, **negative at 1 point
per leg**. The earlier 2025–26 figure (97.7% win, 2.27% breach) was a benign-period
artefact; the full history breaches at 7.32%.
**Blocker:** the edge is too small relative to its own execution cost.
**Strategy-owner decisions:** RSI band inconsistency (40/68 vs 38/70); `sqrt(5/365)`
over a ~7-day hold places the "1.8 SD" short at ~1.52 SD.

### BOT 5 — see `reports/BOT56_DEEP_GRID_FINDINGS.md`
589 trades. The defect is upstream of the options: **the spot moved in the
signalled direction on only 43.4% of trades**, against a 33.3% break-even for its
own 2:1 target/stop. More data will not change this.

### BOT 6 — PROTECTED BASELINE, FROZEN, UNMODIFIED
The only positive **gross** edge in the repository (+₹11,109), destroyed by
₹13,946 of costs. ~₹59/trade of edge against ~₹75/trade of cost.
No parameter, entry rule, exit rule or threshold changed.
**Reported, not acted on:** the target was hit 3 times in 187 trades while 137
exits were EOD — the specified target is effectively unreachable intraday.
**Strategy-owner decision.**

### BOT 7 — see `reports/BOT7_RESEARCH_LEDGER.md`
Ledger written **before** any candidate ran. Seven executions, zero survivors.
The most important entry is the **C6 artefact**: a version that exited on a 15:15
quote reported +₹456,653 at **t=+12.8** and "SURVIVED", purely because it silently
skipped the 101 sessions whose spot moved too far for the strike window — the very
sessions a short straddle loses on (skipped mean move 201 pts vs 53 for priced;
36.6% of skipped blew through the wing vs 0.0% of priced). Corrected to settle at
expiry, it prices 318 of 319 sessions and returns **−₹22,094 at t=−0.305**.

---

## DEFECTS FOUND AND FIXED IN THIS SESSION

1. **Live-path crash (Bots 3/4/5/6).** `trade["target_premium"]` was read directly;
   a position restored without that key raised `KeyError` **inside the monitoring
   loop, aborting evaluation for every bot in the cycle**. Now routed through
   `protective_level()`, which fails closed: no automatic exit fires, the position
   stays open and visible, EOD square-off still applies, and the condition is
   logged. Behaviour is identical when the key is present.
2. **Muhurat sessions in the option grid.** Four evening-only sessions (18:00–19:15,
   zero regular-session bars) would have been traded as if 18:15 were the open.
   Grid now restricted to the regular session.
3. **Silent-skip selection bias** (the C6 artefact above).
4. **Non-terminating simulations.** Per-session filters over 4.0M / 1.5M rows are
   now indexed once; without this neither Bot 1 nor Bot 5/6 completes at full scale.

## KNOWN FAILURES NOT FIXED (out of scope)
`test_h3_settled_bar_strategies_refuse_a_forming_bar` fails for **Bots 3 and 4**
because the strategies are flat on current data, so the adapter returns
`NO_SIGNAL: strategy flat` before reaching the forming-bar guard. The test is
date-sensitive. Bots 2/3/4 are explicitly out of scope for this mission.

---

## TEST COUNT — full suite, 2026-09-18

**478 collected: 476 passed, 2 failed** (14m 27s).

| | baseline `749db3e` | now |
|---|---|---|
| collected | 418 | **478** (+60) |
| failing | **4** | **2** |

The 2 that remain are `test_h3_settled_bar_strategies_refuse_a_forming_bar` for
**Bots 3 and 4**. Both **fail identically on the untouched baseline** (verified by
checking out `749db3e`), so they are pre-existing, not a regression. They are
date-sensitive: the strategies are flat on current data, so the adapter returns
`NO_SIGNAL: strategy flat` before reaching the forming-bar guard the test asserts
on. Bots 2/3/4 are explicitly out of scope for this mission, so they are reported
rather than changed.

The other 2 baseline failures — `test_c1_bot6_blocked_by_max_positions[1]` and
`[-1]` — were the `target_premium` crash and are now **fixed**.

## EXACT NEXT ACTION
Nothing is in flight. Every target bot has reached a specific, evidenced stopping
point. The open items are **strategy-owner decisions**, not engineering tasks:
Bot 1's RSI band and time-scaling, Bot 6's unreachable target, and whether any of
these strategies should be pursued at all given that three of four have a negative
or zero net edge on authentic multi-year data.

---

## UPDATE 2026-09-18 — 3-MONTH PROFITABILITY STUDY CLOSES BOT 1

Full report: `reports/FINAL_3_MONTH_PROFITABILITY_STUDY.md`.

The holdout (2026-06-18 → 2026-09-18) and a fresh 5-bot candidate search were run
on branch `main`. **Outcome B: no strategy met the money-plus-quality gate.**

BOT 1 measured at **t = 6.86 over 79 rupee-priced cycles** and nearly passed. It
was rejected after re-measurement. The rupee simulator can only run from 2024,
because legacy bhavcopy has no `NewBrdLotQty` and it fails closed on lot size —
silently excluding COVID, 2021-22 and the pre-2024 expiry regime. Re-measuring the
identical geometry in **points** over 2019-2026 (259 cycles, no lot size needed):

| Window | n | Gross pts/cycle | t | Breach |
|---|---|---|---|---|
| ALL 2019-2026 | 259 | **+0.15** | **0.06** | 8.5% |
| Pre-2024 | 159 | −4.42 | −1.27 | 10.7% |
| 2024+ | 100 | +7.41 | 3.19 | 5.0% |

**Six of eight years lose money. The only two profitable years, 2025 and 2026, are
the only two with a 0.0% breach rate.** This independently reproduces the 158-cycle
finding already recorded above (+2.90 pts, t=+1.40) and confirms the "benign-period
artefact" diagnosis was correct.

The maximum-loss tail is **not** hypothetical: **6 of 259 cycles (2.3%) lost ~95% of
the wing width** (≈ −₹12,350/lot), four of them at VIX between 12.7 and 20.6. Net
of measured costs (₹123/cycle) the full-sample expectancy is **−₹113 per cycle**.

Also closed: the sole intraday candidate to pass the DEV+VAL gate returned +₹13,250
on the holdout but its **median trade is negative on both DEV (−₹560) and VAL
(−₹1,009)**, and removing its single best VAL trade turns VAL negative. Rejected.

Reproduce with `scripts/research/condor_regime_check.py`.

**Test suite: 530 passed.**

---

## UPDATE 2026-09-18 (later) — 6-MONTH MONEY STUDY, ROGUE STRATEGY SEARCH

Full report: `reports/FINAL_6_MONTH_MONEY_STUDY.md`.

Holdout 2026-03-18 -> 2026-09-18 (125 sessions). Splits: DEV 1,001 / VAL 371 /
HOLDOUT 125. Search: **31 distinct concepts, ~100 implementations, 5 rounds**,
including external sources (Gao/Han/Li/Zhou intraday momentum; public NIFTY ORB
and VWAP-pullback write-ups). **No candidate was promoted.**

### Money result (frozen five-bot system, equal sleeves, whole lots)

| Account | Net | Return | Max DD | Profitable days |
|---|---|---|---|---|
| Rs 20,000 | **nothing executable** | — | — | — |
| Rs 50,000 | **-Rs 14,587** | **-29.17%** | 42.73% | 7.2% of sessions |
| Rs 1,00,000 | **-Rs 17,956** | **-17.96%** | 40.81% | 19.2% of sessions |

Per lot on the holdout: BOT1 +10,565 (0/17 breaches), BOT2 +20,466 (2/17),
BOT6 **-14,587**, BOT7 +653 (n=7), BOT8 **0 trades**.

### What was learned

1. **25 of 31 concepts were gross-negative on DEV** — the directional intraday
   signal is absent, not merely expensive.
2. **NIFTY intraday volatility compressed structurally.** Sessions with a 0.35%
   opening range: 10.1% (2022) -> 2.4% (2023) -> ~2% since. DEV 6.8% / VAL 2.4% /
   HOLDOUT 1.6%. A round trip costs ~Rs 74 on ~Rs 7,000 of premium (1.05%).
3. **Market Intraday Momentum (JFE 2018) does not transfer**: -Rs 123,679,
   t=-4.59, gross-negative. Reported as measured.
4. The one DEV effect (wide-opening-range ORB, 25 of 29 variants positive, two
   monotone axes) **failed validation**: every variant with a usable sample went
   negative; the two that stayed positive fired 9 times in 371 sessions.
5. **Two artifacts of my own making were caught before shipping**, both worth
   large fake profits:
   - a 4-step wing beating a 3-step wing (+Rs 179,017 vs -Rs 46,213) with
     *identical short strikes* — the exit bar was being chosen by data
     availability;
   - a zero-DTE condor at +Rs 141,174 (t=8.07) whose stale-mark filter deleted 68
     of 211 expiry sessions, the refused ones averaging **1.525% prior-day range
     against 0.843%** for the taken ones. Settling at expiry instead of marking
     gives the honest number: **-Rs 47,803, 50.5% breach, t=-1.18**.

### Deliverables

- `src/research/lab2.py` (level-based engine, R:R is a property of the setup)
- `src/research/concepts.py` (31 concepts), `src/research/intraday_premium.py`,
  `src/research/dte0_condor.py`
- `scripts/research/`: dev_sweep, dev_sweep2, dev_sweep3, validate2, dev_premium,
  dte0_study, holdout_6m, money_result_6m
- `tests/test_research_lab2.py` — 19 regression tests targeting lookahead and
  silent selection specifically
- README performance claims replaced with measured results; dashboard
  `/api/historical` extended with capital deployed, return on deployed, win rate,
  expectancy, profit factor, drawdown, day distribution

### Standing conclusion

Across two studies and ~130 tested implementations, **no strategy in this
repository has a validated edge**. BOT6 and BOT8 should be retired. BOT1 and BOT2
are profitable only in zero-breach regimes. `LIVE_TRADING_ENABLED` remains false.

---

## UPDATE 2026-09-19 — ONE-YEAR MONEY STUDY, OUTCOME B

Full report: `reports/FINAL_ONE_YEAR_MONEY_STUDY.md`.
Resume point: `reports/ACTIVE_RESEARCH_STATE.md`.
Machine-readable state: `data/research_state/final_one_year_state.json`.

Holdout **2025-09-18 → 2026-09-18 (248 sessions)**, measured once. Splits:
DEV → 2024-09-17, VAL 2024-09-18 → 2025-09-17 (247), HOLDOUT 248.
**No candidate promoted.** ~90 new implementations this run, ~220 across all three
studies.

### Money result (frozen five-bot system, equal sleeves, whole lots)

| Account | Allocation | Net | Return | Max DD | Profitable days |
|---|---|---|---|---|---|
| Rs 20,000 | **nothing executable** | — | — | — | — |
| Rs 50,000 | `{BOT8: 1}` | **+Rs 311** | **+0.62%** | 0.00% | **1 of 248 = 0.4%** |
| Rs 1,00,000 | `{BOT8: 2, BOT1: 1}` | **+Rs 15,789** | **+15.79%** | 0.00% | 29 of 248 = 11.7% |

Per lot on the holdout: BOT1 +15,166 (28/28 cycles won), BOT2 +30,241 (28/28),
BOT6 −30,937 at 1 lot, BOT7 −17,391, BOT8 +311 from **one trade all year**.

**The Rs 1,00,000 number is 96% BOT1 and it is the zero-breach artefact, now
confirmed a third time.** BOT1's average win is Rs 542 against a Rs 14,630 maximum
loss, so its break-even win rate is **96.43%** while the measured breach rate over
259 cycles from 2019 is **8.5%**. A full year with zero drawdown from a
short-premium strategy means the tail did not occur, not that it is absent.

### The one thing this run established that the previous two did not

NIFTY's directional edge is worth about **15 index points a night**:

| Segment, DEV 2019-01 → 2024-09-17, n=1,409 | Mean | t | Win rate |
|---|---|---|---|
| close → next **open** | **+0.1350%** | **+7.02** | **68.6%** |
| **open → close** (regular session) | **−0.0677%** | **−2.71** | 48.4% |

Positive in each of six DEV years; +0.1245% at t=8.18 excluding 2020; removing the
five best nights leaves 170.7 of 190.2 points. But only **+0.0907% (t=5.06)** is
available at the 09:15 traded spot — 29% of the headline is in the pre-open
auction print, which nobody can trade.

**Every strategy previously built in this repository was flat by 15:15, and so held
exposure only during the half of the day that loses money.**

Why the drift still cannot be monetised at Rs 20k–Rs 1L: a near-ATM weekly option
is the only instrument with a credible spread, it has delta ≈ 0.5 and pays ≈ **12
points of overnight theta**, so 0.5 × 15 − 12 < 0. Measured: long ATM call
overnight **+1.13 pts (t=0.75)**, ATM+1 **+0.65 (t=0.49)**. Structures that do
capture the whole move need **Rs 169,481** of margin:

| Structure | DEV exp | t | Capital/lot |
|---|---|---|---|
| naked short put ATM+2 | +5.29 pts | 2.45 | **Rs 169,481** |
| synthetic long future | +4.48 pts | 1.44 | **Rs 169,481** |
| put spread ATM+2, 400 wide | +4.71 pts | 2.73 | Rs 21,380 |

The affordable defined-risk versions die under cost stress (t=0.47 at 2×, −3.08
pts at 3×): the protective leg costs about two thirds of the edge.

### Open interest was used for the first time

`src/research/chain_panel.py` builds 1,903 sessions × 79 columns of point-in-time
chain state from the 4.0M-row bhavcopy (OI at 100% coverage). Conditional overnight
index move against an unconditional +15.97 points:

| Condition | n | Mean | t | Win |
|---|---|---|---|---|
| **PCR_OI > 1.1** | 195 | **+31.65 pts** | **6.21** | 68.2% |
| PCR_OI > 1.3 | 67 | +26.16 | 2.96 | 68.7% |
| PCR_OI < 0.7 | 196 | +10.15 | 1.23 | 57.1% |
| max pain > 0.5% below spot | 98 | +32.43 | 3.31 | 67.3% |
| VRP < −2 | 43 | +40.93 | 2.80 | 74.4% |

PCR_OI > 1.1 **doubles** the drift on a smooth threshold curve from 0.9 to 1.4.
**The brief's direction is right and its level is wrong**: a high put-call ratio
precedes *continued upward* drift, not reversal.

It still failed. PCR > 1.1 fires on only ~20% of sessions since 2021, so the
validation sample was 28 nights and no candidate reached the pre-registered
t ≥ 2.0 gate (VAL t = 0.68–1.26, sign replicated). All six were negative on the
holdout.

### Three artefacts caught before they became results

1. **Short put overnight, +6.52 pts → the ladder skip.** Pricing exits from the
   ATM±6 grid deleted 12–29 nights per strike whose index move averaged **−185 to
   −279 points** against +19 to +26 for the nights that priced. Repriced from the
   bhavcopy with nothing dropped: **negative**.
2. **Long call overnight, +3.49 pts (t=3.42) → the exit venue.** The entire edge
   was the bhavcopy *opening print*. Exited five minutes later at the 09:20 grid
   bar the same trade **loses 1.31 (t=−0.87)**.
3. **Short straddle, +13.07 pts (t=6.59) → 34 unpriced nights.** Those nights
   averaged **−231.34 points** with a mean |index move| of **468 vs 101**.
   Completely priced: **−0.38 pts, t=−0.13.** This reproduces the repository's own
   C6 artefact by an independent route.

### Also closed

- **Equity cross-section**, 20 ranked features × 4 horizons, 48 NSE names,
  124,511 rows. A real short-term **reversal** effect (mom3 h=1 long-short
  −0.0850%/day, t=−3.51) that is **smaller than STT**: delivery equity pays 0.1%
  on *each* side and the best gross daily alpha is 0.085%. Also survivorship-
  contaminated — the 48 names are the *current* NIFTY 50 and every index-removed
  name has no price file.
- **Long straddle** 1–4 day holds: −18.05 pts/day, t=−9.09, 29.1% win. Filtering
  on "cheap" volatility makes it **worse** (−32.30 at VRP<0): VIX below realised
  usually means realised just spiked and is about to fall.

### Contamination disclosed

While tabulating the drift year by year, the calendar-2025 and calendar-2026 rows
were displayed; both lie inside the holdout (2025 +0.0366% t=1.11, 2026 −0.0107%
t=−0.18). Disclosed in §3.4 of the report. It could only steer toward rejection,
and every candidate had already failed the VAL gate. Independent corroboration:
the **control** (bear call spread) is −5.76 pts (t=−4.54) on DEV and turns
**+7.04 (t=+2.20)** on the holdout — the drift's sign reversed, and the engine
tracks direction rather than costs.

### Deliverables

- `src/research/chain_panel.py`, `src/research/overnight.py`,
  `src/research/equity_panel.py`
- `scripts/research/`: chain_screen, overnight_dev, overnight_falsify,
  overnight_validate, equity_screen, money_result_1y
- `tests/test_research_overnight.py` — **25 tests** targeting silent skips, exit
  venue, adverse marking, margin treatment, lookahead, split integrity, and a
  mirror-sign check that fails if the engine measures costs instead of direction
- README status note and results tables replaced with the one-year measurements

`LIVE_TRADING_ENABLED` remains **false**. Nothing is promoted to paper trading.
BOT1, BOT2, BOT6, BOT7 and BOT8 are all recommended for retirement.

### Addendum — external discovery pass, weekly cycle rejected

An external search pass surfaced one deterministic hypothesis this repository had
not tested: **Durgia, "Weekly Behavior of the Nifty Index", SSRN 5353404** — an
expiry-cycle anchor (session after one expiry → next expiry) for systematic weekly
option selling. Tested in `scripts/research/weekly_cycle_study.py`.

This is the **cleanest measurement in the repository**: settling at expiry needs no
exit price at all, because the bhavcopy writes the underlying's final settlement
value into `SttlmPric` on every expiry session. Ladder truncation, opening prints,
stale marks and silent skips are all structurally absent. One cycle of 242 lacked an
entry price and is the only exclusion. Entry is priced from the bhavcopy 30-minute
VWAP with the measured +0.80-point bias **subtracted** from every short leg.

| Variant | n | exp pts | t | win% | breach% | worst |
|---|---|---|---|---|---|---|
| strangle ±1.0% | 241 | +10.42 | 0.84 | 70.1 | 55.6 | −1,110 |
| strangle ±1.5% | 241 | +11.02 | 0.99 | 76.3 | 38.2 | −1,061 |
| **strangle ±2.0%** | 241 | **+8.76** | **0.87** | 82.6 | 23.7 | **−1,039** |
| strangle ±2.5% | 241 | +6.61 | 0.73 | 88.4 | 14.5 | −1,012 |
| strangle ±3.0% | 241 | +3.99 | 0.48 | 90.9 | 10.4 | −979 |
| straddle ATM | 241 | +7.45 | 0.53 | 61.0 | 100.0 | −1,124 |

**Rejected.** Win rates of 70–91% at t < 1 are the "high win rate, no expectancy"
pattern the brief says to reject. **One cycle of 241 accounts for 49% of all profit**
(net 2,111 points; 3,150 with the single worst cycle removed). By year the ±2%
variant runs −13.32 / +5.51 / +19.68 / +1.56 / +36.63 — no stability.

And the calendar claim does not support selling in the first place: the ATM straddle
costs **1.66% of spot** at entry while only **41.7%** of cycles finish inside ±1% and
76.9% inside ±2%. The weekly move is mean +0.318%, std 2.472%, min −16.99%. The
market prices the weekly distribution about right; the residual is a fat left tail.

Full source ledger in §5b of `reports/FINAL_ONE_YEAR_MONEY_STUDY.md`. Running totals
after this pass: **~96 implementations this run, ~226 across all three studies, 46
distinct concepts.**

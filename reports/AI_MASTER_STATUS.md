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

## TEST COUNT
Baseline 419 → **479 collected** (+32 Bot 1, +14 Bot 5/6 deep grid, +14 Bot 7).
See the final suite run for the current pass/fail split.

## EXACT NEXT ACTION
Nothing is in flight. Every target bot has reached a specific, evidenced stopping
point. The open items are **strategy-owner decisions**, not engineering tasks:
Bot 1's RSI band and time-scaling, Bot 6's unreachable target, and whether any of
these strategies should be pursued at all given that three of four have a negative
or zero net edge on authentic multi-year data.

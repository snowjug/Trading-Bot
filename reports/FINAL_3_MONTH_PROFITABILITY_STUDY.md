# FINAL 3-MONTH PROFITABILITY STUDY

**Holdout window:** 2026-06-18 → 2026-09-18 (65 index sessions, 64 priced, 10 weekly expiry cycles)
**Measured:** once, after every rule was frozen. Nothing in this report was tuned on this window.
**Execution model:** no historical bid/ask exists. Every side pays `max(1 tick, 0.30% of premium)` of
half-spread plus 2 ticks of slippage, on top of statutory charges (IndianCostModel, side-aware STT).
That is deliberately harsher than the 0.22% spread observed live on 2026-09-18.
**LIVE_TRADING_ENABLED = false. Paper only. Dhan used read-only for market data.**

---

## VERDICT — OUTCOME B: NO STRATEGY QUALIFIES

The candidate budget is exhausted. **No strategy meets the money-plus-quality requirement.**

Two candidates looked like winners on the holdout and both were destroyed by the checks that followed:

| Candidate | Holdout net | Why it was rejected |
|---|---|---|
| BOT 1 weekly condor | +₹5,060/lot | Edge exists only in the 2025–26 zero-breach regime. Over 259 cycles (2019–2026) gross expectancy is **+0.15 points, t = 0.06** — nothing. Net of costs: **−₹113/cycle.** |
| `S_thr0.60_tgt0.50` intraday | +₹13,250 | 97% of the profit is two trades. Its **median trade loses money** on both DEV (−₹560) and VAL (−₹1,009). |

**No bot is promoted. No configuration is changed. Nothing is declared ready for real money.**

---

## THE CENTRAL FINDING: A REGIME ARTIFACT THAT ALMOST PASSED

The weekly iron condor (BOT 1) initially measured as a clear winner:

| | n | Win% | Net | Expectancy | **t** | Breaches | MaxDD | Worst |
|---|---|---|---|---|---|---|---|---|
| All rupee-priced cycles | 79 | 92.4% | +₹35,635 | +₹451 | **6.86** | 4 (5.1%) | ₹3,411 | −₹2,207 |
| In-sample | 69 | 91.3% | +₹30,575 | +₹443 | 5.93 | 4 | ₹3,411 | −₹2,207 |
| Out-of-sample holdout | 10 | 100% | +₹5,060 | +₹506 | 7.95 | 0 | ₹0 | +₹172 |

t = 6.86 over 79 nominally independent weekly cycles, with out-of-sample expectancy (₹506) matching
in-sample (₹443). It survives Bonferroni correction for the ~30 candidates tested here. It looked real.

**It is not.** The rupee simulator can only run from 2024 onward, because legacy NSE bhavcopy carries no
`NewBrdLotQty` and the simulator correctly fails closed on missing lot size. That gate silently removed
COVID, 2021–22, and the entire pre-2024 expiry regime — precisely the conditions under which a
short-premium structure is supposed to break. The 79-cycle sample was not chosen; it was **imposed by a
data gate**, and the effect is indistinguishable from cherry-picking the window.

Re-measuring the identical geometry in **points**, which needs no lot size, over the whole store:

| Window | n | Win% | Gross pts/cycle | **t** | Breach rate | Worst |
|---|---|---|---|---|---|---|
| **ALL 2019–2026** | **259** | 91.9% | **+0.15** | **0.06** | 8.5% | −192.27 |
| Pre-2024 (omitted by the rupee study) | 159 | 89.3% | **−4.42** | −1.27 | 10.7% | −192.27 |
| 2024+ (the rupee study's window) | 100 | 96.0% | +7.41 | 3.19 | 5.0% | −174.88 |

Year by year, the mechanism is unmistakable:

| Year | n | Gross pts | t | **Breach rate** | Worst cycle |
|---|---|---|---|---|---|
| 2019 | 12 | −15.79 | −0.95 | 25.0% | −192.27 |
| 2020 | 32 | −1.21 | −0.17 | 6.2% | −190.85 |
| 2021 | 38 | −1.37 | −0.23 | 7.9% | −175.61 |
| 2022 | 40 | −4.49 | −0.60 | 12.5% | −191.48 |
| 2023 | 36 | −6.98 | −0.89 | 11.1% | −188.81 |
| 2024 | 36 | −1.00 | −0.16 | 13.9% | −174.88 |
| **2025** | 38 | **+12.10** | **14.38** | **0.0%** | **+4.94** |
| **2026** | 27 | **+12.07** | **7.90** | **0.0%** | **+4.40** |

**Six of eight years lose money. The two profitable years are the only two with zero breaches.** In 2025
and 2026 NIFTY never once settled beyond a 1.8 σ weekly short strike, so the structure collected full
credit 65 times running. That is not an edge; it is a low-realised-volatility regime, and the t-statistic
measures the regime, not the strategy.

This independently reproduces the earlier 158-cycle finding for this bot (+2.90 pts/cycle, t = +1.40, no
demonstrable edge) and refutes the t = 6.86.

### The tail is not untested — it has fired six times

I initially recorded the maximum loss as "structurally possible but never observed in 79 cycles." Over the
full 259-cycle sample that is false. **Six cycles (2.3%) lost essentially the entire wing width:**

| Entry | Expiry | Settlement | Shorts | Loss |
|---|---|---|---|---|
| 2019-09-19 | 2019-09-26 | 11,571.2 | 10350 / 11050 | −192.27 pts (−96.1% of width) |
| 2020-09-17 | 2020-09-24 | 10,805.5 | 11050 / 12000 | −190.85 pts (−95.4%) |
| 2022-06-09 | 2022-06-16 | 15,360.6 | 15800 / 17150 | −191.48 pts (−95.7%) |
| 2023-11-30 | 2023-12-07 | 20,901.2 | 19600 / 20650 | −188.81 pts (−94.4%) |
| 2022-02-17 | 2022-02-24 | 16,248.0 | 16550 / 18050 | −179.33 pts (−89.7%) |
| 2021-01-28 | 2021-02-04 | 14,895.6 | 13100 / 14550 | −175.61 pts (−87.8%) |

At a 65 lot that is roughly **−₹12,350 per lot in a single week**, and four of the six occurred at VIX
between 12.7 and 20.6 — not at obviously dangerous volatility. A structure that sheds 27 cycles of
expectancy in one week, at a 2.3% rate, cannot be run on the strength of a zero-breach quarter.

### Full-sample money expectancy

Gross +0.15 points × 65 = **+₹9.75 per cycle**, against measured costs of **₹123 per cycle** (₹1,230 over
10 holdout cycles, 4 legs, held to settlement).

**Net expectancy ≈ −₹113 per cycle.** Negative.

---

## PER-BOT HOLDOUT RESULTS (per lot, 2026-06-18 → 2026-09-18)

| Bot | Type | n | Win% | Gross | Costs | Net | PF | MaxDD | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| BOT 1 apex VRP | weekly condor | 10 | 100% | +6,291 | 1,230 | +₹5,060 | — | ₹0 | **REJECTED** — regime artifact, full-sample t = 0.06 |
| BOT 2 zen curvature | weekly vertical | 10 | 100% | +10,889 | 627 | +₹10,261 | — | ₹0 | **REJECTED** — in-sample t = 1.20, not executable |
| BOT 6 micro-momentum | intraday long | 14 | 57.1% | −1,418 | 1,013 | **−₹2,431** | 0.803 | ₹3,909 | **LOSS** |
| BOT 7 displacement | intraday long | 5 | 60.0% | +3,739 | 371 | +₹3,368 | 3.769 | ₹1,216 | positive, **not established** (n=5, t=+0.76) |
| BOT 8 price action | intraday structure | 0 | — | 0 | 0 | ₹0 | — | ₹0 | **NO SIGNAL** — no setup met its rules |

The holdout quarter was benign for short premium: **0/10 breaches for BOT 1, 1/10 for BOT 2.** Both
recorded 100% win rates. A zero-breach quarter cannot test a breach-risk strategy, which is why the
holdout on its own could not have caught this and the full-sample re-measurement was necessary.

### BOT 2 — rejected despite the largest holdout profit

| | n | net | expectancy | **t** | worst cycle | maxDD | max risk/lot |
|---|---|---|---|---|---|---|---|
| In-sample (2024-01 → 2026-06-17) | 69 | +₹24,872 | +₹360 | **1.20** | **−₹13,434** | ₹15,872 | ₹44,366 |
| Holdout | 10 | +₹10,261 | +₹1,026 | 5.52 | +₹498 | ₹0 | ₹38,415 |

t = 1.20 over 69 cycles is indistinguishable from luck; the holdout's t = 5.52 on 10 cycles is the smaller
and noisier sample and cannot rescue it. One lot risks up to ₹44,366, exceeding 60% of a ₹50,000 account —
**not executable at ₹20,000 or ₹50,000.** It carries the same regime dependence as BOT 1 and a worst cycle
30× larger.

### BOT 8 traded zero times

A reported result, not an omission. Its rules (swing confirmation k = 3, break ≥ 0.25 ATR, retest ≤ 0.22 ATR
anchored to the break bar, trend alignment required, VIX ≤ 26, R:R ≥ 1.3) produced no qualifying setup in 65
sessions. **No trade was forced to fill the table.**

---

## THE OTHER NEAR-MISS: `S_thr0.60_tgt0.50`

The intraday continuation family failed validation outright. Every wide-target variant profitable on DEV
lost on VAL:

| Candidate | DEV net | VAL net |
|---|---|---|
| C3_thr0.45_tgt0.50 | +₹39,619 | **−₹41,868** |
| W_tgt0.70_stp0.25 | +₹39,502 | **−₹45,641** |
| W_no_target_stp0.25 | +₹38,906 | **−₹60,647** |
| K_otm1_tgt0.50 | +₹18,138 | **−₹44,614** |

One candidate passed the DEV+VAL gate: `S_thr0.60_tgt0.50` (+₹4,986 on VAL, t = +0.24 on 43 trades). On the
holdout it returned **+₹13,250 on 5 trades, PF 10.4** — the highest return measured anywhere in this study.

**It is not an edge.** Trade-concentration analysis:

| | trades | net | without best trade | without best 2 | **median trade** |
|---|---|---|---|---|---|
| DEV | 146 | +₹63,714 | +₹54,621 | +₹45,822 | **−₹560** |
| VAL | 43 | +₹4,986 | **−₹2,791** | **−₹10,163** | **−₹1,009** |
| HOLDOUT | 5 | +₹13,250 | +₹6,093 | **+₹353** | +₹1,764 |

The VAL survival was a single trade — remove it and VAL turns negative. The holdout is 97% two trades. The
**median trade loses money in both DEV and VAL.** Surviving 1 of 8 validation attempts is what chance
produces. Not promoted, not deployed.

---

## CAPITAL SCENARIOS

Recorded for completeness. **No strategy qualified, so none of these is a recommendation.**

If BOT 1 were run at the holdout's benign results (which the full sample shows is not the expectation):

| Account | Lots (≤60% at risk) | Risk deployed | Holdout net | Return |
|---|---|---|---|---|
| ₹20,000 | **0** | — | — | **NOT EXECUTABLE.** One lot risks ₹14,630 = 73% of the account. |
| ₹50,000 | 2 | ₹29,259 | +₹10,121 | +20.24% |
| ₹1,00,000 | 4 | ₹58,518 | +₹20,242 | +20.24% |

Cumulative capital deployed at ₹1,00,000: ₹4,94,837; return on deployed 4.09%; return on max risk 34.59%.
Daily figures at that size: avg **+0.316%**, median **0.000%** (84.4% of sessions carry no P&L), days
≥ +1% 14.1%, ≥ +2% 7.8%, ≤ −1% 0.0%, holdout maxDD ₹0.

**SPAN / exposure margin: UNKNOWN.** Not obtainable through any read-only endpoint. Capital above is
*capital at risk* = (wing width − credit) × lot, the structural maximum loss. Actual broker margin will
differ and is not estimated.

Against the full-sample expectancy of −₹113/cycle, the honest projection at 4 lots is **−₹452 per week**,
not +₹20,242 per quarter.

---

## ANSWER ON THE 1%-PER-DAY OBJECTIVE

**Not achieved, and not achievable from anything measured here.**

Even taking BOT 1's benign-regime holdout at face value, it delivers **0.316% per trading day** (median
0.000%). Reaching 1% per day would need roughly 3× the size — about 12 lots on ₹50,000, or ₹175,000 of
capital at risk on a ₹50,000 account. That is impossible, and 2% is further out of reach. Once the
full-sample expectancy is applied, the daily figure is **negative**.

The 1% target was investigated as asked. The measured answer is that no strategy in this system produces it,
and no trade was forced to close the gap.

---

## SIGNAL QUALITY CEILING

Feature research on DEV (8,544 observations, 1,424 sessions) measured a maximum information coefficient of
**0.0713** (`from_open`, Spearman). Tail conditioning helps but does not transform it: the top 5% of the
combined signal produced a 63.8% directional hit rate and +0.085 ATR mean forward move against a median
prior ATR of 214 points — roughly **9 points of expected edge**, against a spread that costs more than that
on an ATM option.

That arithmetic is why the intraday long-option families failed, and it bounds what further intraday work
on this data can produce.

### Families closed

- **Intraday continuation** — failed VAL; sole survivor destroyed by concentration analysis.
- **Weekly short premium (condor and vertical)** — profitable only in zero-breach years; full-sample t = 0.06.
- **Mean reversion** — rejected on DEV, t = −3.12. Every measured feature was continuation-signed.
- **Expiry-day iron fly** — gross positive, costs consume it.
- **Wider condor (2.2 σ)** — holdout +₹1,721 vs 1.8 σ's +₹5,060 for the same risk. Dominated.
- **Price action (BOT 8)** — 0 holdout trades; 10 trades and t = −0.10 over its full history.

---

## PAPER STATUS

`LIVE_TRADING_ENABLED = false` in `.env`, verified. Dhan read-only. All five bot implementations are frozen
and unchanged by this study — nothing has been promoted or reconfigured.

**The paper runner is not currently up.** As of 2026-09-18 19:58 IST (market closed since 15:30):

- Last completed paper session: **2026-09-17**. There is no `data/session/2026-09-18/` artifact.
- No single-instance lock is held; no `run_paper_session` process is alive.
- Restarting it tonight would idle until Monday's open, so it was left down rather than started outside
  market hours.

---

## HONESTY LEDGER

- No dates cherry-picked; no losing trades removed; no losing sessions skipped; no parameters optimised
  against the holdout.
- **The one window that was effectively cherry-picked — 2024+, imposed by the lot-size fail-closed gate —
  was caught and re-measured over the full 2019–2026 sample, and it reversed the verdict.** That
  reversal is the main result of this study.
- Costs and slippage are harsher than observed live.
- SPAN/exposure margin: **UNKNOWN**, not estimated.
- Historical bid/ask: does not exist; a documented conservative model is used and stated above.
- Both highest-returning holdout lines (+₹13,250 and +₹10,261) are **rejected**, with evidence shown.
- Holdout breach counts (0/10 and 1/10) are disclosed as a limit on what this window can test.
- Paper and shadow trades are not reported anywhere in this document as historical evidence.
- No bot is declared ready for real money.

## REPRODUCTION

| Script | Produces |
|---|---|
| `scripts/research/edge_discovery.py` | causal feature ICs on DEV |
| `scripts/research/candidates_dev.py`, `candidates_dev2.py` | 32 intraday candidates, DEV only |
| `scripts/research/validate_candidates.py` | the DEV+VAL promotion gate |
| `scripts/research/weekly_premium_lab.py`, `weekly_full_window.py` | weekly short-premium family |
| `scripts/research/holdout_study.py` | the single frozen holdout measurement |
| `scripts/research/condor_ledger.py`, `final_money_math.py` | per-cycle ledger and capital math |
| **`scripts/research/condor_regime_check.py`** | **the 259-cycle regime test that reversed the verdict** |

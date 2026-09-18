# Bot 7 — Research Ledger

**This file is written BEFORE any candidate is tested.** Each hypothesis records
its economic mechanism, data, features, entry, exit, sizing, expected cost and
validation plan in advance, so a result cannot be reverse-engineered into a story
afterwards. Failed candidates stay here permanently; nothing is deleted.

`LIVE_TRADING_ENABLED = false` throughout. Read-only data access only.

---

## Ground rules for this bot

1. **Profitability is an outcome, not the target.** No parameter is searched. Each
   candidate is specified once, tested once, and recorded — win or lose.
2. **A candidate is rejected if it fails ANY of:** causal chronology, realistic
   costs, liquidity, OOS, walk-forward, parameter perturbation, placebo control,
   or multiple-testing adjustment.
3. **"No validated edge" is an acceptable and expected outcome.** Given Bots 1, 5
   and 6 all failed on authentic data, the prior should be that most candidates fail.
4. **Multiple-testing is tracked explicitly.** Every candidate executed counts
   toward the Bonferroni denominator, including the ones that fail.

---

## Data available (all authentic, already ingested)

| Dataset | Coverage | Source |
|---|---|---|
| NIFTY + India VIX daily OHLC | 1,901 sessions, 2019-01 → 2026-09 | NSE public index archive |
| NIFTY option chains, daily, ALL strikes | 1,903 sessions, 4.0M rows, 2019 → 2026 | NSE public F&O bhavcopy |
| NIFTY options, 5-minute, ATM±6, CE+PE | 1,499 sessions, 2.9M rows, 2020-09 → 2026-09 | DhanHQ `/charts/rollingoption`, read-only |

Known limits, carried into every candidate:
- **No bid/ask history anywhere.** All fills are traded-price approximations.
  Slippage is therefore stress-tested rather than assumed.
- Lot size is published only from 2024 (75 → 65); earlier rupee figures are not
  derivable, so per-point results are primary for the deep history.
- The 5-minute grid caps at ATM±10 by endpoint limit.

---

## Capital scenarios

Both are evaluated for every surviving candidate.

| | Scenario A | Scenario B |
|---|---|---|
| Capital | ₹50,000 | ₹1,00,000 |
| NIFTY lot | 65 | 65 |
| One ATM weekly option | ≈ ₹6,500 premium | ≈ ₹6,500 |
| Naked short margin | ≈ ₹1.3L — **not viable** | ≈ ₹1.3L — **not viable** |
| Defined-risk spread | max loss must fit the risk budget | as A |

A candidate that cannot be traded in one lot without exceeding a 20% per-trade
risk budget is marked **NOT VIABLE** for that scenario. Option *selling* without a
defined-risk hedge is out of scope at both capital levels, because SPAN margin
alone exceeds the account.

---

## CANDIDATE REGISTER

Status values: `SPECIFIED` → `TESTED` → `REJECTED` / `SURVIVED`.

---

### C1 — Overnight gap continuation (index, directional)
- **Hypothesis:** the NIFTY close-to-open gap does NOT fully mean-revert intraday;
  the open-to-close return is positively related to the overnight gap.
- **Mechanism:** overnight information (US session, global macro) arrives when the
  Indian market is shut and is impounded at the open. If impounding is incomplete,
  continuation follows.
- **Data:** daily NIFTY OHLC, 2019–2026.
- **Features:** `gap = open[t]/close[t-1] − 1`. Known at 09:15 on day t.
- **Entry:** at the open of day t when `|gap|` exceeds its own trailing 80th
  percentile (trailing window strictly prior to t).
- **Exit:** at the close of day t. No intraday stop.
- **Sizing:** one ATM weekly option in the gap direction.
- **Expected cost:** entry + exit spread, statutory charges on both sides.
- **Validation plan:** causal check, OOS 70/30, 4-fold walk-forward, slippage
  sweep, placebo (random entry days matched in count), Bonferroni.
- **Status:** SPECIFIED

---

### C2 — Volatility-contraction breakout (NR7 / inside day)
- **Hypothesis:** a day whose range is the narrowest of the last 7 is followed by
  an expansion, and the direction of the break from that day's range persists.
- **Mechanism:** volatility clusters and is mean-reverting at short horizons;
  compressed ranges resolve into expansion. This is the best-documented effect in
  the candidate set, which is precisely why it must be cost-tested hard.
- **Data:** daily NIFTY OHLC.
- **Features:** `range[t] = high−low`; NR7 flag if `range[t] == min(range[t-6..t])`.
  Both known at the close of day t.
- **Entry:** on day t+1, when price crosses day t's high (long) or low (short).
- **Exit:** at the close of day t+1.
- **Sizing:** one ATM weekly option in the break direction.
- **Expected cost:** as C1.
- **Validation plan:** as C1, plus a perturbation of the lookback (5, 7, 10) to
  confirm the result is not knife-edge. Perturbation is a ROBUSTNESS check, not a
  selection step — the reported candidate stays at 7.
- **Status:** SPECIFIED

---

### C3 — VIX mean reversion into weekly option decay
- **Hypothesis:** when India VIX is high relative to its own recent history,
  subsequent realised volatility over the following week is lower than implied.
- **Mechanism:** the variance risk premium. This is the same premise as Bot 1, so
  testing it as a spread rather than a condor isolates whether the premium exists
  independently of Bot 1's specific strike construction.
- **Data:** daily VIX, daily option chains.
- **Features:** `vix_z = (vix[t] − mean(vix[t-60..t-1])) / sd(vix[t-60..t-1])`.
- **Entry:** at the close of day t when `vix_z > 1`, sell a defined-risk vertical
  spread 1 SD out of the money, 5 trading sessions to expiry.
- **Exit:** cash settlement at expiry.
- **Sizing:** one spread; max loss = width − credit, must fit the risk budget.
- **Expected cost:** side-aware statutory charges on two legs.
- **Validation plan:** as C1, plus a breach-rate confidence interval against the
  structural break-even, the test that settled Bot 1.
- **Status:** SPECIFIED

---

### C4 — Time-of-day drift in the opening range
- **Hypothesis:** the first 30 minutes' range sets a level that the rest of the
  session respects; breaks of it continue rather than revert.
- **Mechanism:** overnight order imbalance clears in the opening auction and the
  first half hour; what follows is informed flow rather than noise.
- **Data:** 5-minute option grid's `spot` column (authentic intraday index path).
- **Features:** high/low of 09:15–09:45, known at 09:45.
- **Entry:** first 5-minute bar after 09:45 whose spot breaks that range.
- **Exit:** 15:15 flat, no intraday target or stop.
- **Sizing:** one ATM weekly option in the break direction.
- **Expected cost:** as C1.
- **Validation plan:** as C1. Note this is close in spirit to Bots 5 and 6, both of
  which failed; a negative result here would be corroboration, not new information.
- **Status:** SPECIFIED

---

### C5 — Day-of-week theta concentration
- **Hypothesis:** weekly option time decay is not uniform across the week; the
  premium lost per calendar day is largest in the final sessions before expiry.
- **Mechanism:** theta accelerates as expiry approaches, and the weekend carries
  calendar decay without trading risk.
- **Data:** daily option chains, ATM contracts, 2019–2026.
- **Features:** sessions-to-expiry, ATM premium.
- **Entry / Exit:** measurement first — this candidate begins as a DESCRIPTIVE
  study. A tradable rule is only specified if a decay asymmetry is actually found,
  and it will be written into this ledger before being tested.
- **Status:** SPECIFIED (descriptive phase)

---

### C5 — RESULT OF THE DESCRIPTIVE PHASE (recorded before C6 was specified)

Measured on 849 ATM straddle observations across 142 expiry cycles (2024-01 →
2026-09), within-cycle so the spot level cancels:

| sessions to expiry | mean premium change |
|---|---|
| 4 | −8.98% |
| 3 | −14.03% |
| 2 | −17.35% |
| 1 | −27.14% |
| **0 (expiry day)** | **−88.81%** |

The asymmetry is real and large. It is also textbook theta acceleration, which is
**compensation for gamma risk**, not free money — the premium decays fastest
exactly when a single adverse move can exceed the whole premium. Whether it is
tradable is therefore an open question, not a conclusion, and it is specified
below as its own pre-registered candidate.

---

### C6 — Expiry-day defined-risk iron fly (specified AFTER C5's measurement, BEFORE testing)
- **Hypothesis:** the 0DTE ATM straddle's −88.81% mean decay exceeds what its
  realised gamma risk costs, so a short at-the-money structure held into settlement
  has positive expectancy.
- **Mechanism:** variance risk premium concentrated into the final session, plus
  expiry-day pinning around the highest-open-interest strike.
- **Counter-hypothesis to be taken seriously:** the decay is exactly fair
  compensation for gamma, so the structure wins often and loses big. C3 already
  produced that signature (77.3% win rate, negative expectancy), as did Bot 1.
  A high win rate will NOT be treated as evidence.
- **Data:** the 5-minute option grid; on expiry day the near-weekly series IS the
  0DTE contract.
- **Structure:** short ATM call + short ATM put, long call at ATM+4 strikes and
  long put at ATM−4 strikes. Defined risk, so it fits both capital scenarios.
- **Entry:** 09:20 on expiry day, at that bar's traded prices, contracts fixed then.
- **Exit:** 15:15, at that bar's traded prices for the same four contracts.
- **Sizing:** one lot. Max loss = 200 points − credit.
- **Expected cost:** side-aware statutory charges on four legs plus slippage.
- **Validation plan:** OOS 70/30, 4-fold walk-forward, slippage sweep, Monte Carlo,
  Bonferroni across ALL candidates, and an explicit check that expectancy — not win
  rate — is positive.
- **Status:** SPECIFIED

---

## Multiple-testing accounting

Candidates specified: **6** (C6 added after C5's descriptive phase, before testing). Executed: **7** including C2's two declared perturbations. Every one executed counts toward the Bonferroni
denominator whether it succeeds or fails. If a candidate's rule is respecified
after seeing results, that counts as an ADDITIONAL test and is recorded as such.

## Results

All seven executions are recorded. **No candidate survived.**

| Candidate | Trades | Net | t | Bonferroni p | Folds + | Survives slippage | **Verdict** |
|---|---|---|---|---|---|---|---|
| C1 overnight gap | 311 | +₹22,385 | +0.270 | 1.000 | 2/4 | no (dies at 1 pt) | **REJECTED** |
| C2 NR7 breakout | 231 | +₹35,408 | +0.612 | 1.000 | 3/4 | yes | **REJECTED** |
| C2 NR5 *(perturbation)* | 300 | −₹12,357 | −0.180 | 1.000 | 3/4 | no | **REJECTED** |
| C2 NR10 *(perturbation)* | 163 | −₹25,226 | −0.580 | 1.000 | 1/4 | no | **REJECTED** |
| C3 VIX vertical | 44 | −620 pts | −1.323 | 1.000 | 1/4 | no | **REJECTED** |
| C4 opening range | 1,493 | −₹206,697 | −1.361 | 1.000 | 1/4 | no | **REJECTED** |
| C6 expiry iron fly *(corrected)* | 318 | −₹22,094 | −0.305 | 1.000 | 1/4 | no | **REJECTED** |

### What each result actually showed

**C1** — nominally profitable but statistically empty (t = +0.27), OOS sign
disagrees (+₹251 in-sample vs −₹341 out), and it dies at 1 point per side of
slippage. Consistent with no edge.

**C2** — the most interesting failure. At the specified lookback of 7 it makes
+₹35,408 and survives slippage. Both declared perturbations turn it negative:
**NR5 −₹12,357 and NR10 −₹25,226.** A real volatility-contraction effect would not
invert between a 5- and a 10-session lookback. The perturbation test did exactly
what it exists for, and the n=7 result is noise. Had only n=7 been run, this would
have looked like a candidate.

**C3** — a **77.3% win rate with negative expectancy**, the same signature Bot 1
produced. The variance risk premium at these strikes does not cover the tail. Win
rate was explicitly excluded as evidence in advance, which is why this was caught.

**C4** — decisively negative over 1,493 trades and corroborates Bots 5 and 6:
intraday breakout structures on NIFTY options do not pay for their own costs.

**C6** — see below. Its first version was an artefact and is retained as the
clearest methodological lesson in this ledger.

---

## THE C6 ARTEFACT — recorded in full, not deleted

The first implementation of C6 priced the exit from the 5-minute grid at 15:15. It
reported:

> 218 trades, **+₹456,653**, 78.0% win rate, **t = +12.789**, Bonferroni p = 0.000,
> **4/4** walk-forward folds positive, profitable at every slippage level,
> **VERDICT: SURVIVED**

That result was false. Holding a fixed strike from 09:20 to 15:15 requires that
strike to still be inside the ATM±6 window at 15:15. On a large move it is not, so
the session was silently skipped — and those are exactly the sessions a short
straddle loses on:

| | sessions | mean abs move | max | share exceeding the 200-pt wing |
|---|---|---|---|---|
| priced | 218 | **53.4 pts** | 140.7 | **0.0%** |
| skipped | 101 | **201.3 pts** | 532.1 | **36.6%** |

The giveaway was visible before the check: the worst trade was −₹3,891 against a
₹13,000 structural maximum loss. A short straddle that never approaches its own max
loss over 218 expiry days is not a strategy, it is a filter.

**The fix was not to widen the window.** It is expiry day, so the position settles
at intrinsic against the exchange's official settlement price and needs no exit
quote at all. With that, 318 of 319 sessions price and only 1 is dropped:

| | first (artefact) | corrected |
|---|---|---|
| trades | 218 | **318** |
| net | +₹456,653 | **−₹22,094** |
| win rate | 78.0% | 53.5% |
| t | +12.789 | **−0.305** |
| worst trade | −₹3,891 | **−₹8,890** |
| folds positive | 4/4 | **1/4** |
| verdict | SURVIVED | **REJECTED** |

Gross was +₹21,551 against ₹43,645 of costs — the same pattern as Bot 6: a small
gross edge that transaction costs more than consume.

---

## BOT 7 CONCLUSION: **NO VALIDATED EDGE**

Seven executions, zero survivors. This is an acceptable result and no strategy was
forced into existence to avoid it.

Three findings generalise beyond Bot 7:

1. **Costs dominate.** C6 and Bot 6 both had positive gross edges destroyed
   entirely by statutory charges and spread. On NIFTY options at one lot, the cost
   floor is roughly ₹75–₹140 per round trip, and none of the effects tested cleared
   it.
2. **A high win rate is not evidence.** C3 (77.3%), the C6 artefact (78.0%) and
   Bot 1 (94.6%) were all non-positive in expectancy.
3. **Silent skipping is the most dangerous bug in this codebase.** It produced a
   t = +12.8 result out of nothing. Any simulation that drops a session must report
   what it dropped and compare it against what it kept.

## Capital viability

Not applicable — no candidate survived to be sized. For the record, at both
₹50,000 and ₹1,00,000 only defined-risk structures and single long options are
tradable at all; naked short premium requires roughly ₹1.3L of SPAN margin per lot
and is out of scope at both levels.

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

## Multiple-testing accounting

Candidates specified: **5**. Every one executed counts toward the Bonferroni
denominator whether it succeeds or fails. If a candidate's rule is respecified
after seeing results, that counts as an ADDITIONAL test and is recorded as such.

## Results

*(empty — to be filled only after each candidate is executed)*

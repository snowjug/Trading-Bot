# FINAL ONE-YEAR MONEY STUDY

**Holdout:** 2025-09-18 → 2026-09-18 · **248 sessions** · measured once
**Run closed:** 2026-09-19 · **Branch:** `main` · **`LIVE_TRADING_ENABLED`: `false`**
**Dhan usage:** read-only market data only. No order, position, or any other
mutation endpoint was called at any point in this study.

---

## 1. MONEY RESULT

The frozen five-bot system on `main`, over the one-year holdout, sized by the rule
fixed before the numbers were seen: equal sleeves across the bots that can execute
at that account size, whole lots only, never more than 60% of the account at risk
in one position.

### ₹20,000

| | |
|---|---|
| NET P&L | **nothing executable** |
| RETURN | — |
| MAX DD | — |
| PROFITABLE DAYS | — |
| % DAYS ≥ +1% | — |
| % DAYS ≥ +2% | — |

One lot of the cheapest bot (BOT8) needs ₹9,196; the equal sleeve at ₹20,000 is
₹4,000. BOT6 needs ₹20,191, BOT7 ₹20,872, BOT1 ₹14,630, BOT2 ₹44,366. Letting
BOT8 take the whole account (1 lot, ≤60% at risk) returns **+₹311, +1.56%**, from
**one trade in 248 sessions**.

### ₹50,000

| | |
|---|---|
| NET P&L | **+₹311.43** |
| RETURN | **+0.62%** |
| MAX DD | ₹0 (0.00%) |
| PROFITABLE DAYS | **1 of 248 = 0.4%** |
| % DAYS ≥ +1% | 0.0% |
| % DAYS ≥ +2% | 0.0% |

Allocation `{BOT8: 1}`. Everything else is priced out of a ₹10,000 sleeve. The
system traded **once all year**.

### ₹1,00,000

| | |
|---|---|
| NET P&L | **+₹15,788.58** |
| RETURN | **+15.79%** |
| MAX DD | ₹0 (0.00%) |
| PROFITABLE DAYS | **29 of 248 = 11.7%** |
| % DAYS ≥ +1% | 0.4% |
| % DAYS ≥ +2% | 0.0% |

Allocation `{BOT8: 2, BOT1: 1}`. Avg daily +0.0637%, median daily 0.0000%, best
day +₹1,651, worst day ₹0, longest losing-day streak 0. BOT1 contributed ₹15,166
of the ₹15,789.

**A zero max drawdown over a full year, from a short-premium strategy, is not a
good sign. It is the finding.** See §3.

---

## 2. BEST STRATEGY

**There is none.** No strategy in this repository meets the money-plus-quality
gate. This is **outcome B** of the brief: the search budget for this run was
exhausted and every candidate, result and state is preserved.

The nearest thing to a survivor, and why it is not one:

| | |
|---|---|
| BOT | BOT1 |
| INSTRUMENT | NIFTY weekly options, four-leg iron condor |
| STRATEGY FAMILY | short premium / defined risk |
| TRADES (holdout) | 28 cycles |
| WIN RATE (holdout) | **100.0% — 28 of 28** |
| CAPITAL | ₹14,630 per lot (max risk) |
| NET P&L (holdout, 1 lot) | +₹15,166 |
| RETURN on max risk | +103.7% |
| AVG DAILY RETURN | +0.0637% (at ₹1L, portfolio) |
| MEDIAN DAILY RETURN | 0.0000% |
| % DAYS ≥ +1% | 0.4% |
| % DAYS ≥ +2% | 0.0% |
| EXPECTANCY (holdout) | +₹542 / cycle |
| PROFIT FACTOR (holdout) | ∞ (no losing cycle) |
| MAX DD (holdout) | ₹0 |
| MAX LOSING STREAK | 0 |
| **EXPECTANCY, FULL HISTORY 2019-2026** | **+0.15 points/cycle, t = 0.06, n = 259** |
| **COST SENSITIVITY** | negative at 1 point per leg of slippage |

The arithmetic that closes it: the average winning cycle is **₹542** and the
maximum loss is **₹14,630**, so the break-even win rate is
14,630 / (14,630 + 542) = **96.43%**. The measured breach rate over 259 cycles
from 2019 is **8.5%**, which puts the true win rate near 91.5% and the expectancy
below zero. Six of 259 cycles (2.3%) lost ~95% of the wing width. **Six of eight
years lose money; the only two profitable years, 2025 and 2026, are the only two
with a 0.0% breach rate.** The holdout is inside that zero-breach window, which is
exactly why it shows 28 wins and no drawdown: the entire risk of the strategy lives
in a tail that did not occur in these twelve months.

BOT2 (vertical spread) has the same shape: 28 of 28 cycles won, +₹30,241 per lot,
₹44,366 max risk, zero losing cycles.

---

## 3. WHAT THIS RUN ACTUALLY FOUND

One genuine, quantified market fact, and a mechanism-level explanation for why it
cannot be turned into money at the capital levels in the brief.

### 3.1 NIFTY's return is an overnight phenomenon

Measured on the development window (2019-01-01 → 2024-09-17, 1,409 sessions),
using only data that existed at the time:

| Segment | Mean per session | t | Share of sessions positive |
|---|---|---|---|
| Close → next **open** | **+0.1350%** | **+7.02** | **68.6%** |
| **Open → close** (regular session) | **−0.0677%** | **−2.71** | 48.4% |
| Close → close | +0.0668% | — | — |

Positive in every one of six DEV years (weakest 2022 at +0.031%). Excluding 2020
entirely it strengthens to +0.1245%, t = **8.18**. Removing the five best nights
leaves 170.7 of 190.2 points, so it is not an outlier artefact; the median night
(+0.169%) is *better* than the mean, the distribution being left-skewed.

**Every strategy previously tested in this repository was flat by 15:15, and
therefore held exposure only during the half of the day that loses money.** That
is the single most useful thing this study established.

### 3.2 The tradable part is smaller than the official open suggests

| Measured from the previous 15:2x close to… | Mean | t | Win rate |
|---|---|---|---|
| the official index **open** | +0.1278% | 7.35 | 67.1% |
| the **09:15** traded spot | +0.0907% | 5.06 | 61.7% |
| 09:20 | +0.0956% | 5.22 | 62.3% |
| 10:00 | +0.0869% | 4.39 | 58.9% |
| 15:00 | +0.0798% | 2.76 | 56.9% |

**29% of the headline drift is in the pre-open auction print and is not available
to anyone.** What remains — about **+15 index points a night** — is real and does
not decay quickly through the session.

### 3.3 Why 15 points a night is not enough

A near-ATM weekly NIFTY option is the only instrument in this account's reach with
a credible spread (observed live ATM spread 2026-09-18: ~0.22% of mid; the engine
charges 0.30% per side plus 2 ticks). Such an option has delta ≈ 0.5 and pays
roughly **12 points of overnight theta** on a ~99-point premium. So:

    0.5 x 15 points of drift  -  12 points of theta  =  negative

Measured, not asserted: a long ATM call held overnight returns **+1.13 points a
night (t = 0.75)** and ATM+1 **+0.65 (t = 0.49)** — both indistinguishable from
zero. The structures that *do* convert the drift need delta near 1 and little
theta, and all of them need margin far outside the brief:

| Structure | DEV expectancy | t | Capital per lot |
|---|---|---|---|
| Naked short put, ATM+2 | +5.29 pts | 2.45 | **₹169,481** |
| Synthetic long future (long ATM call + short ATM put) | +4.48 pts | 1.44 | **₹169,481** |
| Put spread, short ATM+2, 400 wide | +4.71 pts | 2.73 | ₹21,380 |
| Put spread, short ATM, 300 wide | +2.77 pts | 2.23 | ₹18,166 |

The defined-risk versions are affordable and **die under cost stress** — the
400-wide spread falls to t = 0.47 at 2× costs and to −3.08 points at 3×. The
protective leg costs about two thirds of the edge: two extra crossings plus its own
premium decay.

### 3.4 The effect decayed, and the decay is visible before the holdout

| Year | Overnight drift | t |
|---|---|---|
| 2019 | +0.1480% | 6.26 |
| 2020 | +0.1837% | 2.23 |
| 2021 | +0.1937% | 5.79 |
| 2022 | +0.0313% | 0.66 |
| 2023 | +0.1271% | 6.05 |
| 2024 | +0.0974% | 3.30 |

Every conditioned candidate's DEV significance comes from 2021. Excluding 2020-21,
the best (long ATM−1 call, PCR filter) is **+5.20 points, t = 1.41**, and 2024
alone is **−1.59**.

**Disclosure.** While checking this year-by-year table I displayed calendar 2025
and 2026 rows, which lie inside the one-year holdout. They show the index-level
overnight drift at **+0.0366% (t = 1.11) in 2025** and **−0.0107% (t = −0.18) in
2026**. That look was not part of a pre-registered test and it contaminates the
blindness of the holdout *for this one feature*. It is disclosed rather than
buried. It cannot have manufactured a false positive — it could only have steered
this study toward rejection, which is the conservative direction, and the
pre-registered validation gate had already rejected every candidate before the
holdout was run. The independent confirmation is in §4: the **control** structure,
a bear call spread, turned **positive** on the holdout (+7.04 points, t = 2.20).
The drift did not merely weaken in the holdout year; its sign reversed.

### 3.5 The put-call ratio does carry information

The brief's named PCR hypotheses, tested on DEV rather than assumed. Conditional
overnight index move, against an unconditional +15.97 points:

| Condition | n | Mean move | t | Win rate |
|---|---|---|---|---|
| **PCR_OI > 1.1** | 195 | **+31.65 pts** | **6.21** | 68.2% |
| PCR_OI > 1.3 | 67 | +26.16 | 2.96 | 68.7% |
| PCR_OI < 0.7 | 196 | +10.15 | 1.23 | 57.1% |
| max pain > 0.5% below spot | 98 | +32.43 | 3.31 | 67.3% |
| previous session up > 0.5% | 242 | +30.05 | 5.14 | 67.8% |
| VRP < −2 | 43 | +40.93 | 2.80 | 74.4% |
| days to expiry ≥ 4 | 197 | +6.71 | 0.75 | 58.4% |

PCR_OI > 1.1 **doubles** the drift, and the threshold curve from 0.9 to 1.4 is
smooth rather than a cliff, so the cut is not fitted. **The direction the brief
proposed is right and the level is not**: "PCR > 1.3 → reversal" is not what the
data says; high PCR precedes *continued upward* overnight drift. The brief's
instruction to treat the thresholds as hypotheses rather than truths was correct.

This is the first time any study in this repository has used open interest. It is
information, and it still was not enough — see §4.

---

## 4. THE VALIDATION AND HOLDOUT RESULT

Six candidates were pre-registered in `scripts/research/overnight_validate.py`
with the gate written before the numbers existed: **VAL expectancy > 0 AND
t ≥ 2.0 AND net > 0**, and the control must stay negative.

| Candidate | DEV exp / t | VAL n | VAL exp / t | Gate | HOLDOUT exp / t |
|---|---|---|---|---|---|
| ODC1 long ATM−1 call, PCR>1.1 | +9.44 / 3.00 | 28 | +9.61 / 1.08 | reject | **−10.61 / −1.04** |
| ODC2 long ATM call, PCR>1.1 | +8.12 / 2.93 | 28 | +11.83 / 1.13 | reject | **−10.03 / −1.11** |
| ODC3 put spread +2/400, PCR>1.1 | +7.36 / 2.39 | 28 | +4.38 / 0.68 | reject | **−3.96 / −0.48** |
| ODC4 synthetic long, PCR>1.1 | +16.25 / 3.23 | 28 | +19.78 / 1.19 | reject | **−11.72 / −0.73** |
| ODC5 naked short put +2, PCR>1.1 | +10.79 / 3.12 | 28 | +9.67 / 1.18 | reject | **−2.43 / −0.23** |
| ODC6 long ATM−1 call, PCR pct>70 | +7.01 / 2.50 | 46 | +8.86 / 1.26 | reject | **−12.80 / −1.44** |
| REF long ATM−1 call, unfiltered | +1.98 / 1.11 | 194 | −3.92 / −0.99 | reject | −15.70 / −2.27 |
| REF put spread +2/400, unfiltered | +4.71 / 2.73 | 194 | −2.63 / −0.70 | reject | −6.01 / −1.37 |
| REF naked short put, unfiltered | +5.29 / 2.45 | 194 | −2.23 / −0.36 | reject | −10.51 / −1.69 |
| **CTRL bear call spread** | −5.76 / −4.54 | 194 | −1.72 / −0.69 | control OK | **+7.04 / +2.20** |

**PROMOTED: 0.**

All six conditioned candidates kept the *sign* of their DEV effect on validation —
the mechanism replicated — but PCR_OI > 1.1 fires on only ~20% of sessions since
2021, so the validation sample collapsed to 28 nights and no t-statistic came near
the gate. The unfiltered references had already turned negative on validation. The
holdout, measured once and reported for disclosure only, is negative for all six.

The control's behaviour is the integrity check on the whole engine: it is deeply
negative where the drift is positive (DEV, t = −4.54) and positive where the drift
reversed (holdout, t = +2.20). The engine measures direction, not costs.

---

## 5. REJECTED / RETIRED STRATEGIES AND EXACT REASONS

### Rejected in this run

Row 14 deserves a note on method, because it is the cleanest measurement in the
whole study: settling at expiry needs **no exit price at all**. The bhavcopy writes
the underlying's final settlement value into `SttlmPric` on every expiry session, so
each cycle's payoff is exact arithmetic on an authentic print, and every failure mode
that faked a number elsewhere here — ladder truncation, opening prints, stale marks,
silent skips — is structurally absent. One cycle of 242 lacked an entry price and is
the only exclusion. Entry is priced from the bhavcopy 30-minute VWAP with the measured
+0.80-point bias **subtracted** from every short leg on top of spread and slippage. If
a weekly short-premium edge existed, this is where it would have shown.

| # | Concept | Implementations | Verdict and exact reason |
|---|---|---|---|
| 1 | Overnight long call, ATM−1/ATM/+1/+2 | 4 | +0.65 to +1.98 pts, t ≤ 1.11. Delta 0.5 × 15 points of drift loses to ~12 points of theta. |
| 2 | Overnight long call, deep ITM (ATM−4, ATM−6) | 2 | **−5.94 and −49.31 pts, t = −2.71 and −17.26.** Stale prints: median volume 16,350 at ATM−6 against 1,242,300 at ATM. Not a strategy, a data artefact. |
| 3 | Overnight put spreads, 6 offsets × 3 widths | 18 | Best +1.25 pts, t = 1.24 unconditional. |
| 4 | Overnight put spreads, wide (300–800) | 24 | Non-monotone surface peaking at width 400 (t = 2.73 selected from 44 cells; expected max \|t\| under the null from 44 correlated tests is ≈2.5–2.9). Ex-2020/21 t = 1.27. Dies at 2× costs. |
| 5 | Overnight naked short put, ATM / ATM+2 | 2 | Most stable found (+5.29, t = 2.45, positive every DEV year) but needs **₹169,481** margin — outside all three capital levels. |
| 6 | Overnight synthetic long future | 1 | +4.48, t = 1.44, ex-2020/21 **0.00**. Same margin problem. |
| 7 | Overnight bull call spreads | 4 | −0.79 to −2.78 pts. Pays theta on the long leg and caps the convexity that was the only thing working. |
| 8 | Overnight PCR/OI/max-pain/VRP conditioned structures | 48 cells | Sign replicated on VAL, t = 0.68–1.26 against a 2.0 gate; n = 28 because PCR > 1.1 fires on ~20% of sessions post-2021. Negative on holdout. |
| 9 | Equity cross-section: 20 ranked features × 4 horizons | 80 tests | A real short-term **reversal** effect (mom3 h=1: long-short −0.0850%/day, t = −3.51, i.e. +21.2%/yr reversed) that is **smaller than STT**. Delivery equity pays 0.1% securities transaction tax *on each side*; the best gross daily alpha is 0.085%. Dead at every horizon where the alpha is statistically present. Also survivorship-contaminated (§6). |
| 10 | Long ATM straddle, 1–4 day holds | 4 | **−18.05 pts/day, t = −9.09, 29.1% win.** |
| 11 | Long straddle filtered on cheap volatility (VRP<0, VRP<−2, IV percentile, rv>VIX) | 6 | **Worse, not better: −32.30 pts, t = −7.04 at VRP<0.** The hypothesis is backwards — VIX below realised vol usually means realised vol just spiked and is about to fall. |
| 12 | Short ATM straddle, 1-day hold | 5 | **+13.07 pts (t = 6.59) with 34 nights unpriced → −0.38 pts (t = −0.13) once every night is priced.** The 34 dropped nights averaged **−231.34 points** with a mean absolute index move of **468 points against 101** for the nights that priced. This is the repository's C6 artefact reproduced by an independent route. |
| 13 | Short straddle filtered on rich volatility / high VIX / dte≥4 | 4 | −1.43 to −10.62 pts once completely priced. |
| 14 | **Weekly short strangle / straddle over a full expiry cycle**, settled exactly at expiry (Durgia, SSRN 5353404) | 6 | **Best variant ±2%: +8.76 pts/cycle, t = 0.87, 82.6% win — and one cycle out of 241 accounts for 49% of all profit.** Worst cycle **−1,039 points** (≈ −₹67,535 at lot 65). By year: −13.32 / +5.51 / +19.68 / +1.56 / +36.63. The calendar claim itself does not support selling: the ATM straddle costs **1.66% of spot** at entry while only **41.7%** of cycles finish inside ±1% and 76.9% inside ±2% — the market already prices the weekly distribution. |

### Retired earlier, reconfirmed here

| Bot | Reason | Status |
|---|---|---|
| BOT1 iron condor | +0.15 pts/cycle, t = 0.06 over 259 cycles 2019-2026; six of eight years lose; break-even win rate 96.43% against a measured 8.5% breach rate. Holdout's 28-of-28 is a zero-breach window. | **retire** |
| BOT2 vertical | Same profile: 28 of 28 on the holdout, zero losing cycles, profitable only in zero-breach regimes. | **retire** |
| BOT6 micro momentum | −61.87% over the holdout at ₹1L; 81.31% max drawdown. Gross edge ~₹59/trade against ~₹75/trade of cost. | **retire** |
| BOT7 displacement | −34.78% over the holdout; 41.52% max drawdown. Seven pre-registered candidates, no survivor. | **retire** |
| BOT8 price action | 1 trade in 248 sessions (+₹311). Not an edge; not enough frequency to be one. | **retire** |

---

## 5b. EXTERNAL SOURCE LEDGER (this run)

Every externally sourced idea is treated as a hypothesis. No performance claim from
any source is reproduced as fact.

| Source | Original market / horizon | Rules taken | Claim | Result here |
|---|---|---|---|---|
| Overnight-return / intraday-reversal literature (Cliff–Cooper–Gulen 2008; Lou–Polk–Skouras 2019) | US equities, daily | the segment split: hold close→open, not open→close | overnight returns dominate total returns | **effect confirmed in NIFTY** at +0.1350%/night, t = 7.02; **not convertible** at retail friction (§3.3) |
| Durgia, "Weekly Behavior of the Nifty Index", SSRN 5353404 | NIFTY weekly, 2015-2025 | expiry-cycle anchor (session after one expiry → next expiry) for systematic option selling | a decade-long statistical basis for weekly option selling | **rejected**: ±2% strangle +8.76 pts/cycle at **t = 0.87**, one of 241 cycles is 49% of profit, worst cycle −1,039 pts. Paper returns HTTP 403 to automated fetch, so only rules implied by its title and abstract were reproduced. |
| Common Indian retail PCR framing ("PCR > 1.3 → reversal") | NIFTY, intraday/daily | the ratio and the thresholds, as hypotheses | high PCR precedes a fall | **direction refuted, information confirmed**: high PCR precedes *continued upward* overnight drift, +31.65 pts at PCR > 1.1 (t = 6.21) |
| Variance-risk-premium framing ("buy vol when IV < realised") | general | VIX-vs-realised filters on a long straddle | cheap vol is a buy | **backwards**: −18.05 pts/day unfiltered, **−32.30 at VRP < 0** (t = −7.04) |
| Expiry-day-effect literature (Indian evidence; NSE/arXiv) | NIFTY/BankNifty | expiry-session return, volume and volatility conditioning | returns and volatility are elevated on expiry | weak: expiry-day overnight drift +0.0927%, **t = 2.09**; dte-based gating did not improve any candidate |

Searched and **not** pursued, with the reason: retail blog and tool listings
(niftytrader, icfmindia, stockmojo, optionbacktesting and similar) describe the same
near-ATM directional and OI-support/resistance setups already covered by the 31
concepts closed in the previous study, and offer no rule this run had not tested. No
claim from them is deterministic enough to reproduce, and none addresses the binding
constraint identified in §3.3, which is instrument economics rather than signal choice.

---

## 6. LIMITATIONS, STATED PLAINLY

1. **Holdout blindness was partially broken for one feature.** See §3.4. Disclosed,
   directionally conservative, and independently corroborated by the control.
2. **The equity universe is survivorship-contaminated.** The 48 price histories are
   the *current* NIFTY 50. At least 20 names entered or left since 2015 and every
   name that left has no price file. Results are measured market-relative to
   cancel the part of the bias that lifts all names equally; the part that biases
   the *ranking* cannot be repaired from the data present.
3. **No intraday data exists for BANKNIFTY or for equities** in this repository, so
   intraday work is NIFTY-only and BANKNIFTY/equities are testable at daily
   frequency only. No single-stock or index **futures** prices exist at all, so
   the cheapest delta-1 instrument could not be tested directly — only its option
   synthetic.
4. **Multi-day equity shorts are not implementable by Indian retail** in cash, so
   every cross-sectional long-short number in §5 row 9 is diagnostic, not tradable.
5. **Lot size is authentic only from 2024** (`NewBrdLotQty`). Pre-2024 results are
   reported in points, never converted to rupees. The entire one-year holdout sits
   inside the authentic-lot era.
6. **Broker margin is estimated, not known**, for any structure with an
   unprotected short leg: 12% of spot per naked leg, flagged wherever used.
7. **No historical bid/ask exists.** Execution is modelled as traded price ±
   (0.30% per side + 2 ticks) plus statutory charges, with 1.5×/2×/3× stress
   reported. The live ATM spread observed on 2026-09-18 was ~0.22%.
8. **The bhavcopy `ClsPric` is a 30-minute weighted average, not a closing print**
   (measured +0.80 points above the 15:2x print for puts, n = 19,828). It is used
   only for a leg being bought, where paying more is the conservative direction.

---

## 7. REPRODUCTION

```bash
python src/research/chain_panel.py                      # option-chain panel, 1,903 x 79
python src/research/equity_panel.py                     # equity cross-section, 124,511 rows
python scripts/research/chain_screen.py                 # DEV predictive screen
python scripts/research/overnight_dev.py                # 31 structures, DEV
python scripts/research/overnight_falsify.py            # concentration/regime/venue/cost
python scripts/research/equity_screen.py                # 80 cross-sectional tests
python scripts/research/overnight_validate.py           # pre-registered gate, VAL
python scripts/research/weekly_cycle_study.py            # weekly short strangle, exact expiry settlement
python scripts/research/money_result_1y.py              # the numbers in section 1
python -m pytest tests/test_research_overnight.py -q    # 25 regression tests
```

Artefacts: `reports/chain_screen_dev.csv`,
`reports/chain_hypotheses_dev.csv`, `reports/overnight_dev.csv`,
`reports/overnight_dev_width.csv`, `reports/overnight_dev_conditional.csv`,
`reports/equity_screen_dev.csv`, `reports/overnight_validation.csv`,
`reports/weekly_cycle_dev.csv`, `reports/money_result_1y.json`.

---

## 8. BOTTOM LINE

Across two prior studies and this one — roughly **226 implementations of 46
distinct concepts** — no strategy in this repository has a validated edge, and
this run establishes *why* rather than merely repeating *that*:

> NIFTY's directional edge is worth about **15 index points a night**. A near-ATM
> weekly option — the only instrument a ₹20,000–₹1,00,000 account can trade at a
> credible spread — gives up about **12 points of theta** to hold it and only
> collects half the move. The structures that collect the whole move need
> **₹1.7 lakh** of margin. The gap between those two numbers is the reason this
> repository has never found money, and closing it needs either futures (no data
> here, and still ₹1.4 lakh of margin) or an edge several times larger than
> anything measured.

The multi-day version fails for the mirror-image reason. Holding premium over a full
weekly cycle amortises the friction, but the ATM straddle costs **1.66% of spot** at
entry while only 41.7% of cycles finish inside ±1% — the market prices the weekly
distribution about right, and the residual is a fat left tail in which one cycle of
241 carries half the profit.

`LIVE_TRADING_ENABLED` remains **false**. Nothing is promoted to paper trading.

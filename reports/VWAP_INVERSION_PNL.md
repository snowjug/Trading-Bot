# THE SURVIVING EDGE, PRICED: NO SURVIVOR

**Run:** 2026-09-27 · **NIFTY 5-minute** · 60-minute hold · authentic traded option premium
**DEV** 2022-01-01 → 2023-12-31 · 616 priced signals · lot 50 (derived, validated)
**VAL** 2024-01-01 → 2025-09-17 · 437 priced signals · lot 50 / 25 / 75 (published)
**HOLDOUT** 2025-09-18 → 2026-09-18 — **NOT TOUCHED**
**Reproduce:** `python scripts/research/vwap_inversion_pnl.py --start <a> --end <b>`
**`LIVE_TRADING_ENABLED`:** `false` · Dhan read-only, market data only

---

## 1. THE QUESTION, AND WHY IT HAD TO BE ASKED

`reports/CALIBRATION_DEV_VS_VAL.md` found exactly one directional result that survived two
independent multi-year windows: **`VWAP_REVERSION` is wrong as a family** — 41.9% hit rate
(z = +2.73) on 2022–2023 and 39.9% (z = +2.86) on 2024–2025. Inverted, that is roughly 60%
directional accuracy.

A hit rate is not a profit. The question this answers is the only one that matters:
**is the move large enough to pay for the option used to capture it?**

### The rule was fixed before the answer existed

Written into the script's docstring and unchanged since:

| | |
|---|---|
| **rule** | at every bar `VWAP_REVERSION` fires, buy the ATM option **opposite** its stated direction |
| **side** | **family-level, both sides.** The side attribution failed validation — `dir=-1` was z = +3.26 on DEV and +1.71 on VAL while `dir=+1` went from +0.04 to +2.48 — so a per-side rule would be fitted to one window |
| **strike** | nearest to spot at entry, held to exit, never re-selected |
| **hold** | 60 minutes, the calibration horizon; same session only |
| **expressions** | two, both declared up front: a long ATM option, and an ATM debit vertical one strike out |
| **multiple testing** | 2 expressions × 2 windows = **4 tests**, stated in advance |
| **unpriceable** | a leg with no authentic traded bar at either end is excluded and counted — never substituted |

### The control is the point

At every signal bar **both** the CE and the PE outcome are computed. `INVERTED` picks one by
the detector's sign, `AS_IS` picks the other, and `UNCONDITIONAL` is their mean — precisely
what picking at random would earn. So `INVERTED − UNCONDITIONAL` isolates the **selection**
edge from the cost of merely being long an option, and `INVERTED + AS_IS = 2 × UNCONDITIONAL`
is an identity the script prints as a self-check. It came out at **+0.00** on every row.

---

## 2. THE RESULT — DEV, LONG ATM OPTION

Rupees per trade. `indep` is the non-overlapping sample the t-stat uses (285 of 616).

| half-spread | rule | mean ₹ | t | win% | total ₹ |
|---|---|---|---|---|---|
| 0.0 | **INVERTED** | **−76** | −1.15 | 47.2 | −27,353 |
| 0.0 | AS_IS | −180 | −2.73 | 28.7 | −140,682 |
| 0.0 | UNCONDITIONAL | −128 | −6.94 | 19.0 | −84,017 |
| 0.5 | **INVERTED** | **−126** | −1.90 | 44.6 | −58,153 |
| 0.5 | AS_IS | −230 | −3.48 | 26.5 | −171,482 |
| 0.5 | UNCONDITIONAL | −178 | −9.65 | 15.6 | −114,817 |
| 1.0 | **INVERTED** | **−176** | −2.65 | 42.7 | −88,953 |
| 1.0 | AS_IS | −280 | −4.24 | 24.7 | −202,282 |
| 1.0 | UNCONDITIONAL | −228 | −12.35 | 13.0 | −145,617 |

Negative at every spread assumption, including **zero spread**, which is the most generous
setting the data permits.

---

## 3. THE USEFUL PART: THE EDGE IS REAL AND IT IS 3.4× TOO SMALL

This is not a bare failure. The decomposition says how far away the edge is.

At half-spread 0.5, lot 50 — dividing rupees by the lot gives premium points:

| | per trade | premium points |
|---|---|---|
| `UNCONDITIONAL` — hold an ATM option 60 min, side chosen at random | −₹178 | **−3.56** |
| `INVERTED` — the rule | −₹126 | −2.52 |
| `AS_IS` — the detector as written | −₹230 | −4.60 |
| **selection edge** = `INVERTED − UNCONDITIONAL` | **+₹52** | **+1.04** |

Three things follow.

1. **The inversion carries genuine directional information.** It is worth **+1.04 premium
   points** per trade, `AS_IS` loses the same amount symmetrically, and the consistency
   identity holds at +0.00. The Brier evidence was not an artefact — it reappears here, in
   money, measured on authentic premium.
2. **The instrument costs 3.56 points.** Theta on a 60-minute ATM hold plus statutory
   friction. That is the bar, and it is set by the option market, not by the setup.
3. **1.04 against 3.56 is short by 2.52 points.** The edge would have to be **3.4× larger**
   to break even. No choice of structure closes a 3.4× gap — which is the same conclusion
   `AGENT_SETUP_EDGE_FINDINGS.md` reached from forward returns, now with a number attached.

---

## 4. THE DEBIT VERTICAL IS STRICTLY WORSE, WHICH IS WORTH RECORDING

"Use a spread to cut the cost" is the obvious instinct. It is wrong here.

| half-spread | rule | mean ₹ | t | win% |
|---|---|---|---|---|
| 0.5 | INVERTED | −222 | **−13.18** | **12.0** |
| 0.5 | AS_IS | −252 | −14.08 | 9.3 |
| 0.5 | UNCONDITIONAL | −237 | −49.02 | 1.3 |

A vertical caps the upside while paying **four** legs of friction instead of two, and its
selection edge collapses from +₹52 to **+₹15**. The 12% win rate is the mechanism: the spread
needs a large move to pay and rarely gets one inside 60 minutes.

Friction here is charged per leg, on each leg's own authentic prices — four orders, with STT
on each leg's actual **sale**, which for the short leg is at entry. Charging a vertical as a
single two-order round trip on its net debit (the first version of this script) understates
brokerage by half and puts STT on the wrong side.

---

## 5. BOTH YEARS, AND THE VALIDATION WINDOW

DEV, `INVERTED`, long ATM option, half-spread 0.5:

| year | n | indep | mean ₹ | t | total ₹ |
|---|---|---|---|---|---|
| 2022 | 331 | 153 | −91 | −0.95 | −9,398 |
| 2023 | 285 | 132 | −167 | −1.85 | −48,755 |

Negative in both. No regime rescued it.

### VAL — the selection edge is LARGER out of sample, and still not enough

VAL was run to complete the record, not to decide anything: DEV was already negative. It
matters anyway, because the selection edge grew.

| half-spread | rule | mean ₹ | t | win% | total ₹ |
|---|---|---|---|---|---|
| 0.0 | **INVERTED** | **−52** | **−0.38** | 43.7 | **+4,746** |
| 0.0 | AS_IS | −311 | −2.62 | 29.5 | −134,740 |
| 0.0 | UNCONDITIONAL | −181 | −3.45 | 30.4 | −64,997 |
| 0.5 | **INVERTED** | **−103** | −0.76 | 42.6 | −17,579 |
| 0.5 | AS_IS | −362 | −3.05 | 26.8 | −157,065 |
| 0.5 | UNCONDITIONAL | −232 | −4.42 | 26.5 | −87,322 |
| 1.0 | **INVERTED** | −154 | −1.14 | 42.3 | −39,904 |
| 1.0 | UNCONDITIONAL | −284 | −5.37 | 23.8 | −109,647 |

**Selection edge = +₹129 per trade**, against **+₹52** on DEV. The inversion's directional
information is not only real, it is *stronger* in the window that did not produce it — which
is the opposite of what an over-fitted finding does. It is still swamped: the instrument costs
₹232 per trade at the same spread.

By year, `INVERTED`, half-spread 0.5: **2024 −₹121** (t = −0.97), **2025 −₹78** (t = −0.29).
Negative in both, as in DEV.

**One wrinkle stated plainly.** At *zero* spread the full-sample total is marginally
**positive** (+₹4,746) while the independent-sample mean is **−₹52 at t = −0.38**. The two
statistics disagree in sign. This is the most favourable of the twelve cells reported here,
it is breakeven at best, and a cell where the point estimate and the total contradict each
other on n = 198 independent observations is what no edge looks like — not a discovery.

VAL rupees are **not** converted to premium points, because the lot changed inside the window
(50 → 25 → 75), so a single divisor would be wrong. The points decomposition in §3 is DEV
only, where the lot was 50 throughout.

---

## 6. DATA QUALITY OF THIS RUN

| | |
|---|---|
| signals detected and priced | 616 (DEV) · 437 (VAL) |
| dropped, forward window crosses a session | 5,928 (DEV) · 5,124 (VAL) |
| dropped, **UNPRICEABLE** option leg | **2** (DEV) · **2** (VAL) |
| dropped, no authentic lot size | **0** in both windows |

The zero is the point: an earlier run of this script dropped **all 90** DEV signals as
`NO_LOT`, because `chain_panel.lot_size` is empty before 2024. It refused rather than
inventing a lot. `src/research/option_lots.py` now supplies one for all 1,904 sessions,
validated 100% against the exchange's published `NewBrdLotQty` on 2,998 (session, expiry)
pairs.

---

## 7. LIMITATIONS

1. **No bid/ask exists in the store.** Historical option bid/ask is not published anywhere in
   scope, so the spread is a *stated assumption*, swept at 0.0 / 0.5 / 1.0 points per side.
   The conclusion does not depend on it — the result is negative at zero.
2. **One hold, one underlying.** NIFTY, 60 minutes. A different horizon changes both the
   theta cost and the realised move; the ratio between them is what would have to change.
3. **The detector's signals, not the agent's trades.** The risk gate and decider filters are
   not applied, so this measures the rule in isolation. Applying them reduces trade count and
   cannot turn a negative mean positive.
4. **Exit at a fixed 60 minutes.** No stop, no target. A stop cannot create edge that is not
   in the forward distribution, but it changes the shape of the loss.
5. **Two expressions, not an exhaustive search.** Both were declared before the run. A third
   would be a third test and would need to be counted as one.

---

## 8. BOTTOM LINE

> The one directional finding that survived two independent windows on forecast accuracy
> **does not survive being priced.** On DEV the inversion is worth about **1 premium point**
> per trade while holding the option costs about **3.6** — short by **3.4×**. On VAL the edge
> is *larger* (+₹129 vs +₹52 per trade), which is the opposite of over-fitting, and still not
> enough against a ₹232 instrument cost.
>
> **NO SURVIVOR.** Not because the signal was absent — it is real, it is measurable in money,
> and it is stronger out of sample than in — but because it is a fraction of the friction
> required to trade it. Negative in all four years, at every spread assumption including
> zero, in both expressions, with the defined-risk vertical worse rather than better.
>
> The useful residue is a **number**: an intraday directional signal on NIFTY has to be worth
> more than roughly **3.5 premium points** per 60-minute round trip before an option can carry
> it. Nothing measured in this repository comes close.

Nothing promoted. No target file edited. `journal/proposals.md`'s `INVERT_FAMILY` entries
have now failed criterion 3 ("the excess move clears the measured option friction"), and that
is recorded against them. `LIVE_TRADING_ENABLED` remains `false`. The
2025-09-18 → 2026-09-18 holdout is untouched.

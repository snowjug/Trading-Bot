# CLEAN-ROOM CYCLE 1 — FINDINGS

**Run:** 2026-09-19 · **Branch:** `main` · **`LIVE_TRADING_ENABLED`: `false`**
**Dhan usage:** read-only market data only. No order, position or other mutation
endpoint was called at any point.

This cycle was asked to find the truth, not to make anything look profitable. It
found three defects that changed published numbers, retracted one claim of its own,
acquired the instrument three previous cycles said did not exist, and rejected the
best-looking candidate the project has produced. Nothing is promoted.

---

## 1. TRUTH TABLE

| Strategy | Instrument | Data valid | Implemented correctly | DEV | VAL | Holdout | Net | Status |
|---|---|---|---|---|---|---|---|---|
| BOT1 iron condor | NIFTY weekly options | yes | **now** (was not) | gross −1.96 pts, t=−0.46, n=83 | +7.36, t=+1.25, n=30 | +10.06, t=+11.26, n=27, 0% breach | 140 cycles gross +2.36 pts vs 2.46 pts cost ⇒ **≈ −0.1** | **REJECTED** |
| BOT2 vertical | NIFTY weekly options | yes | **now** (was not) | gross −0.74, t=−0.15, n=72 | −3.45, t=−0.26, n=19 | +18.57, t=+6.51, n=13 | 104 cycles gross +1.18 vs 1.35 cost | **REJECTED** |
| BOT6 / BOT7 / BOT8 | NIFTY intraday options | yes | yes | — | — | −61.9% / −34.8% / 1 trade in 248 | negative | **RETIRED** |
| Futures overnight | NIFTY near-month future | yes | yes | +0.0302%, t=+1.57, n=1,339 | −0.0006%, t=−0.02 | **−0.0440%, t=−1.08** | +2.27 pts vs **5.71 pts** cost ⇒ **−3.44** | **REJECTED** |
| Futures overnight | BANKNIFTY near-month | yes | yes | +0.0334%, t=+1.42 | +0.0134%, t=+0.46 | **−0.0398%, t=−0.93** | +5.06 vs **12.90** cost ⇒ **−7.83** | **REJECTED** |
| Futures intraday | NIFTY / BANKNIFTY | yes | yes | +0.0069% / +0.0038%, t=+0.33 / +0.13 | — | — | flat | **REJECTED** |
| Stock-futures cross-section, ΔOI | 280 F&O names | yes | yes | LS −0.0941%/day, **t=−4.88**, monotone | not reached | not reached | gross 0.094% vs **0.272%** pair cost | **REJECTED** (signal real, economics impossible) |
| Stock-futures cross-section, short-term reversal | 280 F&O names | yes | yes | mom3 h=1 t=**−0.32** (equity was −3.51) | — | — | effect absent | **REJECTED** — prior result was survivorship |
| BANKNIFTY short strangle, expiry-settled | BANKNIFTY weekly options | yes | yes | **+66.85 pts, t=+2.20**, 295 cycles, positive every year, survives 2× cost | 19 cycles of a **different instrument** | not reached | see §4 | **REJECTED — instrument discontinued** |
| BANKNIFTY iron condor (defined risk) | BANKNIFTY weekly options | yes | yes | +35.26 pts, t=+1.97 at wings +3% | same problem | not reached | dies at 1.5× cost (t=1.26) | **REJECTED** |
| BANKNIFTY intraday option buying | BANKNIFTY options | yes | n/a | not run | — | — | — | **NOT PURSUED — measured reason, §5** |
| Overnight NIFTY options (~90 impl.) | NIFTY options | yes | yes | positive | sign replicated, t<2 | negative | — | REJECTED (previous cycle) |
| Equity cross-section (cash) | 48 current NIFTY-50 names | **NO — survivorship** | yes | alpha 0.085%/day | — | — | below 0.20% STT | **REJECTED + SUPERSEDED** |

**PROMOTED TO PAPER: NONE.**

---

## 2. THE THREE INTAKE AND PARITY DEFECTS

### 2.1 The instrument three cycles called missing was discarded at intake

`scripts/ingest_nse_fo_bhavcopy.py` filters `TckrSymb == "NIFTY"` and
`OptnTp in ("CE","PE")`. The previous cycle's closing limitation —
*"No single-stock or index futures prices exist at all, so the cheapest delta-1
instrument could not be tested"* — was an artefact of that filter. `FUTIDX` for
NIFTY and BANKNIFTY sits in the same file from **2019-01-02** with OHLC, settlement,
open interest and turnover.

Replaced by `scripts/ingest_nse_fo_full.py`. Now held: **25,358 index-futures rows**,
**1,036,863 stock-futures rows**, **6.8M index-option rows** across NIFTY, BANKNIFTY,
FINNIFTY, MIDCPNIFTY, NIFTYNXT50 and NIFTYIT, over 1,904 of 1,905 sessions.

The one missing session is **2021-03-30**: a genuine 404 in NSE's archive on both
hostnames and both layouts, although the index traded that day. Recorded in
`data/catalog/fo_full_ingest_failures.csv`, not papered over.

### 2.2 BOT1 and BOT2 research did not share the live signal functions

`bot_signals.py` states parity is "structural". True for Bots 6/7/8. False for the
weekly bots, whose money numbers came from a reimplementation:

| | BOT1 live | BOT1 research |
|---|---|---|
| wings | 0.6 **expected moves** from the short, so width scales with VIX (150 pts at VIX 10, 350 at VIX 20) | **fixed 200 points** |
| cycles that differed on the one-year holdout | — | **15 of 28** |
| max risk per lot | **₹21,759** | ₹14,630 |

₹14,630 fits a ₹20,000 sleeve; ₹21,759 does not, so the defect sat directly on the
capital-executability answer.

| | BOT2 live | BOT2 research |
|---|---|---|
| side | **RSI ≤ 44 puts, ≥ 62 calls, otherwise NO TRADE** | "further side", **no RSI gate** |
| holdout cycles taken | **5** | 28 |
| side agreed | — | **3 of 28** |
| net per lot | **₹5,623 / 5 cycles** | ₹30,241 / 28 cycles |

`src/research/weekly_parity.py` now *calls* `bot_signals`, so divergence is
structurally impossible. Both bots remain rejected, on honest numbers.

### 2.3 My own ingester committed the defect it was auditing for

The replacement ingester matched only the legacy instrument codes. UDiFF publishes
`IDF`/`STF`/`IDO`/`STO`, not `FUTIDX`/`OPTIDX`, so **670 sessions captured zero rows
and every one was logged `OK`**. Caught only because the futures panel returned 669
sessions instead of 1,904. Fixed with one normalised `InstrmClass` vocabulary, an
explicit `EMPTY_BOTH_BUCKETS` status, and a resume check that requires the output
file to exist rather than trusting a ledger row.

### 2.4 A claim this cycle made and then disproved

This audit first asserted that `TtlTradgVol` changes meaning at the 2024 layout
change. **Wrong.** The turnover identity settles it: legacy NIFTY options give 75.5
and futures 75.1 against a lot of 75, and on UDiFF futures
`TtlTrfVal/(ClsPric×TtlTradgVol)` recovers the published `NewBrdLotQty` to within 1%
on **97.9% of 8,884 rows**. Both eras count contracts; the old rename was correct.

**Useful consequence:** the same identity gives an authentic lot-size calendar for
2019–2026 (`data/catalog/lot_size_calendar.csv`). Recovered change dates — NIFTY
75→50 at 2021-06, →25 at 2024-05, →75 at 2025-01, →65 at 2025-12 — match the
published contract history. Rupee results before 2024 are now possible.

---

## 3. THE CENTRAL RESEARCH FINDING: THE OVERNIGHT EDGE IS A BASIS ARTEFACT

The previous cycle's closing paragraph named futures as the instrument that would
convert a measured ~15 point/night index drift into money. Measured on authentic
futures prints, it does not — and the reason is mechanical, not statistical.

**NIFTY near-month, 1,808 same-contract pairs, 2019–2026:**

| | Value |
|---|---|
| INDEX close → next open | **+16.68 pts** |
| FUTURES close → next open | **+2.25 pts** |
| shortfall | **−14.42 pts** |
| genuine carry decay (1 day at 6%/yr) | only **−2.99 pts** |
| **unexplained by carry** | **−11.44 pts = 69% of the index gap** |
| basis at close | **+39.38 pts** |
| basis at open | **+29.63 pts** |

The futures premium builds through the session and collapses at the open, so a
futures holder never receives most of the index's overnight gap. The
basis-by-days-to-expiry profile is clean carry (11.0 pts at ≤3 DTE rising to 85.3 at
30–60 DTE), which is what validates the decomposition.

In the tradable instrument, both segments are small and insignificant:

| | overnight | t | intraday | t |
|---|---|---|---|---|
| NIFTY futures | +0.0166% (+2.27 pts) | +1.06 | +0.0069% | +0.33 |
| BANKNIFTY futures | +0.0213% (+5.06 pts) | +1.14 | +0.0038% | +0.13 |

And the one-year holdout is **negative** for both (−0.0440%, t=−1.08 and −0.0398%,
t=−0.93). Costs settle it regardless:

| | gross ON | round-trip cost | **net** |
|---|---|---|---|
| NIFTY futures | +2.27 pts | 5.71 pts | **−3.44 pts** |
| BANKNIFTY futures | +5.06 pts | 12.90 pts | **−7.83 pts** |

Futures STT is **0.02% of notional** on the sell side — 3.6 points at NIFTY 18,200
and 8.2 at BANKNIFTY 41,000. The delta-1 instrument removes the option's theta and
replaces it with a notional tax of the same order.

Concentration finishes it: removing the best 10 of 1,809 NIFTY nights takes the total
from +4,115 to **−1,009** points; on BANKNIFTY, +9,150 to **−4,301**.

**So the "overnight positive / intraday negative" asymmetry that three cycles built
on is largely an artefact of the index open and the futures premium cycle.** The
index-level statistic was real; the tradable version of it is not.

---

## 4. THE BEST-LOOKING CANDIDATE, AND WHY IT IS STILL REJECTED

BANKNIFTY weekly short strangle at ±1.5%, held to expiry and settled exactly, so no
exit price is involved at all:

| | DEV (295 cycles, 2019 → 2024-09) |
|---|---|
| expectancy | **+66.85 points / cycle** |
| t | **+2.20** |
| win rate | 73.6% |
| breach rate | 45.4% |
| survives 2× cost | **yes, t=+1.99** |
| positive in every year | **yes** (2019 +30, 2020 +7, 2021 +102, 2022 +117, 2023 +25, 2024 +139) |

Four independent reasons it does not survive:

**1. The instrument no longer exists.** NSE discontinued BANKNIFTY weekly expiries in
November 2024. Days-to-expiry by year: median **6** through 2024, then **27** in 2025
and 2026. DEV is a weekly strategy; the validation window can only contain monthlies,
and there are just 19 and 11 cycles. This is not an unvalidated strategy — it is an
unrunnable one.

**2. Concentration.** Total +19,720 points over 295 cycles. Removing the best 10
leaves a mean of +36.40 (t=1.22); removing the best 20 leaves **+15.31 (t=0.51)**. So
20 of 295 cycles — 6.8% — carry 79% of the profit.

**3. The tail is the strategy.** Worst cycles: **−3,493** points (a +15.6% weekly move
in Feb 2021), −3,252 (COVID, −20.2%), −2,841 (COVID, −13.8%). The worst single cycle
is **10.1× the mean credit** — ₹87,313 at lot 25. Regime split: ex-2020 +79.70
(t=2.95) but ex-2021/22 **+43.46 (t=1.18)**.

**4. The version that fits the capital dies on cost.** A naked strangle needs
**₹215,581 of margin at lot 25** (₹258,697 at lot 30) — outside every level in the
brief. The defined-risk iron condor that does fit:

| structure | n | mean pts | t | max risk | cost ×1.5 | cost ×2.0 |
|---|---|---|---|---|---|---|
| short 1.5%, wings +2% | 295 | +23.96 | +1.68 | **₹12,854** | t=1.26 | t=0.84 |
| short 1.5%, wings +3% | 292 | +35.26 | +1.97 | ₹20,605 | — | — |

and it is negative in 2 of 6 years (2019 −17.65, 2023 −7.65).

---

## 5. WHAT WAS MEASURED RATHER THAN ASSUMED, AND NOT PURSUED

The previous cycle diagnosed NIFTY's intraday failure as range compression. That
diagnosis predicts a higher-range index should do better. **It does not**, and the
measurement is why BANKNIFTY intraday option buying was not given search budget:

| | median session range | median ATM premium | **range / premium** |
|---|---|---|---|
| NIFTY | 0.759% | 0.510% | **1.49×** |
| BANKNIFTY | 0.915% | 0.794% | **1.15×** |

BANKNIFTY moves 21% more and its options cost 56% more, so the ratio that decides
whether a buyer can pay for the premium is **23% worse** than the space already closed
by 31 concepts. Its share of wide opening ranges is double NIFTY's (10.3% vs 5.2%) and
that still does not compensate. The market prices the extra volatility, and then some.

---

## 6. OBSERVED SIGNALS THAT ARE NOT STRATEGIES

Kept separate from profitability, as the directive requires.

**Stock-futures ΔOI, 1-day horizon.** Names whose open interest rose most today
underperform tomorrow. Date-level long-short quintile spread **−0.0941%/day, t=−4.88**,
monotone across quintiles (+0.046, +0.022, +0.009, −0.021, −0.055), on 1,148
non-overlapping dates. **Not a roll artefact** — present at every days-to-expiry
bucket (t=−2.72 to −4.02) and strongest with the roll zone excluded. But it is gone by
day 3 (h=3 t=+0.02), and a same-day long-short round trip costs **0.2715%** against a
0.0941% spread. Only positive at literally zero slippage. Long-only bottom quintile is
+0.0380%/day (t=+3.21) against a one-way cost of 0.1358%. Absent 2019–2020, present
2021–2023, weakening in 2024.

**The equity short-term reversal from the previous cycle does not replicate.** On 280
survivorship-free F&O names it vanishes:

| | equity, 48 current NIFTY-50 names | stock futures, 280 names |
|---|---|---|
| mom2 h=1 | −0.0799%, **t=−3.46** | −0.0322%, t=−1.18 |
| mom3 h=1 | −0.0850%, **t=−3.51** | −0.0092%, t=−0.32 |
| mom5 h=1 | −0.0679%, t=−2.81 | +0.0135%, t=+0.46 |

The previous cycle rejected it on cost (0.085% alpha against 0.20% STT) while
flagging the survivorship contamination. The contamination, not the cost, was the
binding problem: **134 of 348 F&O symbols stop trading long before the end**, and
every one of them was missing from the 48-CSV universe. On a universe that keeps them,
the effect is not there.

---

## 7. DATA NOW HELD THAT WAS NOT BEFORE

| Dataset | Coverage |
|---|---|
| Index futures, daily, all symbols | **25,358 rows**, 1,903 sessions, 2019-01 → 2026-09 |
| Stock futures, daily, 348 symbols | **1,036,863 rows**; 348,613 near-month; **survivorship-free** |
| Index options, daily, 6 underlyings | **6.8M rows** (BANKNIFTY alone 2.8M) |
| **BANKNIFTY 5-minute option grid** | **2,474,196 bars**, 1,271 sessions, 2021-08-04 → 2026-09-18, ATM±6, 309 strikes, iv/oi/spot at 100%, **zero gaps** |
| Authentic lot-size calendar | 270 (symbol, month) rows, 2019–2026, derived from turnover |
| Full Dhan scrip master | 207,159 rows, sha256 recorded |
| Raw bhavcopy zips | 1,904 files, sha256 per file in the ingest ledger |

"Intraday work is NIFTY-only" is refuted. Dhan serves 5-minute option bars with iv,
oi and spot fully populated for BANKNIFTY (floor 2021-08), FINNIFTY (2021-08),
MIDCPNIFTY (2022-01), SENSEX (2023-05) and BANKEX (2023-05), all at ATM±10.

---

## 8. REGRESSION TESTS

`tests/test_research_integrity.py` — **31 tests, one per named failure mode A–L**:
condor-is-four-legs with an adversarial wing-deletion test; complete session
accounting; exit session must be the calendar's next one; DTE equals expiry minus
session; no path treats a print as a fill; identity and price provenance travel with
every leg; lot size NaN before 2024 and never back-filled; epoch→IST lands on the
minute and a bar's date matches its session; **mutating every forward column to −999
leaves the fired-session set identical**; `bot1_condor_real` equals `bot_signals` at
every VIX and a fixed-step wing fails the test; defined risk is width−credit, a naked
short is charged SPAN-scale, and a lot that does not fit yields zero lots rather than
a return.

Plus `tests/test_research_overnight.py` (25). **56 passed, 1 skipped.**

---

## 9. LIMITATIONS

1. Historical **bid/ask does not exist** in any dataset in scope, at any date, for any
   instrument. Execution is modelled and stress-tested at 1.5×/2×/3×.
2. Intraday futures history cannot be built: Dhan serves `/charts/intraday` only for
   **currently listed** contracts in ~90-day windows, and expired contract ids are not
   in the scrip master. **UNTESTABLE, not absent.**
3. Stock options (OPTSTK, 210 underlyings, ~36,000 rows/session) not ingested — a
   budget decision.
4. BSE (SENSEX, BANKEX) bhavcopy not ingested — different archive host.
5. 2021-03-30 is missing from NSE's F&O archive although it was a trading session.
6. `dhan_client._post` returns `None` on an HTTP error, so a caller cannot tell 401
   from empty. This is how an expired token first read as "Dhan has no BANKNIFTY
   data". **Still open.**
7. `multileg_paper_broker` and `dhan_contract_resolver` remain classified **UNKNOWN**.
8. The one-year holdout was read for the futures families in this cycle. It has now
   been consumed for those families and must not be re-used for them.

---

## 10. REPRODUCTION

```bash
python scripts/ingest_nse_fo_full.py --start 2019-01-01 --end 2026-09-18
python scripts/probe/probe_dhan_universe.py --sleep 0.7
python scripts/probe/probe_dhan_depth.py --sleep 0.55 --ladder
python scripts/ingest_dhan_grid_multi.py --underlyings BANKNIFTY --max-offset 6
python scripts/research/futures_overnight_study.py
python src/research/stock_futures_panel.py
python scripts/research/futstk_screen.py
python scripts/research/bn_premium_study.py
python -m pytest tests/test_research_integrity.py tests/test_research_overnight.py -q
```

Artefacts: `data/catalog/` (ingest ledger with per-session sha256, failure ledger,
scrip-master provenance, universe and depth probes, lot-size calendar),
`reports/futures_overnight_study.csv`, `reports/futstk_screen_dev.csv`,
`reports/bn_premium_dev.csv`, `research/CLEAN_ROOM_AUDIT.md`,
`reports/DHAN_DATA_COVERAGE.md`.

---

## 11. BOTTOM LINE

Four cycles and roughly 240 implementations have produced no validated edge, and this
one explains more of the *why* than the previous three:

> Every directional edge measured in this repository has been of the same order as the
> friction required to trade it, and the two largest apparent exceptions were both
> artefacts of the measuring instrument rather than of the market. The index's
> overnight gap is 69% futures-premium reset. The equity reversal effect was
> survivorship. What survives measurement — a one-day ΔOI cross-sectional spread of
> 0.094% against 0.27% of round-trip friction, and a BANKNIFTY weekly premium edge in
> an expiry cycle NSE has since abolished — is real and unmonetisable.

`LIVE_TRADING_ENABLED` remains **false**. Nothing is promoted to paper trading.

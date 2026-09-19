# MASTER RESEARCH STATUS

**Updated:** 2026-09-19 · **Branch:** `main` · **Base SHA:** `ce3c4d3`
**`LIVE_TRADING_ENABLED`:** `false` (verified at runtime)
**Cycle:** CLEAN-ROOM CYCLE 1 — **PHASES 1–7 COMPLETE, NOTHING PROMOTED**
Full findings: `reports/CLEAN_ROOM_CYCLE1_FINDINGS.md` (truth table in §1)

---

## PHASE TRACKER

| # | Phase | Status |
|---|---|---|
| 1 | Repository audit | **DONE** → `research/CLEAN_ROOM_AUDIT.md` |
| 2 | Dhan / market-data audit and acquisition | **DONE** — 1,904/1,905 sessions; token renewed mid-session; BANKNIFTY grid acquired |
| 3 | External research and hypotheses | **DONE for this pass** → `research/EXTERNAL_SOURCES.md` |
| 4 | Research-engine regression testing | **DONE** → `tests/test_research_integrity.py`, 31 passed / 1 skipped |
| 5 | Core strategy-family discovery on DEV | **DONE** — futures overnight/intraday, stock-futures cross-section (19 features × 6 horizons), BANKNIFTY expiry-settled premium |
| 6 | Validation | **DONE** — no candidate reached a gate; the one that came closest is unrunnable (its expiry cycle was abolished) |
| 7 | Falsification | **DONE** — concentration, regime, tail, cost stress, roll-artefact and margin checks all applied |
| 8 | Freeze candidate set | NOT STARTED |
| 9 | FINAL HOLDOUT (one run) | NOT STARTED |
| 10 | Capital study | NOT STARTED |
| 11 | Clean-room reproduction | NOT STARTED |
| 12 | Paper-trading candidate selection | NOT STARTED |

**Nothing may skip to Phase 5 while Phase 2 is incomplete**, except work that does
not need the missing data.

---

## DATA STATUS

| Dataset | Status |
|---|---|
| NIFTY options daily, all strikes, 2019→2026, 4,013,288 rows | HELD |
| NIFTY + India VIX daily, 1,905 sessions | HELD |
| NIFTY options 5-min ATM±6, 1,501 sessions | HELD (vendor ceiling ATM±6) |
| **F&O futures all symbols, daily 2019→2026** | **INGESTING** (~885/1,905 sessions at last check) |
| **Index options BANKNIFTY/FINNIFTY/MIDCPNIFTY/NIFTYNXT50 daily** | **INGESTING**, same pass |
| Full Dhan scrip master, 207,159 rows | HELD, sha256 recorded |
| Equity daily, 48 names 2015→2026 | HELD, **survivorship-contaminated** |
| Intraday for any non-NIFTY underlying | **BLOCKED — Dhan token expired 2026-09-19 08:43:45** |
| BSE (SENSEX / BANKEX) bhavcopy | NOT STARTED (budget) |
| Stock options OPTSTK, 210 underlyings | NOT STARTED (budget) |
| Historical bid/ask, any instrument | **NOT PUBLISHED** anywhere in scope |

Coverage report: `reports/DHAN_DATA_COVERAGE.md`.
Ingest ledger: `data/catalog/fo_full_ingest_ledger.csv` (+ failure ledger).

---

## DEFECTS FOUND THIS CYCLE

| # | Defect | Severity | Status |
|---|---|---|---|
| 1 | Bhavcopy ingester dropped **all futures** and all non-NIFTY underlyings; the previous cycle then reported "no futures data exists" as a data fact | **HIGH** — invalidated a stated limitation and the closing recommendation | **FIXED** — `scripts/ingest_nse_fo_full.py` |
| 2 | BOT1 research wings were a **fixed 200 points**; live wings scale with VIX. 15 of 28 holdout cycles differed; max risk per lot ₹14,630 reported vs ₹21,759 actual | **HIGH** — sat on the capital-executability answer | **FIXED** — `src/research/weekly_parity.py` |
| 3 | BOT2 research had **no RSI gate** and picked the side by distance; live picks by RSI and otherwise does not trade. Research took 28 cycles, live would take 5; net ₹30,241 vs ₹5,623 | **HIGH** — the published BOT2 result is a different strategy | **FIXED** — same module |
| 4 | ~~`TtlTradgVol` semantics differ across the 2024 layout change~~ | — | **RETRACTED — this audit was wrong.** The turnover identity shows the volume column counts CONTRACTS in **both** eras (legacy NIFTY options 75.5, futures 75.1 against a lot of 75; UDiFF futures recovers the published lot to within 1% on 97.9% of 8,884 rows). The old ingester's rename is correct. Kept in the record rather than deleted |
| 5 | `dhan_client._post` returns `None` on HTTP error and logs at debug, so an expired token is indistinguishable from empty data at the call site | MEDIUM | **OPEN** |
| 6 | The claim that historical lot size is "not derivable from VAL_INLAKH/CONTRACTS" is **itself wrong** | MEDIUM | **DISPROVED** — see below |
| 7 | **My own new ingester** matched only the legacy instrument-type codes. UDiFF uses `IDF`/`STF`/`IDO`/`STO`, not `FUTIDX`/`OPTIDX`, so 670 sessions captured **zero rows** and each was logged `OK` | **HIGH** | **FIXED** — unified `InstrmClass`, plus an explicit `EMPTY_BOTH_BUCKETS` status so a day that captures nothing can never be recorded as a success |
| 8 | The ingester's resume set came from the ledger alone, so deleting an output file did not force a re-parse — 1,235 days were skipped with no files on disk | MEDIUM | **FIXED** — resume now requires the parquet to exist |

### Defect 7 detail — I committed the defect I was auditing for

The replacement ingester filtered on `FinInstrmTp in ("FUTIDX","FUTSTK","OPTIDX")`.
Those are the **legacy** codes. UDiFF publishes `IDF` / `STF` / `IDO` / `STO`, so
every session from 2024-01-02 matched nothing, wrote no parquet, and was recorded in
the ledger as `OK` with `fut_rows=0, idxopt_rows=0`. It is the same shape of error as
the one being audited — a silent zero presented as a success — and it was caught only
because the futures panel came back with 669 sessions instead of 1,904.

Both the mapping and the reporting are fixed: instrument classes are normalised into
one vocabulary, and a parsed day that yields nothing in both buckets now returns
`EMPTY_BOTH_BUCKETS:<codes seen>` instead of `OK`.

### Defect 6 detail — pre-2024 lot size is recoverable

Implied lot = `VAL_INLAKH × 1e5 / (CONTRACTS × ClsPric)` on liquid futures
(`CONTRACTS > 1000`) is stable, not unstable:

| Symbol | Window | Monthly median | Monthly std | Authentic value |
|---|---|---|---|---|
| NIFTY | 2019-01 → 2020-02 | 74.91 – 75.09 | 0.16 – 0.43 | **75** |
| BANKNIFTY | 2019-01 → 2020-02 | 19.96 – 20.04 | 0.06 – 0.16 | **20** |

Rounded values across the legacy era: NIFTY {75: 1,336, 50: 867}, BANKNIFTY
{25: 1,394, 20: 711} — i.e. it also detects the lot-size *changes* correctly.

This is a derivation from exchange-published turnover, not a guess, and it unlocks
**rupee-denominated results for 2019–2023**, which every prior study had to report in
points.

**The cross-check has now run and it passes.** On the UDiFF era, where
`NewBrdLotQty` is published, `TtlTrfVal / (ClsPric × TtlTradgVol)` recovers the
published lot to within 1% on **97.9% of 8,884 futures rows**, per symbol:

| Symbol | n | median implied | published values | within 1% |
|---|---|---|---|---|
| NIFTY | 2,007 | 64.99 | 25 / 50 / 65 / 75 | **99.2%** |
| BANKNIFTY | 2,007 | 29.95 | 15 / 30 / 35 | 98.6% |
| FINNIFTY | 1,468 | 59.85 | 25 / 40 / 60 / 65 | 98.0% |
| MIDCPNIFTY | 1,994 | 119.67 | 50 / 75 / 120 / 140 | 96.1% |
| NIFTYNXT50 | 1,384 | 24.94 | 10 / 25 | 97.5% |

The same identity applies to index **options** using strike-notional
(`TtlTrfVal / (StrkPric × TtlTradgVol)`), so the calendar can be built from either
file. **ADOPTED** — but only from the new full-fidelity files, because the existing
NIFTY option store did not retain `TtlTrfVal`.

---

## STRATEGY STATUS

| Bot / family | Parity | DEV | VAL | HOLDOUT | Status |
|---|---|---|---|---|---|
| BOT1 iron condor | **now structural** | gross −1.96 pts, t=−0.46 (n=83) | +7.36, t=+1.25 (n=30) | +10.06, t=+11.26 (n=27), **0.0% breach** | **REJECTED** — 140-cycle gross +2.36 pts, t=+0.83, against 2.46 pts of cost ⇒ net ≈ −0.1 |
| BOT2 vertical | **now structural** | gross −0.74, t=−0.15 (n=72) | −3.45, t=−0.26 (n=19) | +18.57, t=+6.51 (n=13) | **REJECTED** — 104-cycle gross +1.18, t=+0.28, cost 1.35 ⇒ net ≈ −0.17 |
| BOT6 micro momentum | structural | — | — | −61.87% at ₹1L | RETIRED |
| BOT7 displacement | structural | — | — | −34.78% at ₹1L | RETIRED |
| BOT8 price action | structural | — | — | 1 trade in 248 sessions | RETIRED |
| Overnight NIFTY options (all structures) | n/a | positive on DEV | sign replicated, t<2 | negative | REJECTED (previous cycle) |
| **BANKNIFTY / FINNIFTY / MIDCPNIFTY / SENSEX 5-min option grids** | — | — | — | — | **ACQUIRING** — Dhan serves them; floors 2021-08 / 2021-08 / 2022-01 / 2023-05, ATM±10, iv+oi+spot fully populated |
| Equity cross-section | n/a | alpha 0.085%/day | — | — | REJECTED — below 0.20% STT |
| Long / short 1-day volatility | n/a | −18.05 / ≈0 pts | — | — | REJECTED |
| Weekly short strangle (Durgia) | n/a | t=0.87, 1 cycle = 49% of profit | — | — | REJECTED |
| **Futures overnight (close→next open), NIFTY** | authentic bhavcopy prints, 1,809 same-contract pairs | +0.0302% / t=+1.57 (n=1,339) | −0.0006% / t=−0.02 (n=236) | **−0.0440% / t=−1.08, win 46.2%** (n=234) | **REJECTED** — +2.27 pts gross vs **5.71 pts** cost ⇒ **net −3.44 pts**; minus the best 10 nights of 1,809 the total goes negative |
| **Futures overnight, BANKNIFTY** | same, 1,808 pairs | +0.0334% / t=+1.42 | +0.0134% / t=+0.46 | **−0.0398% / t=−0.93** | **REJECTED** — +5.06 pts gross vs **12.90 pts** cost ⇒ **net −7.83 pts** |
| **Futures intraday (open→close)** | same | +0.0069% / t=+0.33 (NIFTY), +0.0038% / t=+0.13 (BN) | — | — | **REJECTED** — flat. The index's "negative intraday" is also an artefact |
| Futures intraday (open→close) | authentic | +0.0069% / +0.0038%, t=+0.33 / +0.13 | — | — | **REJECTED** — flat |
| **Stock-futures ΔOI cross-section** | authentic, survivorship-free | LS **−0.0941%/day, t=−4.88**, monotone, not a roll artefact | not reached | not reached | **REJECTED** — gone by day 3; 0.094% against 0.272% pair cost |
| **Stock-futures short-term reversal** | same | mom3 h=1 **t=−0.32** (equity was −3.51) | — | — | **REJECTED** — the prior equity result was survivorship |
| **BANKNIFTY weekly short strangle, expiry-settled** | authentic | **+66.85 pts, t=+2.20**, 295 cycles, positive every year, survives 2× cost | 19 cycles of a structurally different instrument | not reached | **REJECTED** — NSE abolished BANKNIFTY weeklies in Nov 2024; 20 of 295 cycles carry 79% of profit; naked margin ₹215,581; the defined-risk version that fits ₹20k dies at 1.5× cost |
| BANKNIFTY intraday option buying | authentic | not run | — | — | **NOT PURSUED** — range/premium 1.15× vs NIFTY's 1.49×, i.e. 23% worse than a closed space |
| Futures basis / calendar / cross-index | — | — | — | — | UNTESTED |
| **BANKNIFTY / FINNIFTY / MIDCPNIFTY / NIFTYNXT50 options** | — | — | — | — | **UNTESTED — data arriving** |
| **Stock-futures cross-section** | — | — | — | — | **UNTESTED — data arriving** |

**Promoted to paper: NONE.**

### THE HEADLINE RESEARCH FINDING OF THIS CYCLE

The previous cycle closed by naming futures as the instrument that would make the
measured ~15 point/night overnight drift tradable. **Measured on authentic futures
prints, it does not.**

| Measured on the same 1,173 same-contract pairs, NIFTY near-month | Value |
|---|---|
| INDEX close → next open | **+18.90 pts** |
| FUTURES close → next open | **+4.29 pts** |
| shortfall | **−14.61 pts** |
| of which genuine carry decay (1 day at 6%/yr) | only **−2.46 pts** |
| basis at close (futures − index) | **+24.68 pts** mean |
| basis at open | **+12.21 pts** mean |

The futures premium **builds through the session and collapses at the open**. About
**78% of the index's overnight gap is basis being reset, which a futures holder never
receives.** The basis-by-DTE profile is clean carry (5.8 pts at ≤3 DTE rising to 43.5
at 30–60 DTE), which validates the measurement.

Full history, 1,808 pairs: index gap +16.68 pts, futures gap +2.25 pts, shortfall
−14.42, genuine carry only −2.99 — so **69% of the index's overnight gap is
unexplained by carry and is basis being reset.**

So the "overnight positive / intraday negative" asymmetry that three studies built on
is **largely an artefact of the index open and the futures premium cycle, not a
tradable edge**. In the tradable instrument both segments are small and
insignificant, and in the one-year holdout the overnight leg is **negative**.

And the costs settle it regardless of significance:

| | gross ON | round-trip cost | **net** |
|---|---|---|---|
| NIFTY futures (lot 65, price ~18,200) | +2.27 pts | 5.71 pts | **−3.44 pts** |
| BANKNIFTY futures (lot 25, price ~41,000) | +5.06 pts | 12.90 pts | **−7.83 pts** |

STT on futures is levied on the sell side of **notional** and rose to 0.02% in
October 2024, which alone is 3.6 points at NIFTY 18,200 and 8.2 at BANKNIFTY 41,000.
The delta-1 instrument removes the option's theta and replaces it with a
notional-based tax of the same order. That is the mechanism, and it is why the
previous cycle's closing recommendation does not work.

**Bonus capability unlocked:** `data/catalog/lot_size_calendar.csv` — authentic
lot size per (symbol, month) for NIFTY, BANKNIFTY, FINNIFTY and MIDCPNIFTY,
2019–2026, derived from exchange turnover. The recovered change dates (NIFTY 75 →
50 at 2021-06, → 25 at 2024-05, → 75 at 2025-01, → 65 at 2025-12) match the
published contract history. Rupee results before 2024 are now possible.

---

## COUNTS

| | This cycle | All cycles |
|---|---|---|
| Distinct concepts | 0 new strategy concepts yet (Phase 2) | ~46 |
| Implementations | 0 new | ~226 |
| Candidates promoted | 0 | 0 |
| Holdout runs | 0 | 3 (one per previous cycle) |
| Regression tests added | **31** | 576 + 31 |

---

## KNOWN LIMITATIONS

1. No historical bid/ask exists; execution is modelled and stress-tested at 1.5×/2×/3×.
2. Equity universe is survivorship-contaminated and cannot be repaired from data held.
3. Intraday coverage is NIFTY-only until the Dhan token is renewed.
4. Pre-2024 rupee results remain unavailable until the lot-size derivation is
   cross-checked against the published UDiFF values.
5. `multileg_paper_broker` and `dhan_contract_resolver` are classified UNKNOWN — not
   independently re-derived.
6. Overnight-drift figures are carried from the previous cycle, not re-derived here.

---

## NEXT TASK

See `research/NEXT_SESSION.md`.

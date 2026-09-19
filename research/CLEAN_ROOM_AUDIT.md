# CLEAN-ROOM AUDIT

**Opened:** 2026-09-19 · **Branch:** `main` · **Base SHA:** `ce3c4d3`
**`LIVE_TRADING_ENABLED`:** `false` (verified from `src/config.py` at runtime)
**Method:** nothing in existing documentation is accepted because it says
"validated" or "100% pass". Every classification below is either reproduced
independently in this session or marked `UNKNOWN`.

Classification: **VALID** · **PARTIAL** · **INVALID** · **UNKNOWN** · **UNTESTABLE**

---

## 1. HEADLINE FINDINGS OF THIS AUDIT

Three defects were found that changed reported numbers. Two are in the *intake*,
one is in *research/live parity*. All three are the "data availability reported as
strategy failure" error that PART 17 forbids.

### 1.1 The bhavcopy ingester discarded futures and every non-NIFTY underlying — INVALID

`scripts/ingest_nse_fo_bhavcopy.py` filters to `TckrSymb == "NIFTY"` and
`OptnTp in ("CE","PE")`. Everything else in the file was dropped at intake.

The previous study's stated limitation — *"No single-stock or index **futures**
prices exist at all, so the cheapest delta-1 instrument could not be tested"* —
is therefore **wrong**. The NSE F&O bhavcopy carries `FUTIDX` for NIFTY and
BANKNIFTY from **2019-01-02**, with OHLC, settlement price, open interest and
volume. Verified directly against the legacy archive:

```
INSTRUMENT SYMBOL    EXPIRY_DT   OPEN      CLOSE     SETTLE_PR  OPEN_INT  CONTRACTS
FUTIDX     NIFTY     31-Jan-2019 10909.95  10960.55  10960.55   23345700  88310
FUTIDX     BANKNIFTY 31-Jan-2019 27300.20  27505.65  27505.65    1600160  116461
```

The same file also carries `OPTIDX` for BANKNIFTY, FINNIFTY, MIDCPNIFTY,
NIFTYNXT50 and NIFTYIT — all dropped. A single session (2019-01-02) holds
OPTSTK 35,990 / OPTIDX 3,414 / FUTSTK 597 / FUTIDX 9 rows; the repository kept
only the NIFTY slice of the 3,414.

**Remedy shipped:** `scripts/ingest_nse_fo_full.py` — keeps all futures and all
index options, caches the raw zip byte-for-byte, records URL + sha256 + row counts
per session in `data/catalog/fo_full_ingest_ledger.csv`, and writes any failed day
to a failure ledger rather than continuing silently.

### 1.2 A claim this audit made and then DISPROVED — recorded, not deleted

This audit initially asserted that `TtlTradgVol` changes meaning at 2024-01-02
(UDiFF units vs legacy contracts) and classified the old ingester's rename as a
defect. **That assertion was wrong**, and the correction is kept here rather than
edited away, because a retracted finding is part of the record.

Settled by the turnover identity, not by documentation:

| Check | Result |
|---|---|
| legacy 2019-01-02 NIFTY OPTIDX, `VAL_INLAKH×1e5/(STRIKE×CONTRACTS)` | **75.5** |
| legacy 2019-01-02 NIFTY FUTIDX, `VAL_INLAKH×1e5/(CLOSE×CONTRACTS)` | **75.1** |
| UDiFF FUTIDX, n=8,884, `TtlTrfVal/(ClsPric×TtlTradgVol)` vs published `NewBrdLotQty` | within **1% on 97.9%** of rows |
| UDiFF index options, `TtlTrfVal/(StrkPric×TtlTradgVol)` | equals each row's own lot |

The NIFTY lot was 75 in January 2019, so a ratio of ~75 means the volume column
counts **CONTRACTS in both eras** and turnover is notional. The old rename is
**correct** and cross-era volume series are comparable.

**Useful consequence.** The same identity yields the authentic historical lot size on
every session in both eras, where `NewBrdLotQty` only supplies it from 2024. Rupee
results before 2024 become available from a derivation, not a guess — which also
disposes of the separate claim that lot size "is NOT derivable from
VAL_INLAKH/CONTRACTS".

### 1.3 BOT 1 and BOT 2 research did NOT share the live signal functions — INVALID

`src/execution/bot_signals.py` states: *"Research and live share these functions,
so parity is structural rather than something to be audited later."* That holds for
Bots 6, 7 and 8 (`scripts/research/holdout_6m.frozen()` calls them). It does **not**
hold for the weekly bots, whose money numbers came from
`scripts/research/weekly_premium_lab.py`, a **reimplementation**.

Measured divergence on the one-year holdout (2025-09-18 → 2026-09-18):

| | BOT 1 live (`bot1_apex_vrp`) | BOT 1 research (`weekly_premium_lab`) |
|---|---|---|
| wings | `wing_sd − otm_sd` = 0.6 **expected moves** from the short | **fixed 4 strike steps = 200 points** |
| wing width at VIX 10 / 13 / 18 / 20 | 150 / 200 / 300 / 350 pts | 200 / 200 / 200 / 200 pts |
| cycles where the two disagreed | — | **15 of 28** |
| max risk per lot | **₹21,759** | ₹14,630 |

₹14,630 fits a ₹20,000 sleeve; ₹21,759 does not. The defect sat directly on the
capital-executability answer.

| | BOT 2 live (`bot2_zen_curvature`) | BOT 2 research |
|---|---|---|
| side selection | **RSI ≤ 44 → puts, ≥ 62 → calls, otherwise NO TRADE** | "sell whichever side spot is further from", **no RSI gate** |
| wings | 1.9 vs 1.3 expected moves | **fixed 12 steps = 600 points** |
| cycles taken on the holdout | **5** | 28 |
| side agreed | — | **3 of 28** |
| net per lot | **₹5,623 over 5 cycles** | ₹30,241 over 28 cycles |
| max risk per lot | ₹21,323 | ₹44,366 |

The published "BOT 2: +₹30,241 per lot, 28 of 28 cycles won" describes a strategy
the live system does not implement.

**Remedy shipped:** `src/research/weekly_parity.py` — takes **no strategy
parameters of its own**. It calls `bot_signals.bot1_apex_vrp` /
`bot2_zen_curvature`, resolves whatever legs they return against the authentic
chain, and settles at expiry. Divergence is now structurally impossible.

### 1.4 What the corrected measurement says

Parity-correct BOT 1, 140 cycles 2020–2026, priced on authentic chain closes with
per-side spread and slippage already deducted:

| Window | n | Gross pts/cycle | t | Win% | Breach% |
|---|---|---|---|---|---|
| DEV (→2024-09-17) | 83 | **−1.96** | −0.46 | 90.4 | 9.6 |
| VAL (2024-09-18→2025-09-17) | 30 | +7.36 | +1.25 | 93.3 | 6.7 |
| **HOLDOUT (2025-09-18→2026-09-18)** | 27 | **+10.06** | +11.26 | **100.0** | **0.0** |
| ALL | 140 | **+2.36** | **+0.83** | 92.9 | 7.1 |

Measured statutory cost is **2.46 points per cycle** at the authentic lot, so full-
history **net expectancy is ≈ −0.1 points per cycle**. By year: 2020 +7.65, 2021
+4.69, **2022 −11.29, 2023 −9.07**, 2024 +2.71, 2025 +12.68, 2026 +10.92 — and the
losing years are exactly the years with 13–14% breach rates against 0.0% in
2025–26. Removing the single worst cycle raises the 140-cycle total from +330 to
+568 points, i.e. one cycle carries more than 40% of the gross.

**This independently reproduces the previous conclusion (no edge) by a different
and better-founded route, and simultaneously invalidates the numbers that
conclusion was stated with.** Both facts belong in the record.

---

## 2. COMPONENT CLASSIFICATION

### 2.1 Data intake

| Component | Status | Evidence |
|---|---|---|
| `scripts/ingest_nse_fo_bhavcopy.py` | **INVALID for universe claims, VALID for NIFTY options** | drops futures and all non-NIFTY underlyings (§1.1). Its `CONTRACTS`→`TtlTradgVol` rename is correct (§1.2). It does not retain `TtlTrfVal`, so the lot-size identity cannot be applied to its output |
| `scripts/ingest_nse_fo_full.py` (new) | **VALID** | raw zip cached + sha256; 1,905-session ledger; failure ledger; legacy/UDiFF semantics separated |
| `scripts/ingest_dhan_option_grid.py` | **PARTIAL** | authentic, but ATM±6 by vendor ceiling; truncation is directional (§2.4) |
| `scripts/ingest_nse_index_history.py` | **VALID** | 1,905 sessions; cross-checked to 0.0008 pts over 422 overlapping sessions |
| `src/data/dhan_client.py` | **PARTIAL** | read-only; order routes hard-blocked in `_post`; but failures return `None` and callers render that as "0 rows", which is how an expired token looked like absent data (§3) |
| `src/execution/dhan_scrip_master.py` | **PARTIAL** | cached only the index-option slice (12,310 rows) of a 207,159-row master |
| Full scrip master snapshot (new) | **VALID** | 207,159 rows, sha256 `f656aa8a…`, provenance in `data/catalog/` |

### 2.2 Research engines

| Component | Status | Evidence |
|---|---|---|
| `src/research/bot1_condor_real.py` | **VALID** | four roles resolved independently; refuses on any missing leg; agrees exactly with `bot_signals` at every VIX (test pins this) |
| `scripts/research/weekly_premium_lab.py` | **INVALID as a proxy for BOT1/BOT2** | §1.3. Remains valid as a standalone fixed-wing study, and is kept so earlier reports stay reproducible |
| `src/research/weekly_parity.py` (new) | **VALID** | calls the live signals; full session accounting; settles at expiry so no exit price is needed |
| `src/research/lab2.py` | **VALID** | level-based; exits at bar close; one spot per timestamp so no intrabar ambiguity |
| `src/research/overnight.py` | **VALID** | two-venue pricing, adverse marking, no silent skips, SPAN vs defined-risk margin separated |
| `src/research/chain_panel.py` | **VALID** | expiry-day `SttlmPric` trap guarded; forward columns excluded from `feature_columns` |
| `src/research/equity_panel.py` | **PARTIAL** | correct as written; universe is survivorship-contaminated and says so in its own docstring |
| `scripts/research/holdout_6m.py::frozen` | **VALID** | calls `bot_signals` for Bots 6/7/8 — real parity |

### 2.3 Execution and cost

| Component | Status | Evidence |
|---|---|---|
| `src/execution/cost_model.py` | **VALID** | brokerage, STT, exchange, SEBI, GST, stamp duty all present; `slippage_points` default 0.10 double-counts with engines that already penalise fills, which is conservative and is stated |
| `src/execution/bot_signals.py` | **VALID** | `completed_bars()` is a mechanical no-lookahead guarantee; BOT1 emits four legs with correct roles/sides |
| `src/execution/multileg_paper_broker.py` | **UNKNOWN** | not independently re-derived this session |
| `src/execution/dhan_contract_resolver.py` | **UNKNOWN** | not independently re-derived this session |
| Bid/Ask execution | **UNTESTABLE** | no historical bid/ask exists in any dataset here. Execution is modelled as traded price ± (0.30%/side + 2 ticks); live ATM spread observed 2026-09-18 was ~0.22%. This is a data limitation, not a modelling choice |

### 2.4 Known directional data traps (measured, now guarded)

| Trap | Measurement | Guard |
|---|---|---|
| Expiry-day `SttlmPric` is the **underlying's** settlement, not the option's | priced the ATM straddle at 2× spot | `chain_panel._at` |
| `ClsPric` is NSE's 30-minute VWAP, not the closing print | **+0.80 pts above** the 15:2x print for puts, median, n=19,828 | only used for a leg being bought |
| Exiting at the bhavcopy **opening print** | long ATM+1 call +3.49 pts/night there, **−1.31** five minutes later | `overnight._leg_exit` prefers the 09:20 grid bar |
| 5-minute grid truncated to ATM±6 | dropped nights moved **−185 to −279 pts** vs +19 to +26 for priced nights | bhavcopy fallback, then adverse mark; never a drop |
| `NewBrdLotQty` published only from 2024 | 27.4% row coverage | rupee results refused pre-2024; points used instead |

---

## 3. DHAN ACCESS — BLOCKED, AND HOW THAT WAS DIAGNOSED

The environment's Dhan credentials are present and the client constructs cleanly.
`optionchain/expirylist` returns live data. **Every authenticated data endpoint
returns HTTP 401.**

```
charts/historical    401  DH-901  "Client ID or user generated access token is invalid or expired"
charts/intraday      401  DH-901
charts/rollingoption 401  DH-901
fundlimit            401  DH-901
optionchain/expirylist  200  (18 live NIFTY expiries)
```

Cause, read from the token itself without printing any secret:

```
jwt.iat = 2026-09-18 08:43:45
jwt.exp = 2026-09-19 08:43:45      <-- expired
jwt.tokenConsumerType = SELF
```

**The access token expired at 08:43:45 on 2026-09-19.** Renewing it requires a
Dhan console login, which is the account holder's action; bypassing authentication
is forbidden and was not attempted.

This is exactly the failure mode PART 17 names: the first probe run reported
"0 rows" for every underlying and every endpoint, which reads as *"Dhan has no
BANKNIFTY data"* when the truth is *"the token expired"*. Recorded as
**UNTESTABLE — CREDENTIAL EXPIRED**, never as absent data.

**Consequence for this run:** intraday option/futures acquisition for BANKNIFTY,
FINNIFTY, MIDCPNIFTY, NIFTYNXT50, SENSEX and BANKEX is deferred. Everything on the
public NSE archive needs no authentication and proceeded.

**Defect to fix in the client:** `_post` returns `None` on an HTTP error and logs at
`debug`, so callers cannot distinguish "no data" from "not authorised". A probe must
surface the status code. Tracked in `research/NEXT_SESSION.md`.

---

## 4. PREVIOUS CLAIMS — REPRODUCED, CORRECTED OR STILL OPEN

| Previous claim | Verdict | Evidence |
|---|---|---|
| "No futures prices of any kind exist in this repository" | **WRONG — intake defect** | FUTIDX present from 2019-01-02 (§1.1) |
| "Intraday work is NIFTY-only" | **TRUE of the 5-min grid; WRONG as a universe claim** | BANKNIFTY/FINNIFTY/MIDCPNIFTY OPTIDX are in the daily file |
| "BOT1 +0.15 pts/cycle, t=0.06, 259 cycles" | **CONCLUSION SURVIVES, NUMBER REPLACED** | parity-correct: gross +2.36 pts, t=+0.83, 140 cycles, net ≈ −0.1 after 2.46 pts of cost |
| "BOT2 +₹30,241/lot on the holdout, 28/28" | **INVALID** | the live rule takes 5 of 28 cycles; parity-correct holdout is +₹15,383 over 13 cycles at ₹20,522 max risk |
| "BOT1/BOT2 profitable only in zero-breach regimes" | **CONFIRMED independently** | 0.0% breach in 2025 and 2026; 13–14% in 2022–23, which lost 9–11 pts/cycle |
| Overnight drift +0.1350%/night, t=7.02 | **not re-derived this session** | UNKNOWN pending re-check; the engine that produced it is classified VALID |
| "Iron Condor was actually a short strangle" | **NOT REPRODUCED as a live defect** | `bot1_apex_vrp` and `bot1_condor_real` both emit four independently priced legs; regression tests now pin it |

---

## 5. REGRESSION TESTS SHIPPED

`tests/test_research_integrity.py` — **31 passed, 1 skipped**, one test per named
failure mode:

| Directive | Tests |
|---|---|
| A condor ≠ strangle | 4 legs with ordered distinct strikes; credit must change when a wing is deleted; bounded max loss; every holdout cycle carries 4 priced legs |
| B no silent dropping | traded + skips == sessions given; pricing failures may not be bucketed as `FILTER`; unpriceable is its own outcome |
| C exit timestamp | exit session is always `sess+1` on the calendar, never a later quoted one |
| D/E DTE + expiry | `dte == expiry − session` everywhere; never spans an expiry; all legs share one expiry |
| F bid/ask | no path treats a print as a fill; round trip at an unchanged price always loses |
| G identity | side, strike on the 50-point grid, qty and price provenance travel with every leg |
| H lot size | NaN before 2024 and never backfilled; more than one authentic value seen; mismatched legs refused |
| I timezone | epoch→IST lands on the minute; no bar before 03:00; bar date == session label |
| J lookahead | forward columns withheld; **mutating every forward column to −999 leaves the fired-session set identical** |
| K parity | `bot1_condor_real` == `bot_signals` at every VIX; wing width must vary with VIX, which fails if a fixed-step wing is substituted |
| L margin/capital | defined risk = width − credit; naked charged SPAN-scale; a lot that does not fit yields zero lots, not a return; deployed ≠ account capital |

`tests/test_research_overnight.py` (25) and the pre-existing suite remain green.

---

## 6. OPEN ITEMS

1. **Dhan token expired** — blocks all intraday acquisition beyond NIFTY. User action.
2. `dhan_client._post` swallows HTTP status; a failed call is indistinguishable from
   empty data at the call site.
3. `multileg_paper_broker` and `dhan_contract_resolver` remain **UNKNOWN**.
4. Overnight-drift figures are carried forward from the previous study and have not
   been re-derived in this clean-room pass.
5. Stock options (OPTSTK, 210 underlyings, ~36,000 rows/session) not ingested — a
   budget decision, recorded as such, not a claim of unavailability.

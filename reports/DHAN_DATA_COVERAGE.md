# DHAN / MARKET DATA COVERAGE

**Measured:** 2026-09-19 · **Probe:** `scripts/probe/probe_dhan_universe.py`
**Raw results:** `data/catalog/dhan_universe_probe.json`
**Instrument identities:** resolved from the official Dhan scrip master,
207,159 rows, sha256 `f656aa8afa2976311a5839305a6f5e0e7651beb360850759bf8c082dae0387ea`,
provenance in `data/catalog/scrip_master_provenance.json`. **No security ID in this
document is guessed.**

This file must exist before any strategy family is called unavailable. Where a
dataset is missing, the reason is stated as either **NOT PUBLISHED**,
**VENDOR CEILING**, **CREDENTIAL EXPIRED** or **NOT YET INGESTED (budget)** — never
as "the strategy failed".

---

## 0. DHAN API STATUS — BLOCKED

| Endpoint | HTTP | Result |
|---|---|---|
| `optionchain/expirylist` | **200** | 18 live NIFTY expiries returned |
| `charts/historical` | **401** | `DH-901` invalid/expired token |
| `charts/intraday` | **401** | `DH-901` |
| `charts/rollingoption` | **401** | `DH-901` |
| `fundlimit` | **401** | `DH-901` |

Token claims, read without printing any secret:

```
jwt.iat = 2026-09-18 08:43:45
jwt.exp = 2026-09-19 08:43:45     EXPIRED
jwt.tokenConsumerType = SELF
```

**Every Dhan-sourced row in this document therefore comes from the cache ingested
in earlier sessions, not from a live call.** All *new* acquisition in this session
came from the public NSE archive, which needs no authentication.

Renewing the token is the account holder's action. Authentication was not bypassed.

> The first probe run reported "0 rows" for every underlying and every endpoint.
> Read naively that says *Dhan has no BANKNIFTY data*. It actually said *the token
> expired*. The distinction is the whole point of this file.

---

## 1. CURRENTLY HELD DATASETS

### 1.1 NSE public archive (no authentication required)

| Dataset | Coverage | Rows / files | Status |
|---|---|---|---|
| NIFTY + India VIX daily OHLC | 2019-01-01 → 2026-09-18, 1,905 sessions | — | **VALID**, cross-checked to 0.0008 pts over 422 overlapping sessions |
| NIFTY options daily, all strikes + expiries | 2019-01-01 → 2026-09-17, 1,904 sessions | **4,013,288** | **VALID**; OI at 100% coverage |
| **F&O futures, all symbols (new)** | ingesting 2019-01-01 → 2026-09-18 | ~2.5M expected | **VALID**, `data/raw/nse/fo_futures/` |
| **Index options, all underlyings (new)** | ingesting 2019-01-01 → 2026-09-18 | ~15M expected | **VALID**, `data/raw/nse/fo_idxopt/` |
| Raw bhavcopy zips (provenance) | same | ~1,905 files | sha256 per file in `data/catalog/fo_full_ingest_ledger.csv` |
| ~48 NSE equities + BANKNIFTY + NIFTY IT daily | 2015-01 → 2026-09-16 | 124,511 panel rows | **PARTIAL** — survivorship-contaminated (current NIFTY-50 members only) |

### 1.2 Dhan cache (from earlier sessions)

| Dataset | Coverage | Status |
|---|---|---|
| NIFTY options 5-minute, ATM±6, CE+PE, with `iv` and `oi` | 2020-09-01 → 2026-09-18, **1,501 sessions**, 2,927,769 bars | **PARTIAL** — ATM±6 is a **VENDOR CEILING** on `/charts/rollingoption`, not a data limit |
| NIFTY option chain snapshot | 2026-09-17, one session | **PARTIAL** — single snapshot |
| Marketfeed samples | 2026 | **PARTIAL** |

### 1.3 Field-level coverage matrix, NIFTY options bhavcopy

| Field | Coverage | Note |
|---|---|---|
| `TradDt`, `XpryDt`, `StrkPric`, `OptnTp` | 100% | contract identity complete |
| `OpnPric` | 88.8–100% inside ±5% of spot; **40.3%** beyond +5% | deep OTM often does not trade |
| `ClsPric` | 100% | **NOT the closing print** — NSE's 30-minute VWAP; +0.80 pts above the 15:2x print for puts (median, n=19,828) |
| `SttlmPric` | 100% | on an **expiry** session this is the **underlying's** final settlement, not the option's |
| `OpnIntrst`, `ChngInOpnIntrst` | **100%** | enables PCR / ΔOI / OI walls / max pain |
| `TtlTradgVol` | 100% | **semantics change at 2024-01-02**: UDiFF = units, legacy `CONTRACTS` = contracts. Kept separately as `LegacyContracts` |
| `NewBrdLotQty` | **27.4%** (2024+ only) | **NOT PUBLISHED** before 2024. Rupee results refused pre-2024; points used instead |
| `UndrlygPric` | 27.4% | spot taken from the index archive instead |
| **Bid / Ask** | **0%** | **NOT PUBLISHED** in any dataset here, at any date, for any instrument |
| `iv` (5-min grid only) | present 2020-09+ | vendor-computed |

---

## 2. THE INSTRUMENT UNIVERSE THAT EXISTS

From the scrip master. "Listed contracts" is the count currently listed, not
historical depth.

### 2.1 Index options (OPTIDX)

| Exchange | Underlying | Security ID | Listed contracts | Lot | Daily bhavcopy history | Intraday |
|---|---|---|---|---|---|---|
| NSE | **NIFTY** | 13 | 4,052 | 65 | **2019-01 → 2026-09** | ATM±6, 2020-09+ |
| BSE | **SENSEX** | 51 | 3,156 | 20 | not ingested (BSE archive) | none |
| NSE | **BANKNIFTY** | 25 | 2,342 | 30 | **2019-01 → 2026-09 (new)** | **CREDENTIAL EXPIRED** |
| NSE | **NIFTYNXT50** | 38 | 2,146 | 25 | **new** | CREDENTIAL EXPIRED |
| NSE | **MIDCPNIFTY** | 442 | 1,550 | 120 | **new** | CREDENTIAL EXPIRED |
| NSE | **FINNIFTY** | 27 | 1,122 | 60 | **new** | CREDENTIAL EXPIRED |
| BSE | BANKEX | 69 | 1,000 | 30 | not ingested | none |
| BSE | SENSEX50 | 83 | 422 | 75 | not ingested | none |

### 2.2 Index futures (FUTIDX) — previously believed absent

| Underlying | Listed | Lot | Probe contract | Daily bhavcopy history |
|---|---|---|---|---|
| NIFTY | 3 | 65 | `NIFTY-Sep2026-FUT` id 68407 | **2019-01-02 →** |
| BANKNIFTY | 3 | 30 | `BANKNIFTY-Sep2026-FUT` id 68390 | **2019-01-02 →** |
| FINNIFTY | 3 | 60 | `FINNIFTY-Sep2026-FUT` id 68391 | from listing |
| MIDCPNIFTY | 3 | 120 | `MIDCPNIFTY-Sep2026-FUT` id 68406 | from listing |

12 FUTIDX underlyings and 38 contracts listed in total.

**This is the single most consequential correction in this audit.** The previous
study's closing paragraph named futures as the missing instrument that could convert
the measured overnight drift. Daily futures history has been available in this
repository's own data source since 2019 and was discarded at intake.

### 2.3 Stock derivatives

| Type | Underlyings | Listed contracts | Status |
|---|---|---|---|
| OPTSTK | **210** | ~70,000 | **NOT YET INGESTED (budget)** — ~36,000 rows/session |
| FUTSTK | **228** | 1,270 | ingesting with the futures set |

---

## 3. WHAT IS GENUINELY UNAVAILABLE

| Item | Classification | Consequence |
|---|---|---|
| Historical **bid/ask** for any instrument | **NOT PUBLISHED** | execution must be modelled; a traded print is never treated as a fill |
| Lot size before 2024 | **NOT PUBLISHED** | rupee results impossible pre-2024; points used |
| Intraday bars for any non-NIFTY underlying | **CREDENTIAL EXPIRED** | deferred, not failed |
| Intraday bars for equities | **NOT HELD** | equities testable daily only |
| Options beyond ATM±6 intraday | **VENDOR CEILING** | daily bhavcopy covers all strikes |
| Delisted / index-removed equity histories | **NOT HELD** | equity cross-section is survivorship-contaminated |
| BSE (SENSEX / BANKEX) bhavcopy | **NOT YET INGESTED (budget)** | different archive host |

---

## 4. CROSS-CHECKS PERFORMED

| A | B | Result |
|---|---|---|
| Dhan 5-min grid 09:15 open | NSE bhavcopy `OpnPric` | n=19,358 contract-sessions, **median diff 0.000**, corr **0.978** |
| Dhan 5-min grid 15:2x close | NSE bhavcopy `ClsPric` | n=19,828, median diff **+0.800** — resolved: `ClsPric` is a 30-min VWAP, not a print |
| Dhan index history | repository index files | 422 overlapping sessions, max diff **0.0008 points** |
| Scrip master `SEM_SMST_SECURITY_ID` | bhavcopy `FinInstrmId` | 1,694/1,694 identical (earlier session) |
| Put-call parity implied spot vs actual spot | ATM, 112,703 obs | +6.2 pts at 09:15 rising to +9.6 at 15:25 — consistent with carry decay plus an intraday microstructure drift; recorded, not corrected |

No source disagreement was resolved by silently preferring one side; each row above
states the cause.

---

## 5. REPRODUCTION

```bash
python scripts/probe/probe_dhan_universe.py --sleep 0.7      # needs a live token
python scripts/ingest_nse_fo_full.py --start 2019-01-01 --end 2026-09-18
```

Ledgers: `data/catalog/fo_full_ingest_ledger.csv` (per-session URL, sha256, bytes,
row counts, retrieval timestamp) and `data/catalog/fo_full_ingest_failures.csv`.

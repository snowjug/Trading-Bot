# NEXT SESSION

Read this first. Do not restart from scratch.

**Written:** 2026-09-19 · **Branch:** `main` · **SHA at write time:** `ce3c4d3`
(the commit carrying this file will be the new HEAD — check `git log -1`)
**Working tree at write time:** clean before this cycle's commit
**`LIVE_TRADING_ENABLED`:** `false`

---

## BLOCKER THAT NEEDS THE ACCOUNT HOLDER

**The Dhan access token expired at 2026-09-19 08:43:45.**

```
charts/historical / charts/intraday / charts/rollingoption / fundlimit  ->  HTTP 401 DH-901
optionchain/expirylist                                                 ->  HTTP 200
```

Read from the JWT itself: `iat 2026-09-18 08:43:45`, `exp 2026-09-19 08:43:45`.

Renew it in the Dhan console and set `DHAN_ACCESS_TOKEN` in `.env`. Verify with:

```bash
python -c "import sys;sys.path.insert(0,'.');import requests;from src.config import Config;print(requests.post('https://api.dhan.co/v2/charts/historical',json={'securityId':'13','exchangeSegment':'IDX_I','instrument':'INDEX','fromDate':'2026-08-01','toDate':'2026-09-18'},headers={'access-token':Config.DHAN_ACCESS_TOKEN,'client-id':Config.DHAN_CLIENT_ID,'Content-Type':'application/json'},timeout=30).status_code)"
```

Expect `200`. Until then all intraday work is NIFTY-only, and that is
**UNTESTABLE — CREDENTIAL EXPIRED**, never "no data".

---

## COMPLETED THIS SESSION

1. **Clean-room audit** → `research/CLEAN_ROOM_AUDIT.md`. Three high-severity
   defects found and fixed; every component classified.
2. **Full-fidelity F&O ingester** → `scripts/ingest_nse_fo_full.py`. Keeps all
   futures and all index options; caches raw zips with sha256; per-session ledger;
   failure ledger.
3. **Parity engine** → `src/research/weekly_parity.py`. Measures BOT1/BOT2 by
   *calling* `bot_signals`, so research/live divergence is structurally impossible.
4. **Universe probe** → `scripts/probe/probe_dhan_universe.py` +
   `reports/DHAN_DATA_COVERAGE.md`.
5. **31 regression tests** → `tests/test_research_integrity.py`, one per named
   failure mode A–L.
6. **External ledger** → `research/EXTERNAL_SOURCES.md`.
7. **Plan and status** → `research/DATA_RESEARCH_PLAN.md`,
   `research/MASTER_RESEARCH_STATUS.md`.
8. Corrected BOT1/BOT2 measurements (see the audit; both still REJECTED, but the
   published numbers were wrong).
9. Disproved the claim that pre-2024 lot size is not derivable.

---

## EXACT NEXT TASK

### Step 1 — confirm the ingest finished cleanly
```bash
python -c "import pandas as pd;d=pd.read_csv('data/catalog/fo_full_ingest_ledger.csv',dtype={'day':str});print(d['status'].str.split(':').str[0].value_counts());print('days',d['day'].nunique())"
ls data/catalog/fo_full_ingest_failures.csv 2>/dev/null && echo "FAILURES EXIST - re-run the ingester, it resumes"
```
Re-run `python scripts/ingest_nse_fo_full.py` to pick up any failed day; it is
idempotent and resumes from the ledger.

### Step 2 — cross-check the derived lot size against the published one
The decisive test of the derivation in `MASTER_RESEARCH_STATUS.md` §Defect 6:
compute `VAL_INLAKH × 1e5 / (CONTRACTS × ClsPric)` for 2024+ **legacy-style** rows if
any exist, and separately confirm the UDiFF `NewBrdLotQty` values (NIFTY 25/50/65/75,
BANKNIFTY 15/25/30/35) match the implied values on overlapping months. If they match,
adopt a per-(symbol, month) lot calendar in `data/catalog/lot_size_calendar.csv` and
**rupee results become available for 2019–2023 for the first time**. If they do not
match, keep points-only and record why.

### Step 3 — build the continuous futures series
`src/research/futures_panel.py` (does not exist yet):
- near-month NIFTY and BANKNIFTY, rolled on the **authentic expiry** from the
  bhavcopy, roll rule written into the module docstring
- carry both the un-rolled per-contract series and the rolled series; never splice
  silently
- record basis = future − spot, and the roll gap explicitly
- daily OHLC, settlement, OI, volume, authentic lot

### Step 4 — re-ask the overnight question in futures
This is the highest-value single test in the cycle. The previous cycle's closing
conclusion was that the ~15 point/night drift is real but unconvertible because a
near-ATM option pays ~12 points of theta. Futures have **no theta** and ~2 crossings.
Daily close→close is testable immediately; close→open needs intraday (blocked).
Cost reference to beat: futures STT is 0.02% on the sell side ≈ 4.6 points at
NIFTY 23,000, plus brokerage — so ~6 points round trip against ~15 points of drift.
**Margin is ~₹1.3–1.8 lakh per lot, so report executability honestly at ₹20k/₹50k/₹1L
rather than quietly assuming it fits.**

### Step 5 — then, in order
1. Futures basis / calendar spread / NIFTY-vs-BANKNIFTY relative value.
2. The four new index-option underlyings on the daily horizon.
3. Stock-futures cross-section (avoids the 0.20% delivery STT that killed equities).
4. Freeze → `reports/HOLDOUT_FREEZE.md` → **one** holdout run.

---

## DO NOT REDO

- Intraday NIFTY option buying (31 concepts, ~100 implementations)
- Intraday NIFTY premium selling
- Overnight NIFTY options, unconditional and chain-conditioned (~90 implementations)
- Weekly iron condor / vertical (now also re-measured with parity — still rejected)
- Weekly short strangle settled at expiry (Durgia)
- 0-DTE condor
- Long and short 1-day volatility, including "cheap vol" conditioning
- Daily equity cross-section on the current universe

Details and exact reasons: `reports/ACTIVE_RESEARCH_STATE.md`,
`reports/FINAL_ONE_YEAR_MONEY_STUDY.md`, `research/MASTER_RESEARCH_STATUS.md`.

---

## KEY PATHS

| What | Where |
|---|---|
| Futures, per session | `data/raw/nse/fo_futures/fut_YYYYMMDD.parquet` |
| Index options, per session | `data/raw/nse/fo_idxopt/idxopt_YYYYMMDD.parquet` |
| Raw zips (provenance) | `data/raw/nse/fo_zip/` (gitignored) |
| Ingest ledger | `data/catalog/fo_full_ingest_ledger.csv` |
| Scrip master + provenance | `data/raw/dhan/scrip_master/`, `data/catalog/scrip_master_provenance.json` |
| NIFTY option chain panel | `data/derived/chain_panel.parquet` |
| 5-min grid caches | `data/derived/grid5m_{ce,pe}.parquet` (gitignored, rebuildable) |
| Parity engine | `src/research/weekly_parity.py` |
| Overnight engine | `src/research/overnight.py` |

## COMMANDS

```bash
python scripts/ingest_nse_fo_full.py --start 2019-01-01 --end 2026-09-18   # resumes
python scripts/probe/probe_dhan_universe.py --sleep 0.7                     # needs a token
python -m pytest tests/test_research_integrity.py -q                        # 31 tests
python -m pytest tests/ -q -p no:randomly                                   # full suite
```

## OPEN ISSUES

1. Dhan token expired — user action.
2. `dhan_client._post` hides HTTP status from callers; a probe cannot tell 401 from
   empty. Fix before trusting any future coverage probe.
3. `multileg_paper_broker`, `dhan_contract_resolver` classified UNKNOWN.
4. Overnight-drift numbers carried from the previous cycle, not re-derived.
5. `scripts/research/weekly_premium_lab.py` is retained for reproducibility of older
   reports but must not be used for any new money claim — use `weekly_parity`.

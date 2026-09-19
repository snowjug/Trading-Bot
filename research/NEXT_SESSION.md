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

Cycle 1 is closed. Full findings and the truth table: `reports/CLEAN_ROOM_CYCLE1_FINDINGS.md`.

The Dhan token in `.env` expires **2026-09-20 10:00:13**. Check it first; if it has
lapsed, see the blocker section above.

### Highest-value untested work, in order

1. **FINNIFTY / MIDCPNIFTY / SENSEX 5-minute grids.** Dhan serves them (floors
   2021-08, 2022-01, 2023-05, all ATM±10 with iv/oi/spot at 100%). Acquire with
   `python scripts/ingest_dhan_grid_multi.py --underlyings FINNIFTY,MIDCPNIFTY --max-offset 6`.
   Before spending search budget on any of them, run the **range/premium ratio test**
   first — it is one cheap measurement and it is what ruled BANKNIFTY out
   (§5 of the findings). A ratio below NIFTY's 1.49× means option buying there is
   harder than a space already closed.
2. **Expiry-settled premium selling on underlyings whose weeklies still exist.**
   The BANKNIFTY weekly result (+66.85 pts, t=+2.20, positive every year) was killed
   by NSE abolishing the expiry cycle, not by the statistics. NIFTY and SENSEX still
   have weeklies. Whether the same structure works there is open, and the method
   needs no exit price at all, which is why it is the cleanest test available.
   Watch the tail: the BANKNIFTY version's worst cycle was 10.1× the mean credit.
3. **Futures basis, calendar spreads, and NIFTY-vs-BANKNIFTY relative value.** The
   basis is now measured and behaves like clean carry (11 pts at ≤3 DTE to 85 at
   30–60). A spread has lower variance than either leg, so a smaller edge can clear
   costs — but it pays friction on both legs, so start by computing the break-even.
4. **BSE bhavcopy (SENSEX 3,156 and BANKEX 1,000 listed contracts).** Different
   archive host; entirely untested.
5. **Stock options (OPTSTK, 210 underlyings).** ~36,000 rows/session; skipped on
   budget, not on availability.

### Do this first, before any of the above

Fix `src/data/dhan_client._post`: it returns `None` on an HTTP error and logs at
debug, so a caller cannot distinguish 401 from empty data. That is exactly how an
expired token first read as "Dhan has no BANKNIFTY data". Every coverage probe is
untrustworthy until the status code reaches the call site.

## DO NOT REDO

- Intraday NIFTY option buying (31 concepts, ~100 implementations)
- Intraday NIFTY premium selling
- Overnight NIFTY options, unconditional and chain-conditioned (~90 implementations)
- Weekly iron condor / vertical (now also re-measured with parity — still rejected)
- Weekly short strangle settled at expiry (Durgia)
- 0-DTE condor
- Long and short 1-day volatility, including "cheap vol" conditioning
- Daily equity cross-section on the current universe (and note the reversal effect in
  it was **survivorship**, not a cost problem — it vanishes on 280 survivorship-free
  F&O names: mom3 h=1 goes from t=−3.51 to t=−0.32)
- Futures overnight and intraday, NIFTY and BANKNIFTY (the index's overnight gap is
  69% basis reset; net −3.44 and −7.83 points after cost)
- BANKNIFTY weekly short strangle / iron condor (instrument abolished Nov 2024)
- BANKNIFTY intraday option buying (range/premium 1.15× vs NIFTY 1.49×)

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

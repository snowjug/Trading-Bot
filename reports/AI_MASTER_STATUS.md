# AI MASTER STATUS

**Updated:** 2026-09-18
**Branch:** `rebuild/bots-1-5-6-7`
**Baseline tag:** `pre-master-bots-1-5-6-7` → `749db3e1ef7a4c8d88711490719dc82c56cd3880`
**Current SHA:** (uncommitted work in progress — see AI_HANDOFF.md)
**`main` modified:** NO
**`LIVE_TRADING_ENABLED`:** `false`
**Dhan mutation endpoints called:** NONE (read-only probes only)

---

## CURRENT BOT: 1 — NIFTY Weekly Iron Condor

### Headline change: the Bot 1 data blocker is RESOLVED

The previous verdict — "0.0% of 420 sessions feasible" — was a limitation of ONE
vendor endpoint (DhanHQ `/charts/rollingoption`, which serves only ATM±10), not of
the data. NSE publishes the complete daily F&O UDiFF bhavcopy publicly and
unauthenticated:

| Measured | Value |
|---|---|
| Strike range on 2026-09-16 | 12000 – 34500 (spot ≈ 23200) → ATM±226 strikes |
| All four specified legs present | YES |
| Daily volume at the specified legs | 360k – 650k contracts each |
| Archive reach | UDiFF starts 2024-01-02 (2023-11-01 → 404) |

### Completed
- `scripts/ingest_nse_fo_bhavcopy.py` — read-only ingester, per-session parquet.
- `scripts/ingest_nse_index_history.py` — NIFTY + India VIX OHLC from NSE's public
  `ind_close_all` archive, with a cross-check against the repo's own history.
- `src/research/bot1_condor_real.py` — authentic four-leg condor engine.
  - entry: each leg's own traded close, **only if that contract traded** that day
  - exit: exact cash settlement at expiry vs the exchange's official settlement price
  - costs: `condor_leg_costs()` — side-aware STT (sell-side on premium at entry,
    0.125% exercise STT on ITM longs), entry-only brokerage and slippage
  - entry rule: exactly 5 trading sessions to expiry (the faithful reading of
    `df.iloc[i+1:i+6]` + `sqrt(5/365)`), decided from the spec before results
- `scripts/run_bot1_real_condor.py` — runner + causal-lag sensitivity.

### Current research result (PARTIAL DATA — 223 of 423 sessions)
| | as specified | causal lag-1 |
|---|---|---|
| trades | 20 | 21 |
| win rate | 100.00% | 100.00% |
| breach rate | 0.00% | 0.00% |
| avg credit | 13.62 pts (₹885/lot) | 14.56 pts |
| avg max loss | 228.88 pts (₹14,877/lot) | 235.44 pts |
| net per lot | ₹17,864 | ₹20,222 |

**This is NOT evidence of edge.** Risk/reward is ≈ 1:17, so break-even needs a
breach rate under ~5.9%. A 0/20 observation has a 95% upper bound near 16.8%,
which comfortably includes strongly negative rates.

**Disclosure:** an earlier calendar-window variant (DTE 3–9) produced 26 trades
with 2 breaches, including a −₹14,094 loss on 2025-04-03. The canonical
5-trading-session rule excludes that entry because its expiry was 4 sessions
away. Both variants are reported; the 100% win rate is partly an artefact of the
entry-window definition.

### Validation status
NOT YET RUN — deliberately deferred until the full sample is ingested.

### Test count
Unchanged from baseline (419) — new Bot 1 tests not yet written.

### Current blocker
None blocking. Sample size is the open question, being addressed by extending the
history to 2024-01-02.

### Exact next action
1. Finish bhavcopy ingest to 423/423, then extend it back to 2024-01-02.
2. Re-run the full backtest; run the validation battery (OOS, walk-forward, cost
   and slippage sensitivity, regime, placebo, Monte Carlo, breach-rate CI).
3. Write Bot 1 tests; commit checkpoint.

---

## EXTERNAL DEPENDENCIES

| Dependency | Status | Impact |
|---|---|---|
| Dhan access token | **EXPIRED** — `/charts/historical` → 401 DH-901 (verified 2026-09-18) | Does NOT block Bot 1 any more; NSE's public archive supersedes it. Still blocks live quote work. |
| NSE UDiFF archive | Reachable | Starts 2024-01-02; earlier sessions use a different, older format |

---

## BOTS 5, 6, 7
Not started in this session. See AI_HANDOFF.md for what must not be repeated.

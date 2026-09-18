# AI MASTER STATUS

**Updated:** 2026-09-18 (after Dhan token renewal)
**Branch:** `rebuild/bots-1-5-6-7`
**Baseline tag:** `pre-master-bots-1-5-6-7` → `749db3e1ef7a4c8d88711490719dc82c56cd3880`
**Last checkpoint:** `9d7b85f` — Bot 1 real condor
**`main` modified:** NO
**`LIVE_TRADING_ENABLED`:** `false`
**Dhan mutation endpoints called:** NONE. Read-only only: `/charts/historical`,
`/charts/intraday`, `/charts/rollingoption`.

---

## DHAN TOKEN RENEWED — RE-PROBE RESULTS

Token valid 2026-09-18 08:43 → **2026-09-19 08:43 (≈24h)**. Everything previously
recorded as "blocked by an expired token" was re-measured.

### The previous "10 sessions of option data" was a caching artefact, not a limit

| Probe | Previous belief | **Measured 2026-09-18** |
|---|---|---|
| `/charts/rollingoption` history | 10 sessions | **2020-09 → today (~6 years)**; 2019-09 empty |
| Request window | unknown | **one month**; a quarter or longer returns empty |
| Strike ceiling | ATM±10 | **ATM±10 confirmed, and stable across 2021 / 2023 / 2026** |
| Option side | both in one call | CALL populates `ce`, PUT populates `pe` — **two calls** |
| `expiryCode` | near only | **1, 2 and 3 all serve data**; `expiryFlag=MONTH` also works |
| `/charts/intraday` with an OPTION securityId | untested | **WORKS, and reaches ATM+17** — 74 bars/session at 5-min |
| Expired contracts via `/charts/intraday` | untested | **0 rows — listed contracts only** |
| bhavcopy `FinInstrmId` vs Dhan `securityId` | untested | **identical: 1694/1694 = 100%** |

### Consequences
- **Bots 5/6:** the intraday blocker is **RESOLVED**. Ingesting ATM±6 × CE/PE ×
  5-minute from 2020-09; ATM alone already yields **1,240 sessions** (was 10).
- **Bot 1:** the ATM±10 ceiling is real and stable, so `/charts/rollingoption`
  still cannot serve the 1.8/2.4-SD legs (~ATM±13/±17). `/charts/intraday` can
  serve those strikes but **only while listed**, so it cannot backfill history.
  Bot 1's historical pricing therefore stays on the NSE bhavcopy (daily), which
  is complete.

---

## BOT 1 — NIFTY Weekly Iron Condor

### Data blocker: RESOLVED
NSE's public F&O bhavcopy carries every strike (12000–34500 vs a ~23200 spot) with
six-figure volume at exactly the specified legs. Ingest covers **2019 → 2026**
(UDiFF from 2024-01-02, legacy layout before it). Index + VIX history ingested from
NSE's public `ind_close_all` archive and **independently cross-checked** against the
repo's own files: 422 overlapping sessions, max diff 0.0008 points, none over 0.1%.

### Execution question: MEASURED, and my earlier bound was too pessimistic
The first adverse-fill test priced entries at the worst tick of the whole session
and every variant flipped negative. That bound is wrong for a strategy that enters
at the CLOSE. Measured on 5-minute bars at the exact offsets Bot 1 uses:

- the daily close fell inside the **closing half-hour range on 223/223** observations
- that half-hour span averaged **17.7%** of the full-day span on weekly contracts

So the close is an achievable fill. The realistic adverse band is ~1 point per leg,
where the strategy stays positive but thin (+₹19,060/lot at +1.0 pt/leg vs
+₹32,260 at the close). The full-day bound is retained as a floor, labelled as such.

### Research result (2025–2026, 44 trades, canonical entry)
| | value |
|---|---|
| win rate | 97.73% |
| net per lot | ₹32,260 |
| avg credit | 12.45 pts (₹809/lot) |
| avg max loss | 226.19 pts (₹14,702/lot) |
| break-even breach rate | **4.51%** |
| observed breach rate | 1/44 = 2.27%, **CI95 [0.06%, 12.02%]** |
| **verdict** | **NOT_DISTINGUISHABLE** |

All four variants return NOT_DISTINGUISHABLE. OOS 70/30 agrees in sign, 4/4
walk-forward folds positive — but none of that resolves the tail.

### Structural finding (reported, deliberately NOT "fixed")
`exp_move` uses `sqrt(5/365)` while the position is held ~7 calendar days. The true
holding-period sigma is 1.183× larger, so a strike labelled **1.8 SD actually sits
at ~1.52 SD**. Correcting the formula would change the strategy, so it is reported
as-is. **Strategy-owner decision required.**

### Exact blocker
**Sample size.** ~320 trades (~7 years of weekly cycles) are needed before the
breach-rate CI can clear break-even. The 2019–2026 ingest in flight should supply
roughly that; the full-history rerun is the next step.

---

## BOTS 5 / 6 — status
Ingest of the 5-minute option grid in progress (ATM±6, CE+PE, 2020-09 →). Model and
validation not yet rerun on it. **Do not rerun the old n=8 / n=3 result — it is
superseded.**

## BOT 7 — not started.

---

## TEST COUNT
419 baseline + 32 Bot 1 = **451**, all passing.

## EXACT NEXT ACTION
1. Finish the bhavcopy (2019–2024) and option-grid ingests.
2. Rerun Bot 1 validation on the full 2019–2026 history; compare with the
   2025–2026 result recorded above.
3. Rebuild Bot 5/6 real option economics on the new grid and revalidate.

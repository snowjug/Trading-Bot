# AI HANDOFF

Read this before touching anything. It exists so a new session does not repeat
finished work or re-litigate settled decisions.

**Branch:** `rebuild/bots-1-5-6-7`
**Recovery tag:** `pre-master-bots-1-5-6-7` -> `749db3e`
**`main` must not be modified.** Do not merge automatically. Never force-push.

---

## THE ONE-PARAGRAPH SUMMARY

Bots 1, 5, 6 and 7 have all been taken to a specific, evidenced stopping point on
authentic multi-year exchange data. **None has a usable edge.** Bot 1 nets +2.90
points per weekly cycle at t=+1.40 (indistinguishable from zero). Bot 5's signal is
directionally wrong (43.4% correct against a 33.3% requirement). Bot 6 has the only
positive gross edge in the repository and transaction costs consume all of it.
Bot 7 ran seven pre-registered candidates and none survived. **The remaining open
items are strategy-owner decisions, not engineering work.**

---

## ALREADY COMPLETED - DO NOT REDO

### Inherited from earlier sessions (on `main` at `749db3e`)
- Universal RiskEngine gate, AST-verified, 8/8 entries, 0 raw. **Do not re-audit.**
- Broker reconciliation, 4 canonical states; Dhan mutation barrier over
  POST/PUT/PATCH/DELETE for orders/trades/super/forever/positions.
- IST epoch handling; post-close candle exclusion; index staleness gating.
- Kill-switch and EOD fill fabrication removed.
- State-corruption fail-closed; O_EXCL PID lock; new-day rollover.
- Bot 5 same-bar leakage removed (17/393 -> 0/393); Bot 6 verified causal.

### Done in this mission
- **Bot 1**: real four-leg condor on NSE bhavcopy; full 2019-2026 study; report.
- **Bots 5/6**: real option economics on 1,495 sessions of 5-minute bars; report.
- **Bot 7**: ledger, 7 candidates, all rejected; C6 artefact documented in full.
- Four defects found and fixed (see below).

---

## DECISIONS ALREADY MADE - DO NOT RE-OPEN

1. **Bot 1 is a four-leg Iron Condor, not a strangle.** Evidence: class name, the
   hypothesis text, the `wing_sd=2.4` parameter, and the four-leg
   `OptionsStructure.simulate_iron_condor`.
2. **Bot 1 entry = exactly 5 trading sessions before expiry.** `df.iloc[i+1:i+6]`
   and `sqrt(5/365)` both mean five sessions. Fixed from the spec before results.
3. **Expiry exit = exact cash settlement.** Do NOT use the expiry-day `ClsPric`:
   untraded contracts deviate from intrinsic by up to 627.90 vs 1.38 mean for
   traded ones. The 2019-2020 legacy archive publishes `SETTLE_PR = 0.0`, so the
   NSE index close is used there - **verified identical on 90/90 sessions**.
4. **A leg that did not trade cannot be filled.** `TtlTradgVol > 0` is required.
5. **Costs are side-aware.** `condor_leg_costs()` charges sell-side STT on the
   premium received at entry and 0.125% exercise STT on ITM longs. It is
   legitimately CHEAPER than the naive roundtrip helper because holding to a cash
   settlement involves no exit order; that optimism is bounded by the slippage sweep.
6. **Per-lot / per-point economics are the headline.** SPAN margin is not
   obtainable read-only. The old `margin_per_lot = 55000.0` is fabricated.
7. **Bot 6 is FROZEN.** Nothing about its strategy was changed, and nothing should be.

---

## DHAN - MEASURED 2026-09-18, DO NOT RE-PROBE

| Fact | Value |
|---|---|
| `/charts/rollingoption` history floor | 2020-09 (2019-09 empty) |
| Request window | one month; longer returns empty |
| Strike ceiling | **ATM+/-10**, stable across 2021 / 2023 / 2026 |
| Option side | CALL -> `ce`, PUT -> `pe`; two calls |
| `/charts/intraday` with an option securityId | works, reaches ATM+17 |
| Expired contracts via `/charts/intraday` | **0 rows - listed only** |
| bhavcopy `FinInstrmId` vs Dhan `securityId` | identical, 1694/1694 |

The token the user supplied expires **2026-09-19 08:43**. Do not try to refresh it
- ask the user. Everything above is already measured and cached; the ingested data
does not need the token again.

---

## DEFECTS FIXED IN THIS SESSION - keep the regression tests

1. **Live-path `KeyError` crash** - `trade["target_premium"]` read directly at four
   sites; a restored position without the key aborted evaluation for EVERY bot in
   the cycle. Now `protective_level()`, failing closed.
   Tests: `test_missing_protective_level_fails_closed_instead_of_crashing`,
   `test_no_bot_reads_a_protective_level_unguarded`.
2. **Muhurat sessions** - four evening-only sessions (18:00-19:15) in the option
   grid. Test: `test_muhurat_sessions_are_excluded`.
3. **Silent-skip selection bias** - the C6 artefact. Tests:
   `test_quote_exit_version_skips_exactly_the_big_moves`,
   `test_settled_version_reaches_realistic_losses`.
4. **Non-terminating simulations** - `ChainIndex` and the grid session index.

---

## CORRECTIONS TO EARLIER CLAIMS IN THIS BRANCH

- "Every Bot 1 variant flips negative under adverse fills" used the worst tick of
  the WHOLE session, wrong for a close-entry strategy. The close sat inside the
  closing half-hour range on **223/223** observations at Bot 1's own strike
  offsets; that window spans 17.7% of the day. The close is achievable.
- "`condor_leg_costs()` makes costs higher" - it makes them lower, for a legitimate
  reason (no exit order on a cash settlement). Pinned by test.

---

## MUST NOT BE REPEATED

- Do not re-run the "Bot 1 has no data" analysis, or re-derive the ATM+/-10 limit.
- Do not re-audit the risk gate, reconciliation or Dhan safety barrier.
- Do not redesign Bot 6 or change its parameters.
- Do not cite the old n=8 / n=3 Bot 5/6 result - it is superseded.
- Do not tune `otm_sd`, `wing_sd`, `max_vix`, RSI bands or hold periods.
- **Do not trust any simulation that silently skips sessions.** C6 produced
  t=+12.8 out of nothing that way. Always compare what was dropped against what
  was kept.

---

## OPEN ITEMS - ALL STRATEGY-OWNER DECISIONS

| Item | Nature |
|---|---|
| Bot 1 RSI band | class declares 40/68, simulator hardcodes 38/70 |
| Bot 1 time scaling | `sqrt(5/365)` over a ~7-day hold puts the "1.8 SD" short at ~1.52 SD |
| Bot 1 margin basis | SPAN unverifiable read-only |
| Bot 6 target | hit 3 times in 187 trades; effectively unreachable intraday |
| Whether to continue at all | three of four bots have a negative or zero net edge on authentic multi-year data |
| No bid/ask history anywhere | every fill is a traded-price approximation |
| Bots 3/4 h3 test failures | date-sensitive; Bots 2/3/4 out of scope for this mission |
| `get_upcoming_weekly_expiry()` | assumes Thursday; live path uses Scrip Master so unaffected, but the helper is stale |

---

## CURRENT TASK
None in flight.

## EXACT NEXT STEP
Await a strategy-owner decision on the items above. No further code change should
be started without explicit direction.

## LATEST CHECKPOINT
See `git log` on `rebuild/bots-1-5-6-7`.

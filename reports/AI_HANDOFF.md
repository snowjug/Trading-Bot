# AI HANDOFF

Read this before touching anything. It exists so a new session does not repeat
work that is already finished or re-litigate settled decisions.

**Branch:** `rebuild/bots-1-5-6-7`
**Recovery tag:** `pre-master-bots-1-5-6-7` → `749db3e`
**`main` must not be modified.** Do not merge automatically. Never force-push.

---

## ALREADY COMPLETED — DO NOT REDO

### Inherited from earlier sessions (already on `main` at `749db3e`)
- Universal RiskEngine gate: all 8 entry sites route through `_risk_gated_entry`,
  AST-verified, 0 raw entries. **Do not re-audit.**
- Broker reconciliation with 4 canonical states; Dhan mutation barrier covering
  POST/PUT/PATCH/DELETE over orders/trades/super/forever/positions.
- IST epoch handling fixed at 3 sites; post-close candle exclusion; index
  staleness gating.
- Kill-switch and EOD fill fabrication removed (`UNRESOLVED_KILL_SWITCH`,
  `EOD_UNRESOLVED_NO_EXECUTABLE_QUOTE`).
- State-corruption fail-closed; O_EXCL PID session lock; new-day rollover.
- Bot 5 same-bar leakage removed (17/393 → 0/393) via
  `src/research/bot5_point_in_time.py`; live binding uses that causal provider.
- Bot 6 verified causal and **frozen**.
- 419 tests passing at `749db3e`.

### Done in THIS session
- Recovery tag + branch created.
- **Bot 1's data blocker is resolved.** Do not re-derive the ATM±10 limit — it is
  real, but it is a DhanHQ `/charts/rollingoption` limit only. NSE's public UDiFF
  bhavcopy carries every strike (12000–34500) with six-figure volume at exactly
  the legs the strategy specifies.
- `scripts/ingest_nse_fo_bhavcopy.py`, `scripts/ingest_nse_index_history.py`,
  `src/research/bot1_condor_real.py`, `scripts/run_bot1_real_condor.py`.

---

## DECISIONS ALREADY MADE — DO NOT RE-OPEN

1. **Bot 1 is a four-leg Iron Condor, not a strangle.** Evidence: class name,
   the hypothesis text ("Call & Put spreads … hedged wings"), the `wing_sd=2.4`
   parameter, and the four-leg `OptionsStructure.simulate_iron_condor`. The
   two-strike `simulate_weekly_condors` is a degraded implementation of it.
   Building the four legs is implementing the spec, not inventing one.

2. **Entry timing = exactly 5 trading sessions before expiry.** `df.iloc[i+1:i+6]`
   and `sqrt(5/365)` both mean five trading sessions. Decided from the spec
   before any result was seen. The calendar-DTE variant is kept only as a
   sensitivity control.

3. **Expiry exit = exact cash settlement** against the exchange's official
   settlement price, which the expiry-day bhavcopy carries in `SttlmPric` (a
   single value across all rows). Do NOT use the expiry-day `ClsPric`: for
   untraded contracts it deviates from intrinsic by up to 627.90, versus 1.38
   mean for traded ones.

4. **A leg that did not trade cannot be filled.** `TtlTradgVol > 0` is required
   on every leg at entry. Do not relax this.

5. **Costs are side-aware.** `IndianCostModel.calculate_roundtrip_costs` assumes
   buy-then-sell, which charges a short leg's STT on its exit — near zero for an
   option expiring worthless. `condor_leg_costs()` charges sell-side STT on the
   premium received at entry and 0.125% exercise STT on ITM longs.
   It is nonetheless CHEAPER overall than the naive helper, because holding to
   a cash settlement involves no exit ORDER — one brokerage charge and one
   slippage event per leg instead of two. That optimism is bounded by the
   slippage sensitivity, which prices 0.25-2.0 extra points per leg, far more
   than a second brokerage charge. (An earlier note here claimed the opposite;
   `test_short_leg_stt_is_charged_on_the_premium_received` pins the real behaviour.)

6. **Per-lot economics are the headline.** SPAN margin is not obtainable
   read-only, so no portfolio-scale number may depend on it. The old
   `margin_per_lot = 55000.0` is fabricated.

---

## MUST NOT BE REPEATED

- Do not re-run the "Bot 1 has no data" analysis. It is superseded.
- Do not re-audit the risk gate, reconciliation or Dhan safety barrier.
- Do not redesign Bot 6 or change its parameters. It is a protected baseline and
  is frozen absent a PROVEN defect.
- The Dhan token was RENEWED by the user on 2026-09-18 and is valid until
  2026-09-19 08:43. Do not re-probe what is already measured below; do not try to
  refresh it yourself — ask the user if it lapses again.
- Do not tune `otm_sd`, `wing_sd`, `max_vix`, the RSI band, or the hold period to
  improve results.

---

## DHAN RE-PROBE — MEASURED 2026-09-18, DO NOT REPEAT

| Fact | Value |
|---|---|
| `/charts/rollingoption` history floor | **2020-09** (2019-09 empty) |
| Request window | **one month** — longer returns empty |
| Strike ceiling | **ATM±10**, stable across 2021 / 2023 / 2026 |
| Option side | CALL → `ce`, PUT → `pe`; two separate calls |
| `expiryCode` 1/2/3 and `expiryFlag=MONTH` | all serve data |
| `/charts/intraday` with an option securityId | **works, reaches ATM+17** |
| Expired contracts via `/charts/intraday` | **0 rows — listed only** |
| bhavcopy `FinInstrmId` vs Dhan `securityId` | **identical, 1694/1694** |

Consequence: Bot 5/6's intraday blocker is resolved (~6 years of 5-min bars).
Bot 1's far strikes remain unreachable intraday for HISTORICAL sessions, so its
historical pricing stays on the daily bhavcopy.

## CORRECTION TO AN EARLIER FINDING IN THIS SESSION

The first adverse-fill test priced entries at the worst tick of the WHOLE session
and concluded every Bot 1 variant flips negative. That bound is wrong for a
close-entry strategy. Measured at the exact offsets Bot 1 uses: the daily close sat
inside the closing half-hour range on **223/223** observations, and that half-hour
span averaged **17.7%** of the full-day span. The close is achievable; the realistic
adverse band is ~1 point per leg. The full-day figure is kept only as a floor.

## KNOWN OPEN ITEMS

| Item | Nature |
|---|---|
| Bot 1 sample size | THE binding blocker: ~320 trades (~7 yrs) needed for a conclusive breach-rate CI; 2019-2026 ingest should supply it |
| Bot 1 time scaling | `sqrt(5/365)` over a ~7-day hold puts the "1.8 SD" short at ~1.52 SD — reported, NOT corrected. **Strategy-owner decision** |
| Bot 1 RSI band inconsistency | class declares 40/68, `simulate_weekly_condors` hardcodes 38/70 — **strategy-owner decision** |
| Bot 1 margin basis | SPAN unverifiable read-only |
| No bid/ask history anywhere | all option fills are traded-price approximations; the closing-window measurement bounds the error for Bot 1 |
| Bots 3/4 cannot enter | settled-bar requirement vs pre-15:10 windows (out of scope here) |
| `get_upcoming_weekly_expiry()` | assumes Thursday; returns 2026-09-24 while Scrip Master gives Tuesday 2026-09-22. Live path uses Scrip Master, so unaffected — but the helper is stale |

---

## CURRENT TASK
Bot 1 full-history rerun, then Bot 5/6 on the new 5-minute grid.

## EXACT NEXT STEP
1. Let `scripts/ingest_nse_fo_bhavcopy.py` (2019-2024) and
   `scripts/ingest_dhan_option_grid.py` finish.
2. `python scripts/validate_bot1_condor.py` on the full 2019-2026 history and
   compare against the 2025-2026 numbers in AI_MASTER_STATUS.md.
3. Rebuild Bot 5/6 option economics on `data/raw/dhan/option_grid_5m` and
   revalidate. The old n=8 / n=3 result is SUPERSEDED — do not cite it.

## LATEST CHECKPOINT SHA
`9d7b85f` — Bot 1 real four-leg condor, 32 tests passing.

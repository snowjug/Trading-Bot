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
   premium received at entry and 0.125% exercise STT on ITM longs. This makes
   costs HIGHER, not lower.

6. **Per-lot economics are the headline.** SPAN margin is not obtainable
   read-only, so no portfolio-scale number may depend on it. The old
   `margin_per_lot = 55000.0` is fabricated.

---

## MUST NOT BE REPEATED

- Do not re-run the "Bot 1 has no data" analysis. It is superseded.
- Do not re-audit the risk gate, reconciliation or Dhan safety barrier.
- Do not redesign Bot 6 or change its parameters. It is a protected baseline and
  is frozen absent a PROVEN defect.
- Do not try to renew, work around or bypass the Dhan token. It is expired
  (401 DH-901, verified 2026-09-18); that is an external dependency to report.
- Do not tune `otm_sd`, `wing_sd`, `max_vix`, the RSI band, or the hold period to
  improve results.

---

## KNOWN OPEN ITEMS

| Item | Nature |
|---|---|
| Bot 1 sample size | ~1 trade/week caps the sample near 85 over 20 months; being extended to 2024-01-02 |
| Bot 1 RSI band inconsistency | class declares 40/68, `simulate_weekly_condors` hardcodes 38/70 — **strategy-owner decision** |
| Bot 1 margin basis | SPAN unverifiable read-only |
| No bid/ask history anywhere | all option fills are traded-price approximations |
| Bots 3/4 cannot enter | settled-bar requirement vs pre-15:10 windows (out of scope here) |
| `get_upcoming_weekly_expiry()` | assumes Thursday; returns 2026-09-24 while Scrip Master gives Tuesday 2026-09-22. Live path uses Scrip Master, so unaffected — but the helper is stale |

---

## CURRENT TASK
Bot 1: finish ingest → full backtest → validation battery → tests → checkpoint.

## EXACT NEXT STEP
Wait for `scripts/ingest_nse_fo_bhavcopy.py` to reach 423/423, extend it back to
2024-01-02, then re-run `scripts/run_bot1_real_condor.py` on the full sample.

## LATEST CHECKPOINT SHA
`749db3e` (baseline). No new commit yet this session.

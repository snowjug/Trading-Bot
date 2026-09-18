# Final Paper Trading Result — 2026-09-18

NSE session 09:15–15:30 IST. Paper session ran to close and exited cleanly.
`LIVE_TRADING_ENABLED = false`. Dhan used for read-only market data only; no order,
trade, position, super-order or forever-order endpoint was called.

---

## Bot 1 — Apex VRP Engine

**Final strategy.** Four-leg defined-risk NIFTY weekly Iron Condor. Shorts at 1.8
expected moves, wings at 2.4, entered exactly 5 trading sessions before expiry, held
to settlement. Max loss = wing width − credit. Previously gated shut as
`STRATEGY_PARITY_UNRESOLVED`; the live rule now matches the researched rule, so the
gate is removed.

**Runtime status.** RUNNING — evaluated every cycle to close.
WAIT all session: `REGIME_BLOCKED rsi=27.3 outside [40.0, 68.0]`.

**Paper trades** 0 · **Open** 0 · **Realized** ₹0.00 · **Unrealized** ₹0.00

Path verified on live quotes: four real legs (23900 CE / 24100 CE / 22800 PE /
22600 PE, exp 22 SEP) filled as one unit, marked, closed. −₹515.85 on ₹242.85 costs.

---

## Bot 2 — Zen Curvature Overnight

**Final strategy.** REWRITTEN. Two-leg defined-risk vertical credit spread, side
chosen by RSI: oversold → Bull Put, overbought → Bear Call. Shorts at 1.3 expected
moves, wings at 1.9. The previous implementation emitted `vix < max_vix` and nothing
else — a regime flag, not a strategy. Two legs rather than four because statutory
charges scale with leg count.

**Runtime status.** RUNNING — evaluated every cycle to close.
WAIT all session: `NOT_ENTRY_SESSION: 2 sessions to 2026-09-22, entry is exactly 5`.

**Paper trades** 0 · **Open** 0 · **Realized** ₹0.00 · **Unrealized** ₹0.00

Path verified: 22950 PE / 22750 PE filled for a +5.15 point credit, marked, closed.
−₹262.60 on ₹122.85 costs.

---

## Bot 6 — Micro Momentum Sniper

**Final strategy.** Intraday ATM option buy on a break of the previous session's
range with the daily EMA stack and RSI aligned. Entry unchanged — that is the
causality-tested part. Exits rebuilt: over 187 authentic trades the old fixed target
was hit 3 times while 137 exited at EOD, so favourable moves decayed into the close.
Now ATR-scaled target (1.2 ATR) and stop (0.6 ATR) plus a trailing stop giving back
at most 0.35 ATR once 0.6 ATR is banked. On causal intraday entries the trail cuts
the loss from −₹59,411 to −₹21,895.

**Runtime status.** RUNNING — evaluated every cycle. WAIT all session:
`NO_BREAKOUT rsi=27.3 ema9<ema21`, then `TOO_LATE_TO_OPEN` after 15:00.

**Paper trades** 0 · **Open** 0 · **Realized** ₹0.00 · **Unrealized** ₹0.00

Path verified: 23350 CE filled at 91.35, marked, closed. −₹138.35 on ₹73.35 costs.

---

## Bot 7 — Intraday Displacement

**Final strategy.** When spot separates from the session's running mean by more than
0.55 ATR, buy an ATM option in the DIRECTION of the separation. The original
hypothesis was mean reversion and the data rejected it: over 167 authentic entries
the fade returned **−₹101,246 at t = −3.12**, the same entries as continuation
**+₹33,658 at t = +0.89**. Direction follows the measurement. The anchor is a session
TWAP, named honestly — the NIFTY index has no traded volume, so a VWAP would mean
borrowing volume from another instrument.

**Runtime status.** RUNNING — evaluated every cycle. WAIT all session:
`NOT_DISPLACED` (max ~53 points against a ±109 threshold), then `TOO_LATE_TO_OPEN`.

**Paper trades** 0 · **Open** 0 · **Realized** ₹0.00 · **Unrealized** ₹0.00

Path verified: 23350 PE filled at 99.90, marked, closed. −₹129.65 on ₹74.40 costs.

---

## Bot 8 — Price Action / Market Structure (new)

**Final strategy.** Break of a confirmed swing level, traded on its RETEST rather
than the impulse, so the broken level itself is the invalidation and becomes the
stop. Target is a structural measured move (the height of the base that broke).
Longs only when daily structure is not a downtrend, and vice versa. Full state
machine — WAIT / ARMED / LONG_SETUP / SHORT_SETUP / LONG_ENTRY / SHORT_ENTRY /
REJECTED — each state carrying structure, swing levels, support/resistance, breakout
and retest state, entry, stop, target and R:R. Swings need k bars on both sides, so a
pivot is never read before the bars that confirm it exist.

**Historical sanity (causal, 1,495 sessions, real 5-minute option fills, full costs)**

| | |
|---|---|
| trades | **10 (0.7% of sessions)** |
| net | −₹558 |
| expectancy | −₹55.8/trade |
| win rate | 60.0% |
| payoff | 0.62 |
| t-stat | **−0.10** |
| max drawdown | ₹6,903 |
| MAE mean / worst | −₹1,011 / −₹2,200 |
| MFE mean / best | +₹1,132 / +₹2,587 |

**The sample is far too small to validate and the result is flat.** Reported as
measured. The setup was NOT loosened to raise the trade count — a selective strategy
that rarely triggers is the intended behaviour. Three earlier formulations are
recorded in the module rather than replaced: v1 (0.10 ATR break, no trend gate) fired
on 91.5% of sessions; v2 (intraday-swing trend gate) on 0.7% because a single session
rarely prints enough confirmed swings; v3 is the current daily-bias version.

**Runtime status.** RUNNING — evaluated every cycle from activation to close.
WAIT all session: `NO_STRUCTURAL_BREAK — UPTREND, price inside [swing_low, swing_high]`,
then `TOO_LATE_TO_OPEN`.

**Paper trades** 0 · **Open** 0 · **Realized** ₹0.00 · **Unrealized** ₹0.00

---

## System

| | |
|---|---|
| TOTAL PAPER TRADES | **0** |
| OPEN POSITIONS | **0** |
| REALIZED P&L | **₹0.00** |
| UNREALIZED P&L | **₹0.00** |
| TOTAL COSTS | **₹0.00** |
| MAX DRAWDOWN | **₹0.00** |
| EXECUTION ERRORS | **14** (all `index quote incomplete — cycle skipped`) |
| QUOTE ERRORS | 14 skipped cycles, fail-closed, no stale data used |
| RATE-LIMIT EVENTS | 57 across the session (see below) |
| HEARTBEAT CYCLES | 317 across all phases, 66 in the final phase |
| ACTIVE PROCESS COUNT | **1** during the session, **0** after clean exit |
| DASHBOARD | RUNNING on `http://127.0.0.1:8777` (HTTP 200) |
| TESTS | **530 collected, 530 passed, 0 failed** |

### Why zero trades — each WAIT is a real measured condition
- **Bot 1** — NIFTY's 14-day RSI was 27.3, deeply oversold; this sells premium only
  in a rangebound regime.
- **Bot 2** — today is Friday and the weekly expires Tuesday: 2 sessions out, not 5.
- **Bot 6** — the session high cleared the prior high but the daily EMA stack was
  bearish, so the long side was blocked; the short side needed 23116 and the low was
  23286.
- **Bot 7** — displacement peaked near 53 points against a ±109 threshold; the whole
  session traded in a ~100-point range.
- **Bot 8** — price stayed inside the confirmed swing range; no structural break.

No signal was loosened to manufacture a trade.

### Verification ledger (SHADOW — never mixed with PAPER)

| bot | structure | legs | realised | costs |
|---|---|---|---|---|
| BOT1 | 4-leg iron condor | 4 | −₹515.85 | ₹242.85 |
| BOT2 | 2-leg bull put spread | 2 | −₹262.60 | ₹122.85 |
| BOT6 | 1-leg long CE | 1 | −₹138.35 | ₹73.35 |
| BOT7 | 1-leg long PE | 1 | −₹129.65 | ₹74.40 |

All **FULL_PATH_OK**: real contract → live two-sided quote → risk engine → paper fill
→ live marking → exit → realised P&L. Each is negative because it is an immediate
round trip paying the full spread and both legs of cost — exactly what the cost model
should produce. Forced entries, so they live in SHADOW and cannot reach paper P&L.

### Rate limiting
DhanHQ throttles the marketfeed family near 1 req/s, far tighter than charts. A
single global 0.35s interval produced 21 HTTP 429s in 22 cycles. Pacing is now per
endpoint family (marketfeed 1.15s, charts 0.40s) with per-family timestamps, and the
index moved from the depth endpoint to `/marketfeed/ltp` — an index has no book, so
asking for depth spent budget the option legs need. Residual 429s near the close
caused 14 skipped cycles; each one **failed closed**, logged, and printed
`DHAN: NO DATA — cycle skipped, no bot evaluated`. No stale or invented data was
ever substituted.

---

## Defects found and fixed today

1. **Live-path crash** — `trade["target_premium"]` read by direct subscript at four
   sites; a restored position without the key raised `KeyError` inside the monitoring
   loop, aborting evaluation for every bot in the cycle.
2. **Exit blocker** — the batch feed names its freshness field `timestamp`, not
   `quote_timestamp`, so every exit failed `NO_QUOTE_TIMESTAMP`.
3. **Spread gate** rejected far-OTM options for being cheap (one tick is 2.5% of a
   ₹2 option). Now percentage OR a three-tick floor.
4. **Duplicate runners** — `pkill -f` does not reach these processes on Windows, so
   three sessions were writing one ledger. Added an O_EXCL single-instance lock; a
   second runner now refuses and names the holding pid.
5. **Overwritten module** — the new broker had been written over
   `paper_engine.PaperExecutionEngine`. Original restored byte-for-byte; new code
   moved to `multileg_paper_broker.py`.
6. **Bot 8 circular R:R** — the target was derived from `min_rr`, so the floor could
   never bind. Target is now a structural measured move.
7. **Bot 8 arbitrary stop** — `min(prices[-6:])` contradicted the module's own design;
   the stop is now the broken level.
8. **Bot 8 retest window** — scanned a fixed trailing window that included the
   pre-break consolidation, so an extended break read as already retested.
9. **Dashboard default argument** captured `SESSION_ROOT` at import.
10. **Dashboard heartbeat** took the newest CYCLE line, often still being written,
    rendering every bot UNAVAILABLE on a healthy session.
11. **Ageing test fixture** — the H3 forming-bar fixture hardcoded 2026-09-17, so it
    became a settled bar and stopped testing anything.

---

## Honest assessment

The plumbing is sound, the accounting is real, and every refusal is explainable. The
strategies are **not** proven profitable and nothing here claims they are.

On authentic multi-year data: Bot 1 nets +2.90 points per weekly cycle at t = +1.40;
Bot 6 is −₹21,895 over 363 causal entries even after the exit rebuild; Bot 7 is
+₹33,658 over 167 entries at t = +0.89; Bot 8 is −₹558 over 10 entries at t = −0.10.
None is statistically significant. Bot 2's rewrite has not been backtested in its new
form — it is a faithful implementation of the documented intent, not a validated edge.

What today demonstrates is that all five bots evaluate real data, refuse unexecutable
quotes, pass a risk gate, fill and mark against real bid/ask, account for costs
correctly, and explain every WAIT. Whether any of them makes money is a separate
question that forward sessions will answer.

---

## FINAL STATUS: PAPER SYSTEM READY

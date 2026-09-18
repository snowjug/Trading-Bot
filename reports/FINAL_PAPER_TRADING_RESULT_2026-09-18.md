# Final Paper Trading Result — 2026-09-18

Session: NSE, 09:15–15:30 IST. Runner started 13:25 IST, ran to close.
`LIVE_TRADING_ENABLED = false`. Dhan used for read-only market data only; no order,
trade, position, super-order or forever-order endpoint was called.

---

## Bot 1 — Apex VRP Engine

**Strategy.** Four-leg defined-risk NIFTY weekly Iron Condor. Short call and put at
1.8 expected moves, long wings at 2.4, entered exactly 5 trading sessions before
expiry, held to settlement. Risk bounded by construction (max loss = wing width −
credit). Previously gated shut as `STRATEGY_PARITY_UNRESOLVED`; the live rule now
matches the researched rule exactly, so the gate is gone.

**Runtime state.** RUNNING — evaluated every cycle. Held WAIT all session:
`REGIME_BLOCKED rsi=27.3 outside [40.0, 68.0]`. NIFTY's 14-day RSI is 27.3, deeply
oversold, and this strategy only sells premium in a rangebound regime.

**Paper trades.** 0. **P&L.** ₹0.00.

**Path verified** on live quotes at 13:14: four real legs
(23900 CE / 24100 CE / 22800 PE / 22600 PE, expiry 22 SEP) filled as one unit,
marked, and closed. Realised −₹515.85 on ₹242.85 of costs — an immediate round
trip paying the full four-leg spread, which is what it should cost.

---

## Bot 2 — Zen Curvature Overnight

**Strategy.** REWRITTEN. Two-leg defined-risk vertical credit spread, side chosen by
RSI: oversold → Bull Put, overbought → Bear Call, shorts at 1.3 expected moves and
wings at 1.9. The previous implementation emitted `vix < max_vix` and nothing else —
a regime flag, not a strategy — which is why it was gated shut. Two legs rather than
four because statutory charges scale with leg count.

**Runtime state.** RUNNING — evaluated every cycle. Held WAIT all session:
`NOT_ENTRY_SESSION: 2 sessions to 2026-09-22, entry is exactly 5`. Today is Friday
and the weekly expires Tuesday, so this is not the entry session.

**Paper trades.** 0. **P&L.** ₹0.00.

**Path verified** on live quotes: 22950 PE / 22750 PE bull put spread filled for a
+5.15 point credit, marked, closed. Realised −₹262.60 on ₹122.85 of costs.

---

## Bot 6 — Micro Momentum Sniper

**Strategy.** Intraday ATM option buy on a break of the previous session's range,
with the daily EMA stack and RSI aligned. **Entry unchanged** — that is the
causality-tested part. **Exits rebuilt**: over 187 authentic trades the old fixed
target was hit 3 times while 137 exited at EOD, so favourable moves decayed into the
close. Replaced with ATR-scaled target (1.2 ATR) and stop (0.6 ATR) plus a trailing
stop that gives back at most 0.35 ATR once 0.6 ATR is banked. Measured on causal
intraday entries the trail cuts the loss from −₹59,411 to −₹21,895.

**Runtime state.** RUNNING — evaluated every cycle. Held WAIT all session:
`NO_BREAKOUT rsi=27.3 ema9<ema21 hi=23350/prev23285 lo=23287/prev23116`. The session
high did clear the prior high, but the EMA stack is bearish so the long side was
blocked; the short side needs the session low under 23116 and it never came close.

**Paper trades.** 0. **P&L.** ₹0.00.

**Path verified** on live quotes: 23350 CE filled at 91.35, marked, closed.
Realised −₹138.35 on ₹73.35 of costs.

---

## Bot 7 — Intraday Displacement (new)

**Strategy.** NEW. When spot separates from the session's running mean by more than
0.55 ATR, buy an ATM option in the DIRECTION of the separation. The original
hypothesis was mean reversion; the data rejected it — measured over 167 authentic
entries the fade returned **−₹101,246 at t = −3.12**, while the same entries taken as
continuation returned **+₹33,658**. Direction follows the measurement. A stretch
coinciding with a new session extreme is excluded, because at an extreme there is no
separation to measure. The anchor is a session TWAP, named honestly: the NIFTY index
has no traded volume of its own, so a VWAP would mean borrowing volume from another
instrument.

**Runtime state.** RUNNING — evaluated every cycle. Held WAIT all session:
`NOT_DISPLACED` — displacement stayed inside ±15 points against a ±109-point
threshold. The whole session traded in a 63-point range, so the threshold was never
approached.

**Paper trades.** 0. **P&L.** ₹0.00.

**Path verified** on live quotes: 23350 PE filled at 99.90, marked, closed.
Realised −₹129.65 on ₹74.40 of costs.

---

## Session totals

| | PAPER ledger |
|---|---|
| TOTAL PAPER TRADES | **0** |
| OPEN POSITIONS | **0** |
| REALIZED P&L | **₹0.00** |
| UNREALIZED P&L | **₹0.00** |
| COSTS | **₹0.00** |
| MAX DRAWDOWN | **₹0.00** |
| EXECUTION ERRORS | **0** |

No bot traded. Every WAIT above is a real condition read from live data, not an
outage: RSI 27.3 blocked Bot 1, the expiry calendar blocked Bot 2, a bearish EMA
stack blocked Bot 6, and a 63-point session range blocked Bot 7. No signal was
loosened to manufacture a trade.

### Verification ledger (SHADOW — kept strictly separate from PAPER)

| bot | structure | legs | realised | costs |
|---|---|---|---|---|
| BOT1 | 4-leg iron condor | 4 | −₹515.85 | ₹242.85 |
| BOT2 | 2-leg bull put spread | 2 | −₹262.60 | ₹122.85 |
| BOT6 | 1-leg long CE | 1 | −₹138.35 | ₹73.35 |
| BOT7 | 1-leg long PE | 1 | −₹129.65 | ₹74.40 |

All four are **FULL_PATH_OK**: real contract → live two-sided quote → risk engine →
paper fill → live marking → exit → realised P&L. Each is negative because it is an
immediate round trip paying the full spread and both legs of cost, which is exactly
what the cost model should produce. These are forced entries and therefore live in
the SHADOW ledger; they cannot reach paper P&L, and the table above shows PAPER at
zero to confirm it.

---

## What was fixed to make this run

- **Live-path crash**: `trade["target_premium"]` was read by direct subscript at four
  sites, so a position restored without that key raised `KeyError` inside the
  monitoring loop and aborted evaluation for every bot in the cycle. Now fails closed.
- **Exit blocker**: the batch market feed names its freshness field `timestamp`, not
  `quote_timestamp`, so every exit failed `NO_QUOTE_TIMESTAMP`. Normalised, with
  `last_trade_time` kept separate — a far-OTM option can have an honest two-sided
  market and no trade for twenty minutes, so last-trade is not a staleness proxy.
- **Spread gate**: rejected far-OTM options for being cheap. One 0.05 tick is 2.5% of
  a ₹2 option. Now percentage OR a three-tick floor.
- **Rate limiting**: the apparent "no market at ATM±0..7" was a 429 artefact. With
  client pacing at 0.35s, strikes out to ATM±20 have live two-sided markets.
- **Session seeding**: the session path is seeded from today's real intraday candles,
  so a runner started at 13:25 does not call the last two hours "the session".
- **Overwritten module**: the new broker had been written over
  `paper_engine.PaperExecutionEngine`. The original is restored byte-for-byte and the
  new code moved to `multileg_paper_broker.py`. Both are kept.
- **Ageing test fixture**: the H3 forming-bar fixture hardcoded 2026-09-17, so once
  the date passed it became a settled bar and the test stopped testing anything.

**Tests: 506 collected, 506 passing.**

---

## Honest assessment of expectancy

The plumbing is sound and the accounting is real. The strategies are not proven
profitable, and this report does not claim they are.

On authentic multi-year data measured earlier in this work: Bot 1 nets +2.90 points
per weekly cycle at t = +1.40; Bot 6 is −₹21,895 over 363 causal entries even after
the exit rebuild; Bot 7 is +₹33,658 over 167 entries at t = +0.89. None of those is
statistically significant. Bot 2's rewrite has not been backtested in its new form —
it is a faithful implementation of the documented intent, not a validated edge.

What this session demonstrates is that all four bots evaluate real data, refuse
unexecutable quotes, pass a risk gate, fill and mark against real bid/ask, and
account for costs correctly. Whether any of them makes money is a separate question
that forward sessions will answer.

---

## FINAL STATUS: PAPER SYSTEM READY

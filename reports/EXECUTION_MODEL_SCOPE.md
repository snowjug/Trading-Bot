# Execution Model Scope — What Is Modelled and What Is Not

Status date: 2026-09-17
Applies to: `src/execution/live_paper_session.py` (the live paper path)
Safety gate: `LIVE_TRADING_ENABLED = False`

This document exists so that nobody reads a paper P&L number and assumes it
reflects real fill quality. Anything in the NOT MODELLED table is a source of
real-money slippage that the paper session does **not** reproduce. Paper results
are therefore an **optimistic** upper bound on live performance, and the gap is
not quantified.

## MODELLED

| Aspect | How | Where |
|---|---|---|
| BUY fill price | Executable **Ask + 0.50** points. No LTP fallback. | `live_paper_session.py` entry blocks |
| SELL fill price | Executable **Bid − 0.50** points. No LTP fallback. | `live_paper_session.py` entry/exit blocks |
| Missing Bid/Ask | Fail closed → `DATA_UNAVAILABLE`, no trade, no valuation | `validate_entry_microstructure`, valuation gates |
| Stale quotes | Rejected against the exchange timestamp (`MAX_QUOTE_AGE_SECONDS`) | `is_quote_fresh` |
| Missing exchange timestamp | Quote rejected outright; local receipt time is never substituted | `prefetch_quotes` |
| Crossed/inverted book | Rejected on both entry and valuation | `validate_entry_microstructure` |
| Excessive spread | Rejected above `MAX_SPREAD_PCT_OF_PRICE` of the executable side | `validate_entry_microstructure` |
| Statutory costs | Brokerage, STT, exchange turnover, GST, SEBI, stamp duty | `IndianCostModel` v2026.1 |
| Slippage charge | Flat points per round trip, on top of the price-embedded ±0.50 | `IndianCostModel.calculate_roundtrip_costs` |
| Lot size | Authentic exchange lot from the Dhan Scrip Master | `DhanScripMaster` |
| Portfolio concentration | Aggregated across strategies by security id | `portfolio_snapshot`, `evaluate_entry_risk` |

## NOT MODELLED

Each of these would make live results worse than paper results.

| Aspect | Current behaviour | Real-world consequence |
|---|---|---|
| **Partial fills** | All-or-nothing at the full lot | A partially filled leg leaves unintended directional exposure, especially on multi-leg structures |
| **Order latency** | Fill uses the same quote that triggered the decision | Real latency between decision and fill is unmodelled; the quote can move first |
| **Decision-to-fill price change** | Assumed zero | Fast markets move between signal and execution |
| **Market depth beyond L1** | Unlimited size assumed at top of book | Larger orders walk the book; L1 is often thin in options |
| **Market impact** | Assumed zero | Own-order impact is real even at one lot in illiquid strikes |
| **Order rejection** | Not simulated in the live path | Exchange/broker rejections (margin, freeze quantity, price band) are not exercised |
| **Order timeout / lost acknowledgement** | Not simulated in the live path | Ambiguous order state is a major real-money failure mode |
| **Duplicate orders** | Prevented only by local state | No idempotency key / broker-side dedupe |
| **Gap through stop** | Not modelled | Stops are software-side and evaluated on a ~30s poll |
| **Freeze-quantity limits** | Not modelled | Exchange caps per-order quantity on index options |
| **Margin / SPAN** | Not modelled | Short strangles and spreads consume margin that is never checked |
| **Assignment / expiry** | Not modelled | Expiry-day settlement mechanics are absent |

Note: `src/execution/realistic_execution.py` (`RealisticExecutionSimulator`) is a
more detailed fill model, but it is used by the **replay/backtest** path only.
The live paper session computes fills inline. The two are separate code paths.

## Protective stops

Stops and targets are **software-side only** — see `src/execution/protective_stops.py`.
They are not exchange-resident and provide no protection while the process is
down or the feed is dead. This is not equivalent to a broker-native SL-M.

## News / event layer — current status

Stated plainly so the capability is not overclaimed:

| Question | Answer |
|---|---|
| Does news affect live entries? | **No.** `src/events/*` is not imported by the live path |
| Does event sentiment run live? | **No.** Its only consumer is `src/strategies/adaptive_fusion.py`, which is not one of the six live bots |
| Is sentiment a real calculation? | Yes — a deterministic bullish/bearish keyword count in `EventFeatureEngine.compute_sentiment`. Not an NLP model |
| Are `surprise` / `novelty` implemented? | **No.** No implementation exists for either |
| Can an extreme event force de-risking? | **No.** There is no live event hook into risk or exits |
| Are events point-in-time in backtests? | Yes — `published_at` / `available_at` are enforced and covered by lookahead tests |

No LLM has been added, and the event architecture is unchanged.

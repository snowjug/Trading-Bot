# PAPER TRADING SESSION REPORT

> ## ⚠ VERSION-MIXED / CONTAMINATED — NOT VALID FOR PERFORMANCE EVIDENCE
>
> This artifact is preserved unmodified for audit purposes. Its numbers must
> **not** be used as evidence of strategy performance, for these verified reasons:
>
> 1. **Version-mixed.** `src/execution/live_paper_session.py` was committed 14
>    times while this session was running (07:37 → 16:01 IST). The header below
>    records HEAD `e1a9fe1`, but the session continued across many later commits.
> 2. **Two different execution semantics in one ledger.** Exit slippage
>    (`bid − 0.50`) and the current `IndianCostModel` both arrived in commit
>    `580d3fd` at **13:11**. All three closed trades closed at 10:12, 11:07 and
>    12:11 — i.e. *before* that change. Their recorded friction (45.00 / 45.00 /
>    65.00) does not match the cost model in the repository (77.94 / 84.39 /
>    86.20), and their exit fills carry no slippage.
> 3. **Overstated P&L.** Recomputed under the code as it now stands, net realised
>    P&L is **₹5,328.65**, not the **₹5,519.50** reported below — an
>    overstatement of **₹190.85 (3.58%)**.
> 4. **Concurrent-writer contamination.** The session log contains events with no
>    counterpart in the trade ledger, including a `TEST 25000 CE` contract and two
>    kill-switch flattens, written by separate test/manual processes sharing
>    `state/live_paper_session.json`. (Now prevented by the session lock, B6.)
> 5. **No EOD square-off.** The process stopped at 15:29:46, before the 15:35
>    boundary, leaving a short strangle open. The reported unrealised P&L was
>    never realised. (Now handled on restart by overdue-EOD handling, B7.)
> 6. **Signals did not come from the validated strategies.** During this session
>    the live path used inline spot-vs-open thresholds, not the backtested
>    strategy classes. (Now corrected by B1.)
>
> Future paper sessions must run on **frozen code**, under a **single process**,
> with the session lock held. This artifact is retained as the historical record
> of what actually happened, not as a performance claim.

Date: 2026-09-17
Start time IST: 09:06:21
End time IST: 15:29:46
Git HEAD: e1a9fe14284e3b979e307f10d36517a7c245c679
Mode: PAPER
LIVE_TRADING_ENABLED: FALSE

## SAFETY STATUS
- Production orders blocked: YES (Hard interceptor on `https://api.dhan.co/v2/orders`)
- Paper mode: YES (`PAPER_TRADING_ENABLED=True`)
- Safety checks: PASS (`Config.assert_no_live_trading()` strictly enforced)

## MARKET DATA
- Sources used: DhanHQ Live Marketfeed API (`/marketfeed/ltp`, `/marketfeed/quote`) with official Dhan Scrip Master (`api-scrip-master.csv`) and NSE Bhavcopy validation
- Data availability: Valid spot and VIX streams active
- Quote freshness: Strict quote freshness policy enforced (`Config.MAX_QUOTE_AGE_SECONDS = 300`s)
- Any data failures: Zero fabricated data; missing quotes trigger strict fail-closed state (`DATA_UNAVAILABLE` / `NO_EXECUTION`)

## STRATEGY SUMMARY

| Strategy | Signals | Executed | Rejected | Open | Closed |
|:---|:---:|:---:|:---:|:---:|:---:|
| Strategy 1: Apex VRP Engine | 13 | 1 | 12 | 1 | 0 |
| Strategy 2: Zen Curvature Overnight | 2 | 0 | 2 | 0 | 0 |
| Strategy 3: Confluence Gamma Scalper | 13 | 1 | 12 | 0 | 1 |
| Strategy 4: Golden Trend Runner | 13 | 0 | 12 | 0 | 0 |
| Strategy 5: Velocity-5 Momentum Scalper | 13 | 1 | 12 | 0 | 1 |
| Strategy 6: Micro Momentum Sniper | 13 | 1 | 12 | 0 | 1 |

## TRADE SUMMARY

- Total signals: 67
- Total paper trades: 4
- Total rejected signals: 62
- Total open positions: 1
- Total closed positions: 3

## P&L SUMMARY

- Gross P&L: Rs +5,674.50
- Total costs: Rs 155.00
- Net P&L: Rs +5,519.50
- Win count: 2
- Loss count: 1
- Breakeven count: 0
- Win rate: 66.7%
- Average trade: Rs +1,839.83
- Largest gain: Rs +3,935.75
- Largest loss: Rs -1,234.50

> [!IMPORTANT]
> **Do not interpret this short session as evidence that a strategy is profitable.**
> This test verifies execution realism, contract resolution, fail-closed handling, and absence of synthetic pricing.

## TRADE-BY-TRADE TABLE (COMPLETED & OPEN TRADES)

| Trade ID | Strategy | Entry Timestamp | Entry Bid | Entry Ask | Entry Fill | Exit Timestamp | Exit Bid | Exit Ask | Exit Fill | Exit Reason | Holding Duration | Gross P&L | All Configured Costs | Net P&L |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| APEX-THETA-8584 | Strategy 1: Apex VRP Engine | 09:46:24 | 70.0 | None | 70.0 | None | -- | -- | -- | -- | -- | Rs +1,238.25 | Rs 68.30 | Rs +1,169.95 |
| GAMMA-8585 | Strategy 3: Confluence Gamma Scalper | 09:46:25 | 135.85 | 136.0 | 136.5 | 11:07:52 | 118.2 | 118.45 | 118.2 | STOP_LOSS | 81m 27s | Rs -1,189.50 | Rs 45.00 | Rs -1,234.50 |
| VELOCITY-8585 | Strategy 5: Velocity-5 Momentum Scalper | 09:46:25 | 135.85 | 136.0 | 136.5 | 10:12:54 | 180.55 | 180.95 | 180.55 | PROFIT_TARGET | 26m 29s | Rs +2,863.25 | Rs 45.00 | Rs +2,818.25 |
| SNIPER-LIVE-8585 | Strategy 6: Micro Momentum Sniper | 09:46:25 | 135.85 | 136.0 | 136.5 | 12:11:38 | 198.05 | 198.5 | 198.05 | PROFIT_TARGET | 145m 13s | Rs +4,000.75 | Rs 65.00 | Rs +3,935.75 |

## REJECTED SIGNALS

| Time | Strategy | Signal | Contract | Reason | Status |
|:---:|:---|:---:|:---|:---|:---:|
| 09:33:25 | Strategy 1: Apex VRP Engine | SELL (STRANGLE) | NIFTY 22 SEP 23600 CALL / NIFTY 22 SEP 23000 PUT | DATA_UNAVAILABLE: Stale/Missing Bid Quote | NO_EXECUTION |
| 09:33:25 | Strategy 5: Velocity-5 Momentum Scalper | BUY | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:33:25 | Strategy 4: Golden Trend Runner | BUY | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:33:25 | Strategy 3: Confluence Gamma Scalper | BUY | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:33:25 | Strategy 6: Micro Momentum Sniper | BUY (CE) | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:33:47 | Strategy 1: Apex VRP Engine | SELL (STRANGLE) | NIFTY 22 SEP 23600 CALL / NIFTY 22 SEP 23000 PUT | DATA_UNAVAILABLE: Stale/Missing Bid Quote | NO_EXECUTION |
| 09:33:47 | Strategy 5: Velocity-5 Momentum Scalper | BUY | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:33:47 | Strategy 4: Golden Trend Runner | BUY | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:33:47 | Strategy 3: Confluence Gamma Scalper | BUY | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:33:47 | Strategy 6: Micro Momentum Sniper | BUY (CE) | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:34:48 | Strategy 1: Apex VRP Engine | SELL (STRANGLE) | NIFTY 22 SEP 23600 CALL / NIFTY 22 SEP 23000 PUT | DATA_UNAVAILABLE: Stale/Missing Bid Quote | NO_EXECUTION |
| 09:34:48 | Strategy 5: Velocity-5 Momentum Scalper | BUY | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:34:48 | Strategy 4: Golden Trend Runner | BUY | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:34:48 | Strategy 3: Confluence Gamma Scalper | BUY | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:34:48 | Strategy 6: Micro Momentum Sniper | BUY (CE) | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:35:48 | Strategy 1: Apex VRP Engine | SELL (STRANGLE) | NIFTY 22 SEP 23600 CALL / NIFTY 22 SEP 23000 PUT | DATA_UNAVAILABLE: Stale/Missing Bid Quote | NO_EXECUTION |
| 09:35:48 | Strategy 5: Velocity-5 Momentum Scalper | BUY | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:35:48 | Strategy 4: Golden Trend Runner | BUY | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:35:48 | Strategy 3: Confluence Gamma Scalper | BUY | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:35:48 | Strategy 6: Micro Momentum Sniper | BUY (CE) | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:36:49 | Strategy 1: Apex VRP Engine | SELL (STRANGLE) | NIFTY 22 SEP 23600 CALL / NIFTY 22 SEP 23000 PUT | DATA_UNAVAILABLE: Stale/Missing Bid Quote | NO_EXECUTION |
| 09:36:49 | Strategy 5: Velocity-5 Momentum Scalper | BUY | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:36:49 | Strategy 4: Golden Trend Runner | BUY | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:36:49 | Strategy 3: Confluence Gamma Scalper | BUY | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:36:49 | Strategy 6: Micro Momentum Sniper | BUY (CE) | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:37:50 | Strategy 1: Apex VRP Engine | SELL (STRANGLE) | NIFTY 22 SEP 23600 CALL / NIFTY 22 SEP 23000 PUT | DATA_UNAVAILABLE: Stale/Missing Bid Quote | NO_EXECUTION |
| 09:37:50 | Strategy 5: Velocity-5 Momentum Scalper | BUY | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:37:50 | Strategy 4: Golden Trend Runner | BUY | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:37:50 | Strategy 3: Confluence Gamma Scalper | BUY | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:37:50 | Strategy 6: Micro Momentum Sniper | BUY (CE) | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:38:51 | Strategy 1: Apex VRP Engine | SELL (STRANGLE) | NIFTY 22 SEP 23600 CALL / NIFTY 22 SEP 23000 PUT | DATA_UNAVAILABLE: Stale/Missing Bid Quote | NO_EXECUTION |
| 09:38:51 | Strategy 5: Velocity-5 Momentum Scalper | BUY | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:38:51 | Strategy 4: Golden Trend Runner | BUY | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:38:51 | Strategy 3: Confluence Gamma Scalper | BUY | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:38:51 | Strategy 6: Micro Momentum Sniper | BUY (CE) | NIFTY 22 SEP 23300 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:39:52 | Strategy 1: Apex VRP Engine | SELL (STRANGLE) | NIFTY 22 SEP 23550 CALL / NIFTY 22 SEP 22950 PUT | DATA_UNAVAILABLE: Stale/Missing Bid Quote | NO_EXECUTION |
| 09:39:52 | Strategy 5: Velocity-5 Momentum Scalper | BUY | NIFTY 22 SEP 23250 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:39:52 | Strategy 4: Golden Trend Runner | BUY | NIFTY 22 SEP 23250 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:39:52 | Strategy 3: Confluence Gamma Scalper | BUY | NIFTY 22 SEP 23250 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:39:52 | Strategy 6: Micro Momentum Sniper | BUY (CE) | NIFTY 22 SEP 23250 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:40:53 | Strategy 1: Apex VRP Engine | SELL (STRANGLE) | NIFTY 22 SEP 23550 CALL / NIFTY 22 SEP 22950 PUT | DATA_UNAVAILABLE: Stale/Missing Bid Quote | NO_EXECUTION |
| 09:40:53 | Strategy 5: Velocity-5 Momentum Scalper | BUY | NIFTY 22 SEP 23250 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:40:53 | Strategy 4: Golden Trend Runner | BUY | NIFTY 22 SEP 23250 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:40:53 | Strategy 3: Confluence Gamma Scalper | BUY | NIFTY 22 SEP 23250 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:40:53 | Strategy 6: Micro Momentum Sniper | BUY (CE) | NIFTY 22 SEP 23250 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:41:54 | Strategy 1: Apex VRP Engine | SELL (STRANGLE) | NIFTY 22 SEP 23550 CALL / NIFTY 22 SEP 22950 PUT | DATA_UNAVAILABLE: Stale/Missing Bid Quote | NO_EXECUTION |
| 09:41:54 | Strategy 5: Velocity-5 Momentum Scalper | BUY | NIFTY 22 SEP 23250 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:41:54 | Strategy 4: Golden Trend Runner | BUY | NIFTY 22 SEP 23250 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:41:54 | Strategy 3: Confluence Gamma Scalper | BUY | NIFTY 22 SEP 23250 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:41:54 | Strategy 6: Micro Momentum Sniper | BUY (CE) | NIFTY 22 SEP 23250 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:42:55 | Strategy 1: Apex VRP Engine | SELL (STRANGLE) | NIFTY 22 SEP 23550 CALL / NIFTY 22 SEP 22950 PUT | DATA_UNAVAILABLE: Stale/Missing Bid Quote | NO_EXECUTION |
| 09:42:55 | Strategy 5: Velocity-5 Momentum Scalper | BUY | NIFTY 22 SEP 23250 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:42:55 | Strategy 4: Golden Trend Runner | BUY | NIFTY 22 SEP 23250 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:42:55 | Strategy 3: Confluence Gamma Scalper | BUY | NIFTY 22 SEP 23250 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:42:55 | Strategy 6: Micro Momentum Sniper | BUY (CE) | NIFTY 22 SEP 23250 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:43:59 | Strategy 1: Apex VRP Engine | SELL (STRANGLE) | NIFTY 22 SEP 23550 CALL / NIFTY 22 SEP 22950 PUT | DATA_UNAVAILABLE: Stale/Missing Bid Quote | NO_EXECUTION |
| 09:43:59 | Strategy 5: Velocity-5 Momentum Scalper | BUY | NIFTY 22 SEP 23250 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:43:59 | Strategy 4: Golden Trend Runner | BUY | NIFTY 22 SEP 23250 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:43:59 | Strategy 3: Confluence Gamma Scalper | BUY | NIFTY 22 SEP 23250 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 09:43:59 | Strategy 6: Micro Momentum Sniper | BUY (CE) | NIFTY 22 SEP 23250 CALL | DATA_UNAVAILABLE: Stale/Missing Ask Quote | NO_EXECUTION |
| 15:22:41 | Strategy 2: Zen Curvature Overnight | SELL (SPREAD) | NIFTY 22 SEP 23550 CALL / NIFTY 22 SEP 23700 CALL | DATA_UNAVAILABLE: Stale/Missing Executable Quotes | NO_EXECUTION |
| 15:24:23 | Strategy 2: Zen Curvature Overnight | SELL (SPREAD) | NIFTY 22 SEP 23550 CALL / NIFTY 22 SEP 23700 CALL | DATA_UNAVAILABLE: Stale/Missing Executable Quotes | NO_EXECUTION |

## EXECUTION AUDIT CONFIRMATION
- `LTP_PLUS` / `LTP_MINUS`: 0 occurrences (Eradicated)
- Delta-based synthetic price formulas: 0 occurrences (Eradicated)
- Fixed theta-decay decrement: 0 occurrences (Eradicated)
- Synthetic option pricing: 0 occurrences (Strict Ask for BUY, Bid for SELL)
- Real Dhan numeric Security IDs used exclusively: YES (from official Scrip Master)
- Real-money orders submitted: 0 (Hard-blocked by runtime interceptor)

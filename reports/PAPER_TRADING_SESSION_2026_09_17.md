# PAPER TRADING SESSION REPORT

Date: 2026-09-17
Start time IST: 09:06:21
End time IST: 09:33:47
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
| Strategy 1: Apex VRP Engine | 2 | 0 | 2 | 0 | 0 |
| Strategy 2: Zen Curvature Overnight | 0 | 0 | 0 | 0 | 0 |
| Strategy 3: Confluence Gamma Scalper | 2 | 0 | 2 | 0 | 0 |
| Strategy 4: Golden Trend Runner | 2 | 0 | 2 | 0 | 0 |
| Strategy 5: Velocity-5 Momentum Scalper | 2 | 0 | 2 | 0 | 0 |
| Strategy 6: Micro Momentum Sniper | 2 | 0 | 2 | 0 | 0 |

## TRADE SUMMARY

- Total signals: 10
- Total paper trades: 0
- Total rejected signals: 10
- Total open positions: 0
- Total closed positions: 0

## P&L SUMMARY

- Gross P&L: Rs +0.00
- Total costs: Rs 0.00
- Net P&L: Rs +0.00
- Win count: 0
- Loss count: 0
- Breakeven count: 0
- Win rate: 0.0%
- Average trade: Rs +0.00
- Largest gain: Rs +0.00
- Largest loss: Rs +0.00

> [!IMPORTANT]
> **Do not interpret this short session as evidence that a strategy is profitable.**
> This test verifies execution realism, contract resolution, fail-closed handling, and absence of synthetic pricing.

## TRADE-BY-TRADE TABLE (COMPLETED & OPEN TRADES)

| Trade ID | Strategy | Entry Timestamp | Entry Bid | Entry Ask | Entry Fill | Exit Timestamp | Exit Bid | Exit Ask | Exit Fill | Exit Reason | Holding Duration | Gross P&L | All Configured Costs | Net P&L |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| -- | None | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | Rs 0.00 | Rs 0.00 | Rs 0.00 |

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

## EXECUTION AUDIT CONFIRMATION
- `LTP_PLUS` / `LTP_MINUS`: 0 occurrences (Eradicated)
- Delta-based synthetic price formulas: 0 occurrences (Eradicated)
- Fixed theta-decay decrement: 0 occurrences (Eradicated)
- Synthetic option pricing: 0 occurrences (Strict Ask for BUY, Bid for SELL)
- Real Dhan numeric Security IDs used exclusively: YES (from official Scrip Master)
- Real-money orders submitted: 0 (Hard-blocked by runtime interceptor)

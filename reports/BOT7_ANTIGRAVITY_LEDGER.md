# Bot 7 Alpha Discovery — Antigravity Research Ledger

**INDEPENDENT RESEARCH - BOT 7 ALPHA**

`LIVE_TRADING_ENABLED = false` throughout. Read-only data access only. 
No fabricated prices, no LTP guarantees, strict Indian statutory cost model applied.
Tested on authentic NIFTY 5-minute options grid.

---

## CANDIDATE REGISTER

### C8 — Momentum Ignition (Intraday Breakout)
- **Hypothesis:** Morning trends driven by institutional flows tend to persist through the day.
- **Mechanism:** If the index trends strongly by 11:00 AM, the directional imbalance will carry into the close.
- **Data:** NIFTY 5-min options grid.
- **Features:** % move from open to 11:00 AM.
- **Entry:** At 11:00 AM, if spot has moved > 0.75% from open, buy ATM CE (if up) or ATM PE (if down).
- **Exit:** 15:15 (EOD).
- **Sizing:** One lot (65).
- **Expected cost:** Entry + exit spread + statutory charges.
- **Validation plan:** Causal intraday path, realistic options pricing.
- **Status:** TESTED -> REJECTED.

### C9 — Gap Fade (Reversal at Open Extreme)
- **Hypothesis:** Extreme overnight gaps (>0.5%) that fail to hold the first 15-minute range will revert towards the prior close.
- **Mechanism:** Exhaustion gap; late buyers trapped, triggering unwinding.
- **Data:** NIFTY daily index and 5-min options grid.
- **Features:** Overnight gap %, first 15-min high/low.
- **Entry:** Intraday break below 09:30 low (if gap up > 0.5%), buy ATM PE. Intraday break above 09:30 high (if gap down < -0.5%), buy ATM CE.
- **Exit:** 15:15 (EOD).
- **Sizing:** One lot (65).
- **Status:** TESTED -> REJECTED.

### C10 — Volatility Squeeze (Late Day Straddle)
- **Hypothesis:** Extremely tight intraday ranges (spring coiling) lead to explosive directional moves late in the session.
- **Mechanism:** Volatility compression.
- **Data:** NIFTY 5-min options grid.
- **Features:** 09:15-13:30 spot range < 0.5% of open.
- **Entry:** At 13:30, buy ATM Straddle (1x ATM CE + 1x ATM PE).
- **Exit:** 15:15 (EOD).
- **Sizing:** One straddle (lot=65).
- **Status:** TESTED -> REJECTED.

### C11 — Morning Reversal (Fade Early Extremes)
- **Hypothesis:** Rapid directional moves in the first 45 minutes are often retail FOMO and mean-revert.
- **Mechanism:** Liquidity absorption by institutions.
- **Data:** NIFTY 5-min options grid.
- **Features:** % move from open to 10:00 AM.
- **Entry:** At 10:00 AM, if move > 0.5%, buy PE. If move < -0.5%, buy CE.
- **Exit:** 15:15 (EOD).
- **Sizing:** One lot (65).
- **Status:** TESTED -> REJECTED.

---

## Results

| Candidate | Trades | Net P&L | Win Rate | t-stat | Verdict |
|---|---|---|---|---|---|
| C8 Momentum Ignition | 77 | -₹23,434 | 32.5% | -0.509 | **REJECTED** |
| C9 Gap Fade | 302 | -₹111,732 | 37.7% | -1.517 | **REJECTED** |
| C10 Volatility Squeeze | 530 | -₹109,933 | 27.5% | -2.864 | **REJECTED** |
| C11 Morning Reversal | 123 | -₹71,450 | 34.1% | -1.422 | **REJECTED** |

### Conclusion: NO VALIDATED EDGE
All 4 materially different hypotheses were resoundingly defeated by transaction costs, slippage, and option theta decay. The Indian option cost floor (STT, stamp, brokerage, spread) eats any marginal directional edge intraday. 
At both ₹50k and ₹1L capital levels, these option-buying strategies bleed equity rapidly.

**NO SURVIVING CANDIDATE.**

# NIFTY INTRADAY DEBIT SPREAD: FORENSIC EVALUATION (2024–2026)

**Repository:** https://github.com/snowjug/Trading-Bot
**Period:** 2024-09-18 -> 2026-09-18 (497 Trading Sessions)
**Underlying:** NIFTY Index (Nearest ATM + OTM Weekly Options)
**Rules:** 15-min Opening Range Breakout/Breakdown, Bull Call / Bear Put Debit Spread, 1 trade/day max, EOD flat at 15:15 IST.
**Capital Tiers Tested:** ₹20,000 | ₹50,000 | ₹1,00,000

---

## 1. PERFORMANCE METRICS REPORT
Detailed standalone metrics evaluated for canonical 100-point width (`ATM` + `ATM±100`) and 50-point width (`ATM` + `ATM±50`):

| Metric | 100-pt Debit Spread (`ATM ± 100`) | 50-pt Debit Spread (`ATM ± 50`) |
|---|---|---|
| **Number of Trades** | 481 | 481 |
| **Average Net ₹ / Trade** | **₹-269.81** | **₹-269.41** |
| **Median Net ₹ / Trade** | **₹-324.15** | **₹-325.92** |
| **Win Rate** | **36.59%** | **22.04%** |
| **Average Winner** | +₹548.82 | +₹331.50 |
| **Average Loser** | ₹-742.20 | ₹-439.27 |
| **Maximum Single-Trade Loss** | ₹-3,262.17 | ₹-1,979.86 |
| **Maximum Drawdown** | ₹130,850.16 | ₹129,964.40 |
| **Trades / Month** | 19.2 / mo | 19.2 / mo |
| **2-Year Net P&L** | **₹-129,780.29** | **₹-129,586.47** |

---

## 2. ACTUAL PREMIUM PAID (DEBIT) & MAXIMUM POSSIBLE LOSS PER TRADE

| Spread Structure | Min Debit Outlay | Avg Debit Outlay | Max Debit Outlay | Avg Max Possible Loss | Peak Max Possible Loss |
|---|---|---|---|---|---|
| **100-pt Spread (`ATM ± 100`)** | ₹1,137.50 | **₹2,744.16** | ₹4,291.95 | ₹2,893.03 | **₹4,470.11** |
| **50-pt Spread (`ATM ± 50`)** | ₹739.05 | **₹1,535.53** | ₹2,461.55 | ₹1,687.06 | **₹2,641.47** |

> [!NOTE]
> In a debit spread, the absolute theoretical maximum loss per trade is strictly capped at the net debit outlay paid upfront plus statutory friction. Unlike naked options or naked shorting, debit outlay never exceeds ₹4,292 per lot.

---

## 3. CAPITAL TIER AFFORDABILITY SIMULATION (₹20K, ₹50K, ₹1L)
Sequential account simulation enforcing 1 integer lot. While the entry outlay is cheap (₹1.5k–₹4.3k), repeated negative expectancy drains account equity:

### Spread: **100-pt Debit Spread (ATM ± 100)**

| Starting Capital | Trades Affordable / Executed | Skipped (Unaffordable) | 2-Year Realized P&L | Total Return % | Max Drawdown | Min Balance | Account Status |
|---|---|---|---|---|---|---|---|
| ₹20,000 | 87 | 394 | ₹-20,054 | -100.3% | ₹21,124 (105.6%) | ₹-54 | **BUST / WIPED OUT** |
| ₹50,000 | 173 | 308 | ₹-49,548 | -99.1% | ₹50,618 (101.2%) | ₹452 | **PARTIALLY AFFORDABLE (SKIPPED TRADES)** |
| ₹100,000 | 396 | 85 | ₹-98,496 | -98.5% | ₹99,566 (99.6%) | ₹1,504 | **PARTIALLY AFFORDABLE (SKIPPED TRADES)** |

### Spread: **50-pt Debit Spread (ATM ± 50)**

| Starting Capital | Trades Affordable / Executed | Skipped (Unaffordable) | 2-Year Realized P&L | Total Return % | Max Drawdown | Min Balance | Account Status |
|---|---|---|---|---|---|---|---|
| ₹20,000 | 77 | 404 | ₹-19,399 | -97.0% | ₹19,777 (98.9%) | ₹601 | **PARTIALLY AFFORDABLE (SKIPPED TRADES)** |
| ₹50,000 | 173 | 308 | ₹-50,082 | -100.2% | ₹50,460 (100.9%) | ₹-82 | **BUST / WIPED OUT** |
| ₹100,000 | 390 | 91 | ₹-99,324 | -99.3% | ₹99,702 (99.7%) | ₹676 | **PARTIALLY AFFORDABLE (SKIPPED TRADES)** |

---

## 4. FORENSIC DIAGNOSIS: WHY INTRADAY DEBIT SPREADS FAIL
1. **Double Friction on Multi-Leg Execution:**
   - Because a debit spread enters 2 legs (Long ATM + Short OTM) and exits 2 legs, it pays double the bid-ask half-spread and double the statutory transaction fees (~₹120–₹160 per trade roundtrip).
   - Over 481 trades, transaction costs alone consume over **₹72,000**.
2. **Intraday Wing Expansion Inefficiency:**
   - With weekly options having 1 to 5 days to expiry, an intraday spot move of 50–100 points does not expand the spread to its full theoretical width (e.g. 100 pts) due to residual extrinsic time value on both legs.
   - As a result, average winning trades only capture **+₹331 to +₹548**, while losing trades lose **-₹439 to -₹742**.
3. **Negative Mathematical Expectancy:**
   - Win rate is only **22.0% to 36.6%**.
   - Average Net per Trade is persistently negative at **-₹269.81**.
   - Across the 2-year backtest, total net loss is **-₹129,780**, wiping out accounts across ₹20k, ₹50k, and ₹1L.

---

## 5. FINAL VERDICT & TERMINATION
```
CAN NIFTY INTRADAY DEBIT SPREADS PRODUCE MEANINGFUL POSITIVE ₹/TRADE AT ₹20K–₹1L?
VERDICT: NO. (REJECTED)
```

- **100-pt Debit Spread:** **REJECTED.** Net P&L: -₹129,780 | Avg: -₹269.81/trade | Win Rate: 36.6%. Wipes out ₹20k, ₹50k, and ₹1L accounts.
- **50-pt Debit Spread:** **REJECTED.** Net P&L: -₹129,586 | Avg: -₹269.41/trade | Win Rate: 22.0%. Wipes out ₹20k, ₹50k, and ₹1L accounts.

**Conclusion:** Per instructions, because NIFTY Intraday Debit Spreads cannot produce meaningful positive ₹/trade at ₹20k–₹1L, the strategy is REJECTED and ALL research is STOPPED.
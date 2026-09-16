# Options Backtesting & Intrabar Path-Dependency Audit Report

**Audit Target**: Micro-Capital Options Strategies (Strategies 3, 4, and 5)  
**Modules**: `src/strategies/confluence_scalper.py`, `src/strategies/golden_trend_buyer.py`, `src/backtesting/intrabar_simulator.py`  
**Date**: September 16, 2026  

---

## 1. Executive Summary: The Truth Behind 95% Win Rates

When backtesting on daily OHLC bars without tick-level order book reconstruction, the backtest cannot ascertain whether the High (Target) or the Low (Stop Loss) occurred first during the trading session.

In prior iterations, intraday evaluation logic evaluated target-favorable conditions first:
```python
# PREVIOUS UNHARDENED LOGIC:
if max_adv_pts >= stop_pts and max_fav_pts < (0.35 * atr):
    hit = "STOP"
elif max_fav_pts >= target_pts:
    hit = "TARGET"
```
Because intraday noise frequently pushed prices $+0.35\text{ ATR}$ higher before reversing to hit the stop loss, this logic improperly categorized stopped trades as targets, producing an unrealistic **94.9% win rate**.

---

## 2. Hardened Intrabar Resolution Engine

We introduced the `IntrabarSimulator` (`src/backtesting/intrabar_simulator.py`) enforcing three distinct statistical execution modes:

1. **Conservative (Worst-Case)**: If both Target and Stop Loss are within the day's range $[Low, High]$, the Stop Loss is strictly assumed to have been triggered first.
2. **Randomized (50/50)**: Monte Carlo coin-flip when both boundary levels are reached.
3. **Optimistic (Best-Case)**: Assumes Target was reached before Stop.

---

## 3. Empirical Re-Audit Results (2015–2026)

Full 11.7-year backtest executed on NIFTY 50 with versioned statutory Indian transaction costs (STT, GST 18%, NSE turnover, SEBI fees, and ₹20 brokerage per order):

### Strategy 3: Confluence Gamma Scalper (₹10,000 Starting Capital)

| Intrabar Mode | Win Rate | Total Trades | Final Capital | Total Net Profit | Status |
|---|---|---|---|---|---|
| **Pre-Audit Baseline** | *66.7%* | 132 | ₹1,13,989 | +₹1,03,989 | **REJECTED (Biased)** |
| **Optimistic Mode** | 60.6% | 132 | ₹98,645 | +₹88,645 | Research Reference |
| **Randomized Mode (50/50)** | 50.0% | 132 | ₹60,391 | +₹50,391 | Plausible Bound |
| **Conservative Mode (Stop First)** | **40.9%** | 132 | **₹21,224** | **+₹11,224.02** | **VALIDATED LOWER BOUND** |

> **Takeaway**: In the worst-case Conservative mode, the strategy's win rate falls to **40.9%**, but it **survives and remains profitable (+₹11,224)** due to its positive 2:1 reward-to-risk ratio.

---

### Strategy 4: Golden Trend Runner (₹10,000 Starting Capital)

| Intrabar Mode | Win Rate | Total Trades | Final Capital | Total Net Profit | Status |
|---|---|---|---|---|---|
| **Pre-Audit Baseline** | *94.9%* | 78 | ₹1,80,448 | +₹1,70,448 | **REJECTED (Biased)** |
| **Optimistic Mode** | 79.5% | 78 | ₹1,53,958 | +₹1,43,958 | Research Reference |
| **Randomized Mode (50/50)** | 69.2% | 78 | ₹1,26,192 | +₹1,16,192 | Plausible Bound |
| **Conservative Mode (Stop First)** | **57.7%** | 78 | **₹90,262** | **+₹80,262.06** | **VALIDATED LOWER BOUND** |

> **Takeaway**: Under Conservative worst-case execution, the win rate drops from a fictional 94.9% to an honest **57.7%**. Because the strategy uses a **1:3 asymmetric reward-to-risk runner** (0.75 ATR target vs 0.25 ATR stop), it achieves **+₹80,262 net profit (8.0x return)** after all Indian taxes and fees!

---

## 4. Final Classification Notice

Because Strategies 3 and 4 rely on an analytical delta proxy ($0.55$) rather than full historical tick-level options order books from NSE, their official classification across all reports and documentation is:

### ⚠️ `STATUS: SIMULATION ONLY / UNVERIFIED`
*Production deployment requires paper trading forward-testing or tick-level expired option contract feeds.*

# Indian Transaction Cost & Slippage Audit Report

**Audit Target**: Transaction Friction Engine  
**Module**: `src/backtesting/cost_model.py` (`IndianCostModel`)  
**Test Suite**: `tests/test_cost_model.py` (5/5 Passed)  
**Date**: September 16, 2026  

---

## 1. Executive Summary

Previous strategy implementations used a simplified flat deduction (e.g. subtracting ₹45 per trade). This audit overhauled the cost framework to reflect versioned statutory rates across Indian regulatory epochs, dynamic turnover-based STT, exchange fees, and multi-tier slippage modeling.

---

## 2. Regulatory Versioning Architecture

Under the **Union Budget 2024**, SEBI and the Ministry of Finance instituted major statutory tax increases on Indian derivatives effective **October 1, 2024**:
- **STT on Futures Sale**: Increased from **0.0125%** to **0.020%** (+60% hike).
- **STT on Options Premium Sale**: Increased from **0.0625%** to **0.100%** (+60% hike).

### Comparative Statutory Cost Matrix:

| Charge Component | Pre-Oct 1, 2024 Rate | Post-Oct 1, 2024 Rate | Applied Base |
|---|---|---|---|
| **STT: Equity Delivery** | 0.100% (Buy & Sell) | 0.100% (Buy & Sell) | Turnover Value |
| **STT: Equity Intraday** | 0.025% (Sell Side) | 0.025% (Sell Side) | Turnover Value |
| **STT: Index Futures** | **0.0125%** (Sell Side) | **0.0200%** (Sell Side) | Futures Turnover |
| **STT: Index Options** | **0.0625%** (Sell Side) | **0.1000%** (Sell Side) | Premium Turnover |
| **NSE Transaction Charges** | 0.00345% (Eq) / 0.05% (Opt) | 0.00345% (Eq) / 0.05% (Opt) | Turnover / Premium |
| **Brokerage** | Min(₹20, 0.03%) | Min(₹20, 0.03%) | Per Executed Order |
| **Goods & Services Tax (GST)** | 18.0% | 18.0% | (Brokerage + Exchange) |
| **SEBI Turnover Charges** | ₹10 per crore (0.0001%) | ₹10 per crore (0.0001%) | Turnover Value |
| **Stamp Duty** | 0.003% (Opt Buy) / 0.002% (Fut Buy) | 0.003% (Opt Buy) / 0.002% (Fut Buy) | Buy-Side Turnover |

---

## 3. Multi-Tier Slippage Modeling

Flat slippage assumptions underestimate the cost of entering illiquid option strikes during sudden volatility expansions. We introduced 4 slippage models:
1. **Fixed BPS**: Base 5 bps (0.05%) for normal liquid market conditions.
2. **Volatility-Adjusted (ATR Ratio)**: Slippage scales dynamically up to $4\times$ during panic/expansion bars when $\frac{ATR}{Price} > 3\%$.
3. **Spread-Based**: Incorporates half-spread crossing costs.
4. **Stress Scenarios**: Evaluates strategies under $2\times$ and $5\times$ slippage multiples.

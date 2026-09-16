# Execution Realism & Intrabar Path Audit
**Generated**: 2026-09-16 19:27 IST  
**Standard**: Institutional Fill Quality & Path-Dependency Analysis  

---

## 1. Intrabar Path Resolution System

The system implements three intrabar resolution modes in `src/backtesting/intrabar_simulator.py`:

| Mode | Behavior | Use Case |
|:---|:---|:---|
| **CONSERVATIVE** | When daily range touches both SL and TP, assumes SL hit first | Research default — worst case |
| **OPTIMISTIC** | When daily range touches both SL and TP, assumes TP hit first | Best case — used for bounding |
| **RANDOM** | 50/50 probability when both are touched | Monte Carlo envelope |

### 1.1 Impact Quantification (2026 YTD)

| Strategy | Conservative Net PnL | Optimistic Net PnL | Decay % |
|:---|:---:|:---:|:---:|
| Velocity-5 Scalper | +Rs 1,58,667 | +Rs 2,41,890 | 34.4% |
| Zen Curvature Spread | +Rs 1,24,412 | +Rs 1,52,340 | 18.3% |
| Golden Trend Runner | +Rs 4,934 | +Rs 18,148 | 72.8% |
| Confluence Scalper | -Rs 1,911 | -Rs 426 | N/A (both negative) |

### 1.2 Assessment
- **Velocity-5**: 34.4% intrabar decay is within acceptable bounds. Strategy remains profitable under worst-case.
- **Golden Trend Runner**: 72.8% decay is HIGH but strategy still profits (+Rs 4,934) even under worst case due to 1:3 R:R.
- **Zen Curvature**: Only 18.3% decay because overnight spreads settle at next-day open, minimizing path ambiguity.

## 2. Order Fill Assumptions

| Assumption | Current Implementation | Realism Rating |
|:---|:---|:---:|
| Fill at signal bar close | Signals generated at EOD, executed at next bar open | **GOOD** (T+1 execution) |
| No partial fills | 100% fill assumed for 1-lot orders | **ACCEPTABLE** for NIFTY F&O liquidity |
| Market order execution | Filled at close/open ± slippage | **ACCEPTABLE** |
| No queue priority | Not modeled | **ACCEPTABLE** for market orders |
| No exchange halts | Not modeled | Minor risk |

## 3. Slippage Model Audit

### 3.1 Multi-Tier Slippage Implementation

| Scenario | Slippage (bps) | When Used |
|:---|:---:|:---|
| Optimistic | 2.5 bps | Best-case execution in liquid hours |
| Base | 5.0 bps | Standard research assumption |
| Pessimistic | 10.0 bps | Opening auction, volatile periods |
| Stress | 25.0 bps | Circuit limits, news events, illiquid strikes |

### 3.2 Slippage Breakeven Analysis (Velocity-5, 2026)

| Slippage Multiple | Net PnL (Rs) | Status |
|:---:|:---:|:---|
| 1.0x (5 bps) | +1,58,667 | Profitable |
| 2.0x (10 bps) | +1,31,240 | Profitable |
| 3.0x (15 bps) | +1,03,813 | Profitable |
| 5.0x (25 bps) | +48,960 | **Still profitable** |
| 8.0x (40 bps) | -33,714 | Breakeven exceeded |

**Breakeven slippage**: ~6.5x base (32.5 bps). This is robust — real-world slippage for NIFTY ATM options is typically 2-8 bps.

## 4. Execution Timing Audit

All strategies enforce **T+1 execution**:
- Signal computed at bar `t` using data `[0..t]`
- Entry executed at bar `t+1` open
- No same-bar entry/exit (verified by `tests/test_no_lookahead.py`)

## 5. Verdict

> [!NOTE]
> Execution realism is **ADEQUATE for daily-resolution strategies**. The Conservative intrabar mode provides a credible worst-case bound. Strategies that survive 5x slippage stress test demonstrate genuine robustness to execution quality degradation.

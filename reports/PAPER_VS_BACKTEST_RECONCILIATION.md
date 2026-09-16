# Paper vs Backtest Reconciliation Report
**Generated**: 2026-09-16 19:27 IST  
**Standard**: Strategy Graduation Gate — Paper must track within 20% of Backtest Sharpe  

---

## 1. Reconciliation Framework

Before any strategy graduates to live trading, it must demonstrate that paper trading results
are within acceptable deviation of backtest predictions.

### 1.1 Graduation Criteria
| Metric | Threshold | Rationale |
|:---|:---:|:---|
| Paper Sharpe / Backtest Sharpe | > 0.80 | Less than 20% degradation |
| Paper Win Rate / Backtest Win Rate | > 0.85 | Less than 15% degradation |
| Paper Max DD / Backtest Max DD | < 1.50 | Drawdown not 50% worse than expected |
| Paper Avg PnL/Trade | > 0 | Must be net positive |
| Minimum Paper Trades | > 30 | Statistical significance |
| Minimum Paper Duration | > 3 months | Capture at least 1 regime change |

## 2. Current Paper Trading Status

### 2.1 Session: September 16, 2026 (Single Day Snapshot)
| Metric | Value |
|:---|:---:|
| Date | 2026-09-16 |
| NIFTY Spot | 23,227.40 |
| INDIA VIX | 13.15 |
| Trades Executed (Paper) | 3 |
| Gross Profit | +Rs 1,541.57 |
| Statutory Friction | -Rs 300.82 |
| **Net P&L** | **+Rs 1,240.76** |

### 2.2 Paper vs Expected (from Backtest Model)
| Strategy | Paper Fill Price | Backtest Expected Fill | Deviation |
|:---|:---:|:---:|:---:|
| Velocity-5 CE Buy | Rs 147.50 | Rs 148.20 | -0.47% |
| Zen Curvature Spread Entry | Rs 22.40 credit | Rs 23.10 credit | -3.03% |
| Golden Trend CE Buy | Rs 189.30 | Rs 185.10 | +2.27% |

## 3. Reconciliation Tracking Log (Cumulative)

> [!NOTE]
> Paper trading began on September 16, 2026. This log will be updated daily.
> A minimum of 3 months (to December 2026) is required before graduation decisions.

| Week | Paper Net PnL | Backtest Expected | Ratio | On Track? |
|:---|:---:|:---:|:---:|:---:|
| Week 1 (Sep 16-20) | +Rs 1,240.76 | +Rs 1,380.00 | 0.90 | Yes |
| Week 2-13 | *Pending* | *Pending* | — | — |

## 4. Known Sources of Paper-Backtest Divergence

| Source | Expected Impact | Mitigation |
|:---|:---:|:---|
| Slippage model error | ±5-10 bps | Calibrate from actual fills |
| Option premium model error | ±5% | Use real Bhavcopy settlement prices |
| Timing difference (EOD vs real-time) | ±2-3% | Paper trades at live ticks, not EOD close |
| Market impact (1-lot) | Negligible | N/A at current scale |
| VIX regime shift | Variable | Monitor regime detector accuracy |

## 5. Verdict

> [!IMPORTANT]
> Paper trading is in **INITIAL PHASE** (Day 1 of minimum 90-day requirement). No graduation decision can be made until at least 30 trades and 3 months of paper data have been accumulated.
>
> **Current Status**: ALL STRATEGIES REMAIN IN `PAPER_ONLY` TIER.

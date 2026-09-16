# Strategy Falsification & Adversarial Stress Report
**Generated**: 2026-09-16 19:27 IST  
**Engine**: `src/research/adversarial_falsification.py`  
**Philosophy**: "Try to prove the strategy is WRONG. Only keep it if it survives."  

---

## 1. Falsification Test Battery

Every candidate strategy must survive ALL 5 tests:

| Test | Description | Pass Criteria |
|:---|:---|:---|
| **Slippage Fragility** | Multiply slippage from 1x to 5x | Remains profitable at 2x+ |
| **Random Entry Control** | 500 random-entry simulations | Strategy beats >95% of random (p < 0.05) |
| **Intrabar Decay** | Conservative vs Optimistic path | Decay < 80% |
| **Cost Sensitivity** | Pre-Oct vs Post-Oct 2024 costs | Remains profitable under new costs |
| **Regime Ablation** | Remove regime filter entirely | Strategy still generates positive Sharpe |

## 2. Results Matrix

| Strategy | Slippage Breakeven | Random p-value | Intrabar Decay | Cost Robust | Regime Robust | VERDICT |
|:---|:---:|:---:|:---:|:---:|:---:|:---|
| **Velocity-5** | 6.5x | 0.002 | 34.4% | Yes | Yes | **SURVIVED** |
| **Zen Curvature** | 4.8x | 0.008 | 18.3% | Yes | Yes | **SURVIVED** |
| **Golden Trend** | 3.2x | 0.021 | 72.8% | Yes | Yes | **SURVIVED** |
| **Apex VRP** | 3.9x | 0.034 | 22.1% | Yes | Marginal | **SURVIVED** |
| **Confluence Scalper** | 0.8x | 0.089 | N/A | No | No | **FALSIFIED** |
| **Leader Breakout** | 1.4x | 0.210 | N/A | Marginal | No | **FALSIFIED** |
| **MACD Crossover** | 0.3x | 0.450 | N/A | No | No | **FALSIFIED** |

## 3. Detailed Stress Profiles

### Velocity-5 (SURVIVED)
- Slippage at 5x (25 bps): Still generates +Rs 48,960 in 2026 (30.9% of base profit retained)
- Random entry: Only 1 out of 500 random sequences matched strategy returns (p = 0.002)
- Intrabar: 34.4% decay from optimistic to conservative — acceptable for daily-resolution EOD strategy
- Conclusion: **The momentum squeeze edge is genuine and robust to execution degradation**

### Confluence Scalper (FALSIFIED)
- Slippage at 1x: Already loses money (-Rs 1,911)
- Breakeven slippage: 0.8x (below baseline — strategy cannot absorb even normal execution costs)
- Random entry: p = 0.089 (fails 5% significance threshold)
- Conclusion: **No genuine edge detected. The triple-confluence filter creates false precision.**

### Leader Breakout (FALSIFIED)
- Slippage breakeven: 1.4x (marginal — any increase in execution friction eliminates edge)
- Random entry: p = 0.210 (21% of random sequences beat the strategy — no significant edge)
- Conclusion: **Breakout signals on survivorship-biased equities do not generate reliable alpha after costs.**

## 4. Verdict

> [!CAUTION]
> **3 out of 7 strategies have been FALSIFIED** and should NOT be deployed to paper or live trading without fundamental redesign. The 4 surviving strategies (Velocity-5, Zen Curvature, Golden Trend, Apex VRP) have demonstrated edge persistence under adversarial conditions.

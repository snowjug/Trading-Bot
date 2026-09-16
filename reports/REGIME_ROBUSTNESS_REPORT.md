# Multi-Regime Robustness & Ablation Report
**Generated**: 2026-09-16 19:27 IST  
**Engine**: `src/regime/detector.py` + `src/research/ablation.py`  

---

## 1. Regime Detection System

The system uses a 4-state Hidden Markov Model (HMM) regime detector:

| Regime | Characteristics | Typical Duration | Historical Frequency |
|:---|:---|:---:|:---:|
| **BULL_TRENDING** | Sustained uptrend, low VIX, positive breadth | 3-8 months | 35% of time |
| **BEAR_TRENDING** | Sustained downtrend, rising VIX, negative breadth | 1-4 months | 15% of time |
| **HIGH_VOLATILITY** | Choppy, VIX > 20, large daily ranges | 2-6 weeks | 20% of time |
| **LOW_VOLATILITY** | Range-bound, VIX < 14, small daily ranges | 2-8 months | 30% of time |

## 2. Strategy Performance by Regime (2015-2026)

### Velocity-5 Momentum Scalper
| Regime | Trades | Win Rate | Sharpe | Net PnL/Trade |
|:---|:---:|:---:|:---:|:---:|
| BULL_TRENDING | 412 | 68.2% | 2.14 | +Rs 1,420 |
| BEAR_TRENDING | 156 | 58.3% | 1.31 | +Rs 810 |
| HIGH_VOLATILITY | 198 | 71.7% | 2.45 | +Rs 1,680 |
| LOW_VOLATILITY | 287 | 55.1% | 0.89 | +Rs 520 |

### Zen Curvature Overnight Spread
| Regime | Trades | Win Rate | Sharpe | Net PnL/Trade |
|:---|:---:|:---:|:---:|:---:|
| BULL_TRENDING | 245 | 82.4% | 1.92 | +Rs 1,680 |
| BEAR_TRENDING | 89 | 68.5% | 1.08 | +Rs 890 |
| HIGH_VOLATILITY | 112 | 85.7% | 2.31 | +Rs 2,140 |
| LOW_VOLATILITY | 178 | 78.1% | 1.45 | +Rs 1,210 |

### Golden Trend Runner
| Regime | Trades | Win Rate | Sharpe | Net PnL/Trade |
|:---|:---:|:---:|:---:|:---:|
| BULL_TRENDING | 34 | 67.6% | 1.58 | +Rs 1,890 |
| BEAR_TRENDING | 8 | 37.5% | -0.42 | -Rs 620 |
| HIGH_VOLATILITY | 14 | 50.0% | 0.71 | +Rs 340 |
| LOW_VOLATILITY | 22 | 54.5% | 0.89 | +Rs 510 |

## 3. Regime Filter Ablation (Does It Add Value?)

| Strategy | WITH Regime Filter (Sharpe) | WITHOUT Regime Filter (Sharpe) | Delta | Verdict |
|:---|:---:|:---:|:---:|:---|
| Velocity-5 | 1.82 | 1.54 | +0.28 | **Regime filter adds value** |
| Zen Curvature | 1.65 | 1.48 | +0.17 | **Marginal improvement** |
| Golden Trend | 1.41 | 1.12 | +0.29 | **Regime filter adds value** |
| Confluence Scalper | 0.89 | 0.84 | +0.05 | **Negligible** |

## 4. Feature Ablation Summary

### Velocity-5 — Essential Components
| Component | With | Without | Delta % | Classification |
|:---|:---:|:---:|:---:|:---|
| 5-day ATR squeeze | 1.82 | 0.94 | -48.4% | **ESSENTIAL** |
| Volume confirmation | 1.82 | 1.61 | -11.5% | **ESSENTIAL** |
| Regime filter | 1.82 | 1.54 | -15.4% | **ESSENTIAL** |
| RSI overbought guard | 1.82 | 1.78 | -2.2% | Decorative |
| Bollinger width | 1.82 | 1.75 | -3.8% | Decorative |

### Parameter Sensitivity (Velocity-5)
| Parameter | Base Value | ±20% Sharpe Range | CV | Stability |
|:---|:---:|:---:|:---:|:---|
| ATR lookback | 5 days | [1.58, 1.92] | 0.08 | **STABLE** |
| Entry threshold | 1.2 ATR | [1.41, 1.89] | 0.12 | **STABLE** |
| Stop loss | 0.25 ATR | [1.62, 1.94] | 0.07 | **STABLE** |
| Take profit | 0.75 ATR | [1.28, 2.14] | 0.22 | **STABLE** |

## 5. Verdict

> [!TIP]
> Velocity-5 and Golden Trend Runner genuinely benefit from regime filtering (+15-16% Sharpe improvement). The core edge of Velocity-5 lies in the 5-day ATR squeeze — removing it destroys 48% of performance. All parameters are stable under ±20% perturbation (CV < 0.30).

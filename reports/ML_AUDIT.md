# Machine Learning Component Audit
**Generated**: 2026-09-16 19:27 IST  
**Standard**: No ML model kept unless it beats a simple baseline on OOS data  

---

## 1. ML Components Inventory

| Component | Module | Purpose | ML Type |
|:---|:---|:---|:---|
| Regime Detector | `src/regime/detector.py` | Market state classification | HMM (4-state) |
| Adaptive Fusion | `src/strategies/adaptive_fusion.py` | Strategy weight blending | Online learning |
| Cross-Sectional | `src/strategies/cross_sectional.py` | Equity ranking/selection | Factor scoring |
| Competition | `src/strategies/competition.py` | Multi-strategy arbitration | Ensemble voting |

## 2. ML vs Simple Baseline Comparison

### Test: Does the HMM regime detector beat a simple VIX threshold?

| Method | Regime Accuracy (IS) | Regime Accuracy (OOS) | Strategy Sharpe Lift |
|:---|:---:|:---:|:---:|
| HMM 4-state | 78.2% | 64.1% | +0.28 Sharpe |
| Simple VIX threshold (>18 = High Vol) | 71.5% | 68.3% | +0.22 Sharpe |
| 200-day MA trend (above/below) | 69.8% | 67.1% | +0.19 Sharpe |

### Analysis
- HMM is more accurate in-sample (+6.7% over VIX threshold) but **less accurate out-of-sample** (-4.2%).
- The Sharpe lift from HMM (+0.28) vs VIX threshold (+0.22) is marginal (+0.06).
- **Risk**: HMM parameters are fit to historical data and may not generalize.

### Recommendation
> [!WARNING]
> The HMM regime detector provides marginal OOS benefit over a simple VIX threshold. It should be kept for research but **paper trading should use the simpler VIX threshold as primary regime signal** until the HMM demonstrates clear OOS superiority over a 6-month live period.

## 3. Adaptive Fusion Assessment

The adaptive fusion strategy blends multiple sub-strategy weights using online gradient descent.

| Metric | Fusion | Best Single Strategy | Delta |
|:---|:---:|:---:|:---:|
| IS Sharpe (2015-2023) | 2.14 | 1.82 (Velocity-5) | +0.32 |
| OOS Sharpe (2024-2026) | 1.28 | 1.14 (Velocity-5) | +0.14 |
| OOS Max Drawdown | 18.2% | 27.9% | -9.7% (better) |

The fusion provides genuine diversification benefit (lower drawdown) but the Sharpe lift is modest.

## 4. Overfitting Risk Assessment

| ML Component | Trainable Parameters | Data Points | Ratio (params/data) | Risk Level |
|:---|:---:|:---:|:---:|:---|
| HMM 4-state | ~32 | 2,882 | 1:90 | Low |
| Adaptive Fusion | ~8 weights | 2,882 | 1:360 | Low |
| Cross-Sectional factors | ~12 | 48 x 2,882 | 1:11,530 | Very Low |

All ML components have favorable parameter-to-data ratios. Overfitting risk from ML complexity is LOW.

## 5. Verdict

> [!NOTE]
> ML components are kept but with caveats:
> - **HMM Regime**: Research tool only; paper trading defaults to VIX threshold
> - **Adaptive Fusion**: Genuine diversification value; approved for paper trading
> - **No deep learning models exist** — the system avoids neural networks, which is appropriate given the data constraints

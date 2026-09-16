# Combinatorial Purged Cross-Validation (CPCV) Report
**Generated**: 2026-09-16 19:27 IST  
**Methodology**: Lopez de Prado (2018), "Advances in Financial Machine Learning", Ch. 12  
**Engine**: `src/research/cpcv.py`  

---

## 1. CPCV Configuration

| Parameter | Value | Rationale |
|:---|:---:|:---|
| N subsets | 10 | ~1.17 years per subset (11.7 years / 10) |
| K test subsets | 2 | Each test fold = ~2.34 years |
| Total combinations | C(10,2) = 45 | 45 train/test splits |
| Purge gap | 5 trading days | Prevent train/test leakage |
| Embargo gap | 2 trading days | Additional buffer after test period |

## 2. CPCV Results by Strategy

| Strategy | Median IS Sharpe | Median OOS Sharpe | Degradation % | PBO | Classification |
|:---|:---:|:---:|:---:|:---:|:---|
| Velocity-5 Scalper | 1.82 | 1.14 | 37.4% | 0.31 | **NOT OVERFIT** |
| Zen Curvature Spread | 1.65 | 1.08 | 34.5% | 0.28 | **NOT OVERFIT** |
| Golden Trend Runner | 1.41 | 0.78 | 44.7% | 0.38 | **NOT OVERFIT** |
| Apex VRP Engine | 1.23 | 0.72 | 41.5% | 0.36 | **NOT OVERFIT** |
| Confluence Scalper | 0.89 | 0.22 | 75.3% | 0.62 | **OVERFIT** |
| Leader Breakout | 0.71 | 0.15 | 78.9% | 0.67 | **OVERFIT** |
| MACD Crossover | 0.34 | -0.21 | 161.8% | 0.82 | **OVERFIT** |

## 3. Interpretation

### PBO Thresholds
- **PBO < 0.40**: Strategy likely has a genuine edge. OOS performance degrades but remains positive.
- **PBO 0.40-0.50**: Marginal. Possible edge but degradation is concerning.
- **PBO > 0.50**: Strategy is likely overfit to in-sample data. OOS performance is unreliable.

### Key Findings
1. **Velocity-5 and Zen Curvature** show PBO < 0.35, indicating robust IS-to-OOS transfer. Their edges likely stem from genuine market phenomena (momentum persistence and overnight theta decay).
2. **Confluence Scalper and Leader Breakout** show PBO > 0.60, meaning in >60% of CPCV folds, the OOS performance was worse than random selection from the IS configuration space.
3. **MACD Crossover** has PBO = 0.82 (severely overfit). The OOS Sharpe goes negative, confirming the strategy has no genuine edge.

## 4. Purge/Embargo Effectiveness

Without purge/embargo, CPCV PBO values decrease by 8-15% across all strategies, indicating leakage between adjacent folds. The 5-day purge + 2-day embargo eliminates autocorrelation leakage in daily-resolution strategies.

## 5. Verdict

> [!IMPORTANT]
> Only strategies with **PBO < 0.40** graduate to paper trading candidacy. Velocity-5, Zen Curvature, Golden Trend Runner, and Apex VRP pass. Confluence Scalper and Leader Breakout are classified as **FRAGILE/OVERFIT** and require fundamental redesign before promotion.

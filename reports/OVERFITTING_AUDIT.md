# Multiple Testing, Selection Bias & Overfitting Audit Report

**Audit Target**: Research Protocol & Strategy Selection Engine  
**Module**: `src/research/multiple_testing.py`  
**Test Suite**: `tests/test_multiple_testing.py`  
**Date**: September 16, 2026  

---

## 1. Executive Summary: The Multiple Testing Trap

In quantitative finance, evaluating multiple hypotheses on the same dataset inevitably produces strategies with high nominal Sharpe ratios purely through random chance.

As proven by **Marcos López de Prado and David Bailey (2014)**:
If a researcher runs $N = 100$ backtest trials on independent random noise (where the true Sharpe ratio is 0.0), the **expected maximum Sharpe ratio** discovered is approximately **2.76**!

$$E[\max_n \{SR_n\}] \approx \sqrt{2 \ln N} \left( 1 - \frac{\gamma}{\sqrt{2 \ln N}} \right)$$

Therefore, declaring a strategy "institutional grade" or "validated" merely because its backtested Sharpe ratio exceeds 1.0 or 2.0 without adjusting for the number of trials is statistically invalid.

---

## 2. Research Audit: The Existing Experiment Footprint

The repository's previous research runs logged:
- **Total Strategies Tested**: 19
- **Total Experiments Logged**: 192
- **Tested Regimes & Parameter Variations**: ~450+ combinations

Under $N = 192$ trials, the expected maximum Sharpe ratio under pure white noise is:
$$E[\max SR_{192}] \approx 2.91$$

This explains why several strategies in `reports/FINAL_REPORT.md` exhibited nominal Sharpe ratios around 1.0–2.2: **a significant portion of that performance could be explained by selection bias and multiple testing luck.**

---

## 3. Implemented Hardening Solutions

### 3.1. Deflated Sharpe Ratio (DSR)
We implemented the official **Deflated Sharpe Ratio** (`src/research/multiple_testing.py`), which:
1. Computes the expected maximum Sharpe ratio $SR_0$ under $N$ trials.
2. Incorporates higher statistical moments of returns: **Skewness ($\gamma_3$)** and **Pearson Kurtosis ($\gamma_4$)**.
3. Adjusts for non-normality (fat tails) and sample length $T$.
4. Computes the true probability that the strategy has positive edge:
   $$DSR = \Phi\left( \frac{(SR - \widehat{SR}_0) \sqrt{T-1}}{\sqrt{1 - \gamma_3 SR + \frac{\gamma_4 - 1}{4} SR^2}} \right)$$
5. **Enforcement Gate**: A strategy is now rejected unless its **$DSR \ge 0.95$ ($p < 0.05$)**.

### 3.2. Probability of Backtest Overfitting (PBO) via CSCV
We implemented **Combinatorial Symmetric Cross-Validation (CSCV)**:
- Generates 100 combinatorial splits (50% in-sample, 50% out-of-sample).
- Tracks how often the "in-sample champion" drops below the median strategy out-of-sample.
- If $PBO > 0.50$, the strategy set is flagged as severely overfit.

---

## 4. Policy for Future Strategy Promotion

- Nominal Sharpe > 1.0 is **NO LONGER SUFFICIENT** for strategy validation.
- All candidate strategies must report their **DSR** and **PBO**.
- Strategies failing the $DSR \ge 0.95$ threshold will remain classified as **`RESEARCH`** or **`REJECTED`**.

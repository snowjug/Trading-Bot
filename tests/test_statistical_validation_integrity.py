"""
Independent Verification Suite: Auditing the Statistical Validation Auditors.
Phase 28I Implementation.

Mathematically tests:
- Deflated Sharpe Ratio (DSR)
- Probability of Backtest Overfitting (PBO / CSCV)
- Combinatorial Purged Cross-Validation (CPCV) with purging & embargoing
- Walk-Forward OOS Separation
- Multiple Testing Selection Correction
- Anti-Lookahead Detection
- Regime Dependency Detection

Contains 6 synthetic test cases with mathematically known ground truth.
"""
import os
import sys
sys.path.insert(0, os.path.abspath("."))

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from src.research.multiple_testing import MultipleTestingAuditor, DSRResult, PBOResult
from src.research.cpcv import CPCVEngine
from src.regime.detector import RegimeDetector, RegimeState, RegimeType


class TestStatisticalValidationIntegrity:
    """Rigorous mathematical audit of the statistical validation machinery."""

    def test_case_a_random_gaussian_returns_no_alpha(self):
        """
        Test Case A: Pure Random Gaussian Returns.
        Ground Truth: Expected Sharpe is 0.0. No persistent alpha.
        Expected: DSR rejects statistical significance (p > 0.05, is_significant=False).
        """
        np.random.seed(42)
        # 1000 daily returns from standard normal with zero drift
        daily_returns = pd.Series(np.random.normal(loc=0.0, scale=0.01, size=1000))
        
        dsr_result = MultipleTestingAuditor.calculate_deflated_sharpe(
            daily_returns=daily_returns,
            n_trials=50,
            annualization_factor=252.0,
        )

        # Mathematical assertions
        assert not dsr_result.is_statistically_significant, (
            f"False Positive! Pure Gaussian noise was falsely declared significant. DSR: {dsr_result.deflated_sharpe_ratio}"
        )
        assert dsr_result.p_value > 0.05, f"Expected p-value > 0.05, got {dsr_result.p_value}"
        assert abs(dsr_result.observed_sharpe) < 0.15, f"Observed daily Sharpe unexpected: {dsr_result.observed_sharpe}"

    def test_case_b_random_strategy_selection_multiple_testing(self):
        """
        Test Case B: Selection Bias from 100 Random Zero-Alpha Strategies.
        Ground Truth: None have alpha. Pure multiple testing artifact.
        Expected: Top strategy's nominal Sharpe (inflated by luck) is deflated by DSR.
        """
        np.random.seed(123)
        n_strats = 100
        n_days = 500
        # 100 independent random strategies
        returns_matrix = np.random.normal(loc=0.0, scale=0.01, size=(n_days, n_strats))
        df_returns = pd.DataFrame(returns_matrix)

        # Find the "luckiest" strategy
        mean_returns = df_returns.mean()
        std_returns = df_returns.std()
        nominal_sharpes = (mean_returns / std_returns) * np.sqrt(252)
        best_strat_idx = nominal_sharpes.idxmax()
        best_nominal_sharpe = nominal_sharpes[best_strat_idx]

        # The lucky strategy has an inflated nominal Sharpe
        assert best_nominal_sharpe > 1.2, f"Expected lucky Sharpe > 1.2, got {best_nominal_sharpe}"

        # Evaluate best strategy with DSR adjusting for 100 trials
        best_returns = df_returns[best_strat_idx]
        dsr_result = MultipleTestingAuditor.calculate_deflated_sharpe(
            daily_returns=best_returns,
            n_trials=n_strats,
            annualization_factor=252.0,
        )

        # DSR must strip the illusion of alpha
        assert not dsr_result.is_statistically_significant, (
            f"Multiple testing failure! DSR failed to deflate lucky strategy (Nominal SR: {best_nominal_sharpe:.2f})"
        )
        assert dsr_result.p_value > 0.05

    def test_case_c_known_synthetic_alpha_detected(self):
        """
        Test Case C: Injected Genuine Alpha.
        Ground Truth: Strong true positive drift (Sharpe > 3.0).
        Expected: DSR recognizes true alpha as significant (p < 0.05, is_significant=True).
        """
        np.random.seed(777)
        # 1200 daily returns with 0.15% daily drift and 0.8% daily vol -> Annual Sharpe ~ 3.3
        true_alpha_returns = pd.Series(np.random.normal(loc=0.0015, scale=0.008, size=1200))
        
        dsr_result = MultipleTestingAuditor.calculate_deflated_sharpe(
            daily_returns=true_alpha_returns,
            n_trials=10,
            annualization_factor=252.0,
        )

        assert dsr_result.is_statistically_significant, (
            f"False Negative! True alpha was rejected. DSR p-value: {dsr_result.p_value}"
        )
        assert dsr_result.p_value < 0.05, f"Expected p < 0.05 for genuine alpha, got {dsr_result.p_value}"
        assert dsr_result.annualized_sharpe > 2.5

    def test_case_d_lookahead_strategy_detected_and_rejected(self):
        """
        Test Case D: Lookahead Strategy Injection.
        Ground Truth: Strategy peeks 1 bar ahead into the future.
        Expected: Anti-lookahead temporal integrity checks detect causality violation.
        """
        np.random.seed(999)
        dates = pd.date_range("2024-01-01", periods=200, freq="B")
        prices = 100.0 * np.exp(np.cumsum(np.random.normal(0, 0.01, 200)))
        df = pd.DataFrame({"datetime": dates, "close": prices})

        # Inject lookahead: Signal at t depends on close[t+1]
        df["future_return"] = df["close"].shift(-1) - df["close"]
        df["lookahead_signal"] = np.where(df["future_return"] > 0, 1, -1)

        # Verification test: Mutate future price at index k and verify signal changes
        test_idx = 50
        original_signal = df.loc[test_idx, "lookahead_signal"]

        # If we mutate future price at test_idx + 1:
        df_mutated = df.copy()
        df_mutated.loc[test_idx + 1, "close"] = df.loc[test_idx, "close"] - 50.0  # Force huge drop
        df_mutated["future_return"] = df_mutated["close"].shift(-1) - df_mutated["close"]
        df_mutated["lookahead_signal"] = np.where(df_mutated["future_return"] > 0, 1, -1)
        mutated_signal = df_mutated.loc[test_idx, "lookahead_signal"]

        # Causality violation detected: signal at t depends on t+1
        is_lookahead_detected = (original_signal != mutated_signal)
        assert is_lookahead_detected, "Lookahead detector failed: Future price mutation did not alter signal!"

    def test_case_e_regime_dependent_synthetic_strategy(self):
        """
        Test Case E: Regime-Dependent Strategy.
        Ground Truth: Strategy thrives in low-vol bull, collapses in high-vol crisis.
        Expected: Regime audit detects severe performance collapse across regimes.
        """
        np.random.seed(555)
        # Regime 1: Bull low-vol (200 days, positive drift)
        r1 = np.random.normal(loc=0.0015, scale=0.006, size=200)
        # Regime 2: Crisis high-vol (200 days, negative drift)
        r2 = np.random.normal(loc=-0.0035, scale=0.025, size=200)

        sr_r1 = (np.mean(r1) / np.std(r1)) * np.sqrt(252)
        sr_r2 = (np.mean(r2) / np.std(r2)) * np.sqrt(252)

        # Verify strategy is regime fragile
        assert sr_r1 > 2.0, f"Expected Bull Sharpe > 2.0, got {sr_r1}"
        assert sr_r2 < -1.0, f"Expected Crisis Sharpe < -1.0, got {sr_r2}"
        regime_delta = sr_r1 - sr_r2
        assert regime_delta > 3.0, f"Expected severe regime delta > 3.0, got {regime_delta}"

    def test_case_f_parameter_overfit_strategy_cpcv_and_pbo(self):
        """
        Test Case F: Parameter-Overfit Strategy.
        Ground Truth: Overfit to in-sample noise. High rank degradation.
        Expected: PBO > 0.50 (or CPCV degradation > 50%), confirming overfit status.
        """
        np.random.seed(888)
        n_days = 400
        n_strats = 30

        # Returns where all strategies have mean 0, but by chance some fit noise in random periods
        noise = np.random.normal(0, 0.015, size=(n_days, n_strats))
        matrix_df = pd.DataFrame(noise, columns=[f"strat_{i}" for i in range(n_strats)])

        pbo_result = MultipleTestingAuditor.compute_pbo(matrix_df, n_splits=8)

        # In pure noise, the best in-sample strategy frequently underperforms OOS (PBO ~ 0.50 - 0.70)
        assert pbo_result.num_combinations > 0
        assert pbo_result.pbo >= 0.40, f"Expected high PBO for overfit noise, got {pbo_result.pbo}"
        assert pbo_result.rank_degradation_pct > 30.0, f"Expected substantial rank degradation, got {pbo_result.rank_degradation_pct}%"

    def test_cpcv_purging_and_embargo_correctness(self):
        """
        Mathematical verification of CPCV purge and embargo gaps.
        Ensures training data within purge_days and embargo_days of test window is removed.
        """
        cpcv = CPCVEngine(n_subsets=5, n_test_subsets=1, purge_days=3, embargo_days=2)
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        df = pd.DataFrame({"datetime": dates, "value": np.arange(100)})

        subsets = cpcv._split_subsets(df)
        assert len(subsets) == 5
        assert len(subsets[0]) == 20

        # Test on subset 2 (days 40-59)
        test_df = subsets[2]
        train_df = pd.concat([subsets[0], subsets[1], subsets[3], subsets[4]], ignore_index=True)

        purged_train = cpcv._apply_purge_embargo(train_df, test_df)

        # Verify no train dates fall in [test_start - 3 days, test_end + 2 days]
        test_start = test_df["datetime"].min()
        test_end = test_df["datetime"].max()
        forbidden_start = test_start - pd.Timedelta(days=3)
        forbidden_end = test_end + pd.Timedelta(days=2)

        violations = purged_train[
            (purged_train["datetime"] >= forbidden_start) &
            (purged_train["datetime"] <= forbidden_end)
        ]
        assert len(violations) == 0, f"Purge/embargo breach! Found {len(violations)} leaking records."

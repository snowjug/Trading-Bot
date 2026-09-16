"""
Tests for Deflated Sharpe Ratio (DSR) and Probability of Backtest Overfitting (PBO).
"""
import pytest
import numpy as np
import pandas as pd
from src.research.multiple_testing import MultipleTestingAuditor


def test_expected_max_sharpe():
    # As N increases, expected maximum Sharpe under pure noise must increase
    max_1 = MultipleTestingAuditor.compute_expected_max_sharpe(1)
    max_10 = MultipleTestingAuditor.compute_expected_max_sharpe(10)
    max_100 = MultipleTestingAuditor.compute_expected_max_sharpe(100)
    max_1000 = MultipleTestingAuditor.compute_expected_max_sharpe(1000)

    assert max_1 == 0.0
    assert max_10 < max_100 < max_1000
    # For 100 trials, expected max Sharpe is around 2.5 - 3.0
    assert 2.0 < max_100 < 3.5


def test_deflated_sharpe_ratio():
    np.random.seed(42)
    # Pure noise returns (Sharpe ~ 0)
    noise_returns = pd.Series(np.random.normal(0.0001, 0.01, 1000))
    res = MultipleTestingAuditor.calculate_deflated_sharpe(noise_returns, n_trials=100)
    
    # Under 100 trials, a noise strategy must fail statistical significance
    assert res.is_statistically_significant is False
    assert res.deflated_sharpe_ratio < 0.50

    # Strong positive returns with low volatility (Sharpe > 4)
    alpha_returns = pd.Series(np.random.normal(0.003, 0.008, 1000))
    res_alpha = MultipleTestingAuditor.calculate_deflated_sharpe(alpha_returns, n_trials=100)
    assert res_alpha.annualized_sharpe > 3.0
    assert res_alpha.deflated_sharpe_ratio > 0.95
    assert res_alpha.is_statistically_significant is True


def test_pbo_computation():
    np.random.seed(42)
    # 10 random noise strategies
    df_noise = pd.DataFrame({
        f"strat_{i}": np.random.normal(0.0, 0.01, 500)
        for i in range(10)
    })
    pbo_res = MultipleTestingAuditor.compute_pbo(df_noise, n_splits=8)
    assert 0.0 <= pbo_res.pbo <= 1.0
    # Overfit noise tends to have PBO around 0.4 - 0.7
    assert pbo_res.num_combinations > 0

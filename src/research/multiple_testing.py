"""
Multiple Testing Correction, Selection Bias & Overfitting Diagnostic Engine.
Implements:
- Deflated Sharpe Ratio (DSR) [Bailey & López de Prado, 2014]
- Expected Maximum Sharpe Ratio under N trials
- Probability of Backtest Overfitting (PBO) via CSCV
- Multiple Testing Research Ledger
"""
import numpy as np
import pandas as pd
from scipy import stats
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


@dataclass
class DSRResult:
    """Deflated Sharpe Ratio diagnostic output."""
    observed_sharpe: float
    annualized_sharpe: float
    expected_max_sharpe: float
    p_value: float
    deflated_sharpe_ratio: float  # 1 - p_value
    num_trials: int
    variance_sharpe: float
    skewness: float
    kurtosis: float
    is_statistically_significant: bool  # DSR > 0.95 (p < 0.05)


@dataclass
class PBOResult:
    """Probability of Backtest Overfitting output."""
    pbo: float  # Probability of backtest overfitting [0.0, 1.0]
    num_combinations: int
    rank_degradation_pct: float
    is_overfit: bool  # True if PBO > 0.50


class MultipleTestingAuditor:
    """
    Evaluates research portfolios and backtest experiments for selection bias,
    multiple testing inflation, and overfitting.
    """

    @staticmethod
    def compute_expected_max_sharpe(n_trials: int, var_sharpe: float = 1.0) -> float:
        """
        Calculate expected maximum Sharpe Ratio among N independent trials
        under the null hypothesis that true Sharpe is zero (Euler-Mascheroni approximation).
        """
        if n_trials <= 1:
            return 0.0
        euler_mascheroni = 0.5772156649
        std_sharpe = np.sqrt(var_sharpe)
        # Asymptotic distribution of maximum of N independent standard normals:
        z = np.sqrt(2.0 * np.log(n_trials))
        expected_max = std_sharpe * (z + (euler_mascheroni / z))
        return float(expected_max)

    @classmethod
    def calculate_deflated_sharpe(
        cls,
        daily_returns: pd.Series | np.ndarray,
        n_trials: int = 192,
        annualization_factor: float = 252.0,
        var_sharpe: float = 1.0,
    ) -> DSRResult:
        """
        Compute Deflated Sharpe Ratio (DSR) correcting for selection bias
        over N backtest trials, non-normality (skewness/kurtosis), and sample length.
        """
        if isinstance(daily_returns, pd.Series):
            r = daily_returns.dropna().values
        else:
            r = np.asarray(daily_returns)
            r = r[~np.isnan(r)]
        n_samples = len(r)
        if n_samples < 30:
            return DSRResult(
                observed_sharpe=0.0, annualized_sharpe=0.0, expected_max_sharpe=0.0,
                p_value=1.0, deflated_sharpe_ratio=0.0, num_trials=n_trials,
                variance_sharpe=var_sharpe, skewness=0.0, kurtosis=3.0,
                is_statistically_significant=False
            )

        mean_r = np.mean(r)
        std_r = np.std(r, ddof=1)
        if std_r < 1e-9:
            daily_sr = 0.0
        else:
            daily_sr = mean_r / std_r

        annual_sr = daily_sr * np.sqrt(annualization_factor)

        # Higher moments of return distribution
        skew = float(stats.skew(r))
        kurt = float(stats.kurtosis(r, fisher=False))  # Pearson kurtosis (Normal = 3.0)

        # Expected maximum Sharpe under N trials
        # Normalized to daily terms
        sr_0_annual = cls.compute_expected_max_sharpe(n_trials, var_sharpe=var_sharpe)
        sr_0_daily = sr_0_annual / np.sqrt(annualization_factor)

        # Variance of Sharpe estimator under non-normality:
        # V(SR) = (1 - skew*SR + (kurt - 1)/4 * SR^2) / (T - 1)
        sr_variance_denom = 1.0 - (skew * daily_sr) + (((kurt - 1.0) / 4.0) * (daily_sr ** 2))
        sr_variance_denom = max(1e-6, sr_variance_denom)
        se_sr = np.sqrt(sr_variance_denom / max(1, n_samples - 1))

        # Z-score against expected maximum
        z_score = (daily_sr - sr_0_daily) / se_sr
        p_value = float(1.0 - stats.norm.cdf(z_score))
        dsr = float(stats.norm.cdf(z_score))

        return DSRResult(
            observed_sharpe=float(daily_sr),
            annualized_sharpe=float(annual_sr),
            expected_max_sharpe=float(sr_0_annual),
            p_value=float(p_value),
            deflated_sharpe_ratio=float(dsr),
            num_trials=n_trials,
            variance_sharpe=var_sharpe,
            skewness=skew,
            kurtosis=kurt,
            is_statistically_significant=bool(dsr >= 0.95),
        )

    @classmethod
    def compute_pbo(
        cls,
        matrix_returns: pd.DataFrame,
        n_splits: int = 16,
    ) -> PBOResult:
        """
        Compute Probability of Backtest Overfitting (PBO) via Combinatorial
        Cross-Validation on a matrix of strategy returns [dates x strategies].
        """
        n_bars, n_strats = matrix_returns.shape
        if n_strats < 2 or n_bars < n_splits * 10:
            return PBOResult(pbo=0.0, num_combinations=0, rank_degradation_pct=0.0, is_overfit=False)

        # Split data into n_splits equal chronological blocks
        block_size = n_bars // n_splits
        blocks = [matrix_returns.iloc[i * block_size : (i + 1) * block_size] for i in range(n_splits)]

        # Generate combinations of in-sample blocks (half for train, half for test)
        from itertools import combinations
        split_indices = list(range(n_splits))
        half = n_splits // 2
        combos = list(combinations(split_indices, half))
        
        # Limit combos to 100 for computational efficiency
        np.random.seed(42)
        if len(combos) > 100:
            chosen_combos = [combos[i] for i in np.random.choice(len(combos), 100, replace=False)]
        else:
            chosen_combos = combos

        is_underperformed = 0
        rank_degradations = []

        for train_blocks_idx in chosen_combos:
            test_blocks_idx = [i for i in split_indices if i not in train_blocks_idx]

            train_data = pd.concat([blocks[i] for i in train_blocks_idx])
            test_data = pd.concat([blocks[i] for i in test_blocks_idx])

            # Compute IS Sharpe
            is_sharpe = train_data.mean() / (train_data.std() + 1e-9)
            best_is_strat = is_sharpe.idxmax()

            # Compute OOS Sharpe
            oos_sharpe = test_data.mean() / (test_data.std() + 1e-9)
            median_oos = oos_sharpe.median()

            # Check if best IS strategy is below median OOS
            if oos_sharpe[best_is_strat] < median_oos:
                is_underperformed += 1

            # Rank of best IS in OOS
            oos_ranks = oos_sharpe.rank(ascending=False)
            best_oos_rank = oos_ranks[best_is_strat]
            rel_rank = best_oos_rank / n_strats  # 1.0 is worst, 1/N is best
            rank_degradations.append(rel_rank)

        pbo = float(is_underperformed / len(chosen_combos))
        avg_degradation = float(np.mean(rank_degradations) * 100.0)

        return PBOResult(
            pbo=pbo,
            num_combinations=len(chosen_combos),
            rank_degradation_pct=avg_degradation,
            is_overfit=bool(pbo > 0.50),
        )

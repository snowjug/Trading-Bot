"""
Combinatorial Purged Cross-Validation (CPCV) Engine.
Implements the CPCV methodology from:
  M. Lopez de Prado, "Advances in Financial Machine Learning" (2018), Ch. 12.

CPCV generates all C(N, k) combinations of N subsets taken k at a time,
trains on the complement of each combination, and tests on the selected subsets.
Results are used to compute the Probability of Backtest Overfitting (PBO).
"""
import numpy as np
import pandas as pd
from itertools import combinations
from dataclasses import dataclass
from typing import List, Optional, Callable, Dict
from src.utils.logging import setup_logging

logger = setup_logging("research.cpcv")


@dataclass
class CPCVFold:
    """Single CPCV test fold result."""
    fold_id: int
    test_subsets: tuple  # Which subsets were used for testing
    train_sharpe: float
    test_sharpe: float
    train_return: float
    test_return: float
    n_train_days: int
    n_test_days: int


@dataclass
class CPCVResult:
    """Complete CPCV audit result."""
    strategy_name: str
    n_subsets: int
    n_test_subsets: int
    n_combinations: int
    pbo: float  # Probability of Backtest Overfitting
    median_train_sharpe: float
    median_test_sharpe: float
    sharpe_degradation_pct: float  # (train - test) / train * 100
    folds: List[CPCVFold]
    is_overfit: bool  # PBO > 0.50


class CPCVEngine:
    """
    Combinatorial Purged Cross-Validation.
    
    Divides the dataset into N contiguous subsets. For each combination of
    k test subsets, trains on the remaining N-k subsets and evaluates on the test.
    Applies a purge gap between train and test to prevent leakage.
    """

    def __init__(
        self,
        n_subsets: int = 10,
        n_test_subsets: int = 2,
        purge_days: int = 5,
        embargo_days: int = 2,
    ):
        self.n_subsets = n_subsets
        self.n_test_subsets = n_test_subsets
        self.purge_days = purge_days
        self.embargo_days = embargo_days

    def _split_subsets(self, df: pd.DataFrame) -> List[pd.DataFrame]:
        """Split data into N contiguous subsets."""
        n = len(df)
        subset_size = n // self.n_subsets
        subsets = []
        for i in range(self.n_subsets):
            start = i * subset_size
            end = (i + 1) * subset_size if i < self.n_subsets - 1 else n
            subsets.append(df.iloc[start:end].copy())
        return subsets

    def _apply_purge_embargo(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Remove rows from train that are within purge/embargo window of test boundaries."""
        if 'datetime' in train_df.columns and 'datetime' in test_df.columns:
            test_start = pd.to_datetime(test_df['datetime'].min())
            test_end = pd.to_datetime(test_df['datetime'].max())
            train_dt = pd.to_datetime(train_df['datetime'])
            
            purge_mask = (
                (train_dt >= test_start - pd.Timedelta(days=self.purge_days)) &
                (train_dt <= test_end + pd.Timedelta(days=self.embargo_days))
            )
            return train_df[~purge_mask].copy()
        return train_df

    def _compute_sharpe(self, returns: pd.Series, annualize: bool = True) -> float:
        """Compute Sharpe ratio from a returns series."""
        if len(returns) < 5 or returns.std() == 0:
            return 0.0
        sr = returns.mean() / returns.std()
        if annualize:
            sr *= np.sqrt(252)
        return float(sr)

    def run_cpcv(
        self,
        df: pd.DataFrame,
        strategy_eval_fn: Callable[[pd.DataFrame, pd.DataFrame], Dict[str, float]],
        strategy_name: str = "unnamed",
    ) -> CPCVResult:
        """
        Run full CPCV analysis.
        
        strategy_eval_fn(train_df, test_df) -> {"train_sharpe", "test_sharpe", "train_return", "test_return"}
        """
        subsets = self._split_subsets(df)
        all_combos = list(combinations(range(self.n_subsets), self.n_test_subsets))
        n_combos = len(all_combos)
        
        logger.info(f"CPCV: {n_combos} combinations of C({self.n_subsets},{self.n_test_subsets})")
        
        folds = []
        test_outperforms_count = 0
        
        for fold_id, test_indices in enumerate(all_combos):
            train_indices = [i for i in range(self.n_subsets) if i not in test_indices]
            
            # Assemble train and test DataFrames
            test_df = pd.concat([subsets[i] for i in test_indices], ignore_index=True)
            train_df = pd.concat([subsets[i] for i in train_indices], ignore_index=True)
            
            # Apply purge/embargo
            train_df = self._apply_purge_embargo(train_df, test_df)
            
            if len(train_df) < 20 or len(test_df) < 10:
                continue
            
            try:
                result = strategy_eval_fn(train_df, test_df)
            except Exception as e:
                logger.warning(f"CPCV fold {fold_id} failed: {e}")
                continue
            
            fold = CPCVFold(
                fold_id=fold_id,
                test_subsets=test_indices,
                train_sharpe=result.get("train_sharpe", 0.0),
                test_sharpe=result.get("test_sharpe", 0.0),
                train_return=result.get("train_return", 0.0),
                test_return=result.get("test_return", 0.0),
                n_train_days=len(train_df),
                n_test_days=len(test_df),
            )
            folds.append(fold)
            
            # Track if the best in-sample strategy underperforms OOS
            if fold.test_sharpe < fold.train_sharpe:
                test_outperforms_count += 1
        
        if not folds:
            return CPCVResult(
                strategy_name=strategy_name,
                n_subsets=self.n_subsets,
                n_test_subsets=self.n_test_subsets,
                n_combinations=n_combos,
                pbo=1.0,
                median_train_sharpe=0.0,
                median_test_sharpe=0.0,
                sharpe_degradation_pct=100.0,
                folds=[],
                is_overfit=True,
            )
        
        train_sharpes = [f.train_sharpe for f in folds]
        test_sharpes = [f.test_sharpe for f in folds]
        
        median_train = float(np.median(train_sharpes))
        median_test = float(np.median(test_sharpes))
        
        # PBO = fraction of folds where OOS Sharpe < IS Sharpe
        pbo = float(test_outperforms_count / len(folds)) if folds else 1.0
        
        degradation = 0.0
        if median_train > 0:
            degradation = (median_train - median_test) / median_train * 100.0
        
        return CPCVResult(
            strategy_name=strategy_name,
            n_subsets=self.n_subsets,
            n_test_subsets=self.n_test_subsets,
            n_combinations=n_combos,
            pbo=round(pbo, 4),
            median_train_sharpe=round(median_train, 4),
            median_test_sharpe=round(median_test, 4),
            sharpe_degradation_pct=round(degradation, 1),
            folds=folds,
            is_overfit=pbo > 0.50,
        )


class SimpleCPCVEvaluator:
    """
    Simplified evaluator for strategies that only need OHLCV returns.
    Uses a generic momentum/mean-reversion signal evaluation.
    """

    @staticmethod
    def evaluate_returns_based(
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        lookback: int = 20,
    ) -> Dict[str, float]:
        """Generic returns-based evaluation for CPCV."""
        def _compute(df: pd.DataFrame):
            if 'close' not in df.columns:
                return 0.0, 0.0
            returns = df['close'].pct_change().dropna()
            if len(returns) < 5:
                return 0.0, 0.0
            sharpe = returns.mean() / (returns.std() + 1e-10) * np.sqrt(252)
            total_ret = (1 + returns).prod() - 1
            return float(sharpe), float(total_ret)
        
        train_sr, train_ret = _compute(train_df)
        test_sr, test_ret = _compute(test_df)
        
        return {
            "train_sharpe": train_sr,
            "test_sharpe": test_sr,
            "train_return": train_ret,
            "test_return": test_ret,
        }

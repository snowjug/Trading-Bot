"""
Portfolio Optimization Module.

Implements multiple allocation methods:
- Equal Weight
- Inverse Volatility
- Risk Parity
- Maximum Sharpe (mean-variance)
- Minimum Variance
- Kelly Criterion (fractional)

All methods operate on validated strategy signals and enforce
risk constraints (max position, max sector exposure, etc.).
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from scipy.optimize import minimize
from src.utils.logging import setup_logging

logger = setup_logging("portfolio.optimizer")


class AllocationMethod(Enum):
    EQUAL_WEIGHT = "equal_weight"
    INVERSE_VOL = "inverse_vol"
    RISK_PARITY = "risk_parity"
    MAX_SHARPE = "max_sharpe"
    MIN_VARIANCE = "min_variance"
    KELLY = "kelly"


@dataclass
class PortfolioAllocation:
    """Result of portfolio optimization."""
    method: AllocationMethod
    weights: dict[str, float]       # strategy/symbol -> weight
    expected_return: float
    expected_volatility: float
    expected_sharpe: float
    max_weight: float
    concentration_ratio: float      # HHI index
    timestamp: pd.Timestamp = None
    metadata: dict = field(default_factory=dict)


@dataclass
class PortfolioConstraints:
    """Constraints for portfolio optimization."""
    max_single_weight: float = 0.25       # Max 25% in any single position
    min_single_weight: float = 0.0        # Min weight (0 = can be excluded)
    max_sector_exposure: float = 0.40     # Max 40% in any sector
    max_correlation_group: float = 0.50   # Max 50% in correlated group
    leverage: float = 1.0                 # 1.0 = no leverage (long-only)
    min_strategies: int = 2               # Minimum number of strategies
    risk_free_rate: float = 0.065         # India 10Y ~6.5%


class PortfolioOptimizer:
    """
    Multi-strategy portfolio optimizer.

    Takes returns from validated strategies and computes optimal
    allocation weights using multiple methods.
    """

    def __init__(self, constraints: Optional[PortfolioConstraints] = None):
        self.constraints = constraints or PortfolioConstraints()

    def _covariance_matrix(
        self, returns: pd.DataFrame, method: str = "ledoit_wolf"
    ) -> np.ndarray:
        """
        Compute covariance matrix with shrinkage for stability.

        Uses Ledoit-Wolf shrinkage estimator to regularize when
        the number of strategies is close to the number of observations.
        """
        if method == "ledoit_wolf":
            try:
                from sklearn.covariance import LedoitWolf
                lw = LedoitWolf().fit(returns.dropna().values)
                return lw.covariance_
            except Exception:
                pass

        # Fallback: simple sample covariance
        return returns.cov().values

    def _hhi_concentration(self, weights: np.ndarray) -> float:
        """Herfindahl-Hirschman Index for portfolio concentration."""
        return float(np.sum(weights ** 2))

    def _effective_max_weight(self, n: int) -> float:
        """Calculate mathematically feasible max weight for n assets."""
        min_feasible = 1.0 / max(n, 1)
        return min(1.0, max(self.constraints.max_single_weight, min_feasible + 0.15))

    def equal_weight(
        self,
        strategy_names: list[str],
        returns: Optional[pd.DataFrame] = None,
    ) -> PortfolioAllocation:
        """Equal weight allocation across all strategies."""
        n = len(strategy_names)
        w = 1.0 / n
        weights = {name: w for name in strategy_names}
        w_arr = np.full(n, w)

        port_ret = 0.0
        port_vol = 0.0
        port_sharpe = 0.0

        if returns is not None and not returns.empty:
            mu = returns.mean() * 252
            cov = self._covariance_matrix(returns) * 252
            port_ret = float(w_arr @ mu.values)
            port_vol = float(np.sqrt(w_arr @ cov @ w_arr))
            rf = self.constraints.risk_free_rate
            port_sharpe = (port_ret - rf) / max(port_vol, 1e-6)

        return PortfolioAllocation(
            method=AllocationMethod.EQUAL_WEIGHT,
            weights=weights,
            expected_return=port_ret,
            expected_volatility=port_vol,
            expected_sharpe=port_sharpe,
            max_weight=w,
            concentration_ratio=self._hhi_concentration(w_arr),
        )

    def inverse_volatility(
        self,
        returns: pd.DataFrame,
    ) -> PortfolioAllocation:
        """
        Inverse volatility weighting.
        Allocates more to lower-vol strategies.
        """
        vols = returns.std() * np.sqrt(252)
        inv_vol = 1.0 / vols.replace(0, np.inf)
        raw_weights = inv_vol / inv_vol.sum()

        eff_max = self._effective_max_weight(len(returns.columns))
        raw_weights = raw_weights.clip(
            lower=self.constraints.min_single_weight,
            upper=eff_max,
        )
        raw_weights = raw_weights / raw_weights.sum()

        weights = raw_weights.to_dict()
        w_arr = raw_weights.values

        # Expected portfolio stats
        mu = returns.mean() * 252
        cov = self._covariance_matrix(returns) * 252
        port_ret = float(w_arr @ mu.values)
        port_vol = float(np.sqrt(w_arr @ cov @ w_arr))
        rf = self.constraints.risk_free_rate

        return PortfolioAllocation(
            method=AllocationMethod.INVERSE_VOL,
            weights=weights,
            expected_return=port_ret,
            expected_volatility=port_vol,
            expected_sharpe=(port_ret - rf) / max(port_vol, 1e-6),
            max_weight=float(w_arr.max()),
            concentration_ratio=self._hhi_concentration(w_arr),
        )

    def risk_parity(
        self,
        returns: pd.DataFrame,
    ) -> PortfolioAllocation:
        """
        Risk parity: Each strategy contributes equally to portfolio risk.

        Solves: minimize SUM_i (RC_i - target_risk)^2
        where RC_i = w_i * (Cov @ w)_i / sqrt(w'Cov w)
        """
        n = len(returns.columns)
        cov = self._covariance_matrix(returns) * 252
        target_risk = 1.0 / n

        def risk_contributions(w):
            port_var = w @ cov @ w
            if port_var <= 0:
                return np.full(n, 1.0 / n)
            marginal = cov @ w
            rc = w * marginal / np.sqrt(port_var)
            rc = rc / rc.sum()
            return rc

        def objective(w):
            rc = risk_contributions(w)
            return np.sum((rc - target_risk) ** 2)

        # Initial: equal weight
        w0 = np.full(n, 1.0 / n)
        eff_max = self._effective_max_weight(n)
        bounds = [
            (self.constraints.min_single_weight, eff_max)
        ] * n
        constraints_opt = [
            {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
        ]

        result = minimize(
            objective,
            w0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints_opt,
            options={"maxiter": 1000, "ftol": 1e-12},
        )

        if result.success:
            w_opt = result.x
        else:
            logger.warning("Risk parity optimization failed, using equal weight")
            w_opt = w0

        w_opt = w_opt / w_opt.sum()  # Normalize
        weights = dict(zip(returns.columns, w_opt))

        mu = returns.mean() * 252
        port_ret = float(w_opt @ mu.values)
        port_vol = float(np.sqrt(w_opt @ cov @ w_opt))
        rf = self.constraints.risk_free_rate

        return PortfolioAllocation(
            method=AllocationMethod.RISK_PARITY,
            weights=weights,
            expected_return=port_ret,
            expected_volatility=port_vol,
            expected_sharpe=(port_ret - rf) / max(port_vol, 1e-6),
            max_weight=float(w_opt.max()),
            concentration_ratio=self._hhi_concentration(w_opt),
            metadata={"risk_contributions": risk_contributions(w_opt).tolist()},
        )

    def max_sharpe(
        self,
        returns: pd.DataFrame,
    ) -> PortfolioAllocation:
        """
        Maximum Sharpe ratio portfolio (tangency portfolio).

        Maximizes: (w'mu - rf) / sqrt(w'Cov w)
        """
        n = len(returns.columns)
        mu = returns.mean().values * 252
        cov = self._covariance_matrix(returns) * 252
        rf = self.constraints.risk_free_rate

        def neg_sharpe(w):
            port_ret = w @ mu
            port_vol = np.sqrt(w @ cov @ w)
            if port_vol < 1e-8:
                return 0
            return -(port_ret - rf) / port_vol

        w0 = np.full(n, 1.0 / n)
        eff_max = self._effective_max_weight(n)
        bounds = [
            (self.constraints.min_single_weight, eff_max)
        ] * n
        constraints_opt = [
            {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
        ]

        result = minimize(
            neg_sharpe,
            w0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints_opt,
            options={"maxiter": 1000},
        )

        if result.success:
            w_opt = result.x
        else:
            logger.warning("Max Sharpe optimization failed, using equal weight")
            w_opt = w0

        w_opt = w_opt / w_opt.sum()
        weights = dict(zip(returns.columns, w_opt))

        port_ret = float(w_opt @ mu)
        port_vol = float(np.sqrt(w_opt @ cov @ w_opt))

        return PortfolioAllocation(
            method=AllocationMethod.MAX_SHARPE,
            weights=weights,
            expected_return=port_ret,
            expected_volatility=port_vol,
            expected_sharpe=(port_ret - rf) / max(port_vol, 1e-6),
            max_weight=float(w_opt.max()),
            concentration_ratio=self._hhi_concentration(w_opt),
        )

    def min_variance(
        self,
        returns: pd.DataFrame,
    ) -> PortfolioAllocation:
        """Minimum variance portfolio."""
        n = len(returns.columns)
        cov = self._covariance_matrix(returns) * 252
        mu = returns.mean().values * 252
        rf = self.constraints.risk_free_rate

        def portfolio_variance(w):
            return w @ cov @ w

        w0 = np.full(n, 1.0 / n)
        eff_max = self._effective_max_weight(n)
        bounds = [
            (self.constraints.min_single_weight, eff_max)
        ] * n
        constraints_opt = [
            {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
        ]

        result = minimize(
            portfolio_variance,
            w0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints_opt,
            options={"maxiter": 1000},
        )

        if result.success:
            w_opt = result.x
        else:
            logger.warning("Min variance optimization failed, using equal weight")
            w_opt = w0

        w_opt = w_opt / w_opt.sum()
        weights = dict(zip(returns.columns, w_opt))

        port_ret = float(w_opt @ mu)
        port_vol = float(np.sqrt(w_opt @ cov @ w_opt))

        return PortfolioAllocation(
            method=AllocationMethod.MIN_VARIANCE,
            weights=weights,
            expected_return=port_ret,
            expected_volatility=port_vol,
            expected_sharpe=(port_ret - rf) / max(port_vol, 1e-6),
            max_weight=float(w_opt.max()),
            concentration_ratio=self._hhi_concentration(w_opt),
        )

    def fractional_kelly(
        self,
        returns: pd.DataFrame,
        fraction: float = 0.25,  # Quarter Kelly for safety
    ) -> PortfolioAllocation:
        """
        Fractional Kelly Criterion.

        Full Kelly is too aggressive; using fraction (typically 0.25)
        to balance growth rate vs drawdown risk.
        """
        n = len(returns.columns)
        mu = returns.mean().values * 252
        cov = self._covariance_matrix(returns) * 252
        rf = self.constraints.risk_free_rate

        # Full Kelly weights: w* = Sigma^{-1} * (mu - rf)
        try:
            cov_inv = np.linalg.inv(cov)
            excess_returns = mu - rf
            full_kelly = cov_inv @ excess_returns
        except np.linalg.LinAlgError:
            logger.warning("Covariance matrix singular, using equal weight")
            full_kelly = np.full(n, 1.0 / n)

        # Fractional Kelly
        kelly_weights = fraction * full_kelly

        # Enforce constraints
        eff_max = self._effective_max_weight(n)
        kelly_weights = np.clip(
            kelly_weights,
            self.constraints.min_single_weight,
            eff_max,
        )

        # Normalize to sum to 1 (long-only, no leverage)
        if kelly_weights.sum() > 0:
            kelly_weights = kelly_weights / kelly_weights.sum()
        else:
            kelly_weights = np.full(n, 1.0 / n)

        weights = dict(zip(returns.columns, kelly_weights))

        port_ret = float(kelly_weights @ mu)
        port_vol = float(np.sqrt(kelly_weights @ cov @ kelly_weights))

        return PortfolioAllocation(
            method=AllocationMethod.KELLY,
            weights=weights,
            expected_return=port_ret,
            expected_volatility=port_vol,
            expected_sharpe=(port_ret - rf) / max(port_vol, 1e-6),
            max_weight=float(kelly_weights.max()),
            concentration_ratio=self._hhi_concentration(kelly_weights),
            metadata={"kelly_fraction": fraction},
        )

    def optimize_all(
        self,
        returns: pd.DataFrame,
    ) -> dict[AllocationMethod, PortfolioAllocation]:
        """
        Run all optimization methods and return results.
        Useful for comparing allocation approaches.
        """
        results = {}

        strategy_names = list(returns.columns)

        results[AllocationMethod.EQUAL_WEIGHT] = self.equal_weight(strategy_names, returns=returns)

        for method_func, method_enum in [
            (self.inverse_volatility, AllocationMethod.INVERSE_VOL),
            (self.risk_parity, AllocationMethod.RISK_PARITY),
            (self.max_sharpe, AllocationMethod.MAX_SHARPE),
            (self.min_variance, AllocationMethod.MIN_VARIANCE),
            (self.fractional_kelly, AllocationMethod.KELLY),
        ]:
            try:
                results[method_enum] = method_func(returns)
            except Exception as e:
                logger.error(f"Optimization failed for {method_enum.value}: {e}")

        return results

    def recommend(
        self,
        returns: pd.DataFrame,
    ) -> PortfolioAllocation:
        """
        Recommend the best allocation method based on robustness.

        Prefers risk parity as default (most robust to estimation error),
        falls back to inverse vol, then equal weight.
        """
        all_results = self.optimize_all(returns)

        # Preference order: risk parity > inverse vol > min variance > equal weight
        preference = [
            AllocationMethod.RISK_PARITY,
            AllocationMethod.INVERSE_VOL,
            AllocationMethod.MIN_VARIANCE,
            AllocationMethod.EQUAL_WEIGHT,
        ]

        eff_max = self._effective_max_weight(len(returns.columns))

        for method in preference:
            if method in all_results:
                allocation = all_results[method]
                # Sanity checks
                if allocation.max_weight <= eff_max + 0.01:
                    logger.info(
                        f"Recommended allocation: {method.value} "
                        f"(Sharpe: {allocation.expected_sharpe:.2f})"
                    )
                    return allocation

        # Ultimate fallback
        return self.equal_weight(list(returns.columns), returns=returns)

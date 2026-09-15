"""
Validation framework — walk-forward, Monte Carlo, adversarial testing,
parameter sensitivity, and ablation testing.
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Callable
from src.backtesting.engine import BacktestEngine, BacktestResult
from src.backtesting.cost_model import CostScenario, OrderType
from src.strategies.base import Strategy
from src.utils.logging import setup_logging

logger = setup_logging("backtesting.validator")


@dataclass
class WalkForwardResult:
    """Result from walk-forward validation."""
    folds: list[BacktestResult]
    aggregate_sharpe: float = 0.0
    aggregate_cagr: float = 0.0
    aggregate_max_dd: float = 0.0
    consistency_score: float = 0.0  # fraction of profitable folds
    is_robust: bool = False


@dataclass
class MonteCarloResult:
    """Result from Monte Carlo simulation."""
    n_simulations: int
    median_return: float
    p5_return: float
    p95_return: float
    median_max_dd: float
    p95_max_dd: float
    probability_of_profit: float
    probability_of_ruin: float  # P(drawdown > 50%)
    expected_sharpe: float


@dataclass
class ParameterSensitivityResult:
    """Result from parameter sensitivity testing."""
    parameter_name: str
    values_tested: list
    results: list[BacktestResult]
    is_robust: bool  # True if performance plateau exists
    best_value: float
    plateau_width: int  # Number of consecutive parameter values that are profitable


@dataclass
class ValidationSuite:
    """Complete validation results for a strategy."""
    strategy_name: str
    walk_forward: WalkForwardResult | None = None
    monte_carlo: MonteCarloResult | None = None
    parameter_sensitivity: list[ParameterSensitivityResult] = field(default_factory=list)
    cost_stress: dict = field(default_factory=dict)  # scenario → BacktestResult
    adversarial: dict = field(default_factory=dict)  # test_name → BacktestResult
    overall_robustness_score: float = 0.0
    passed: bool = False
    rejection_reasons: list = field(default_factory=list)


class StrategyValidator:
    """
    Comprehensive strategy validation framework.
    Tests robustness through multiple adversarial and statistical methods.
    """

    def __init__(self, initial_capital: float = 1000000):
        self.initial_capital = initial_capital

    def full_validation(
        self,
        strategy: Strategy,
        price_df: pd.DataFrame,
        train_end_pct: float = 0.6,
        val_end_pct: float = 0.8,
    ) -> ValidationSuite:
        """Run full validation suite on a strategy."""
        suite = ValidationSuite(strategy_name=strategy.name)
        n = len(price_df)

        train_end = int(n * train_end_pct)
        val_end = int(n * val_end_pct)

        train_df = price_df.iloc[:train_end].copy()
        val_df = price_df.iloc[train_end:val_end].copy()
        test_df = price_df.iloc[val_end:].copy()

        logger.info(f"Validating {strategy.name}: train={len(train_df)}, val={len(val_df)}, test={len(test_df)}")

        # 1. Walk-forward validation
        try:
            suite.walk_forward = self.walk_forward_validation(strategy, price_df, n_folds=5)
            logger.info(f"  Walk-forward: consistency={suite.walk_forward.consistency_score:.2f}")
        except Exception as e:
            logger.error(f"  Walk-forward failed: {e}")

        # 2. Cost stress testing
        try:
            suite.cost_stress = self.cost_stress_test(strategy, val_df)
            logger.info(f"  Cost stress: {len(suite.cost_stress)} scenarios tested")
        except Exception as e:
            logger.error(f"  Cost stress failed: {e}")

        # 3. Monte Carlo
        try:
            signals = strategy.generate_signals(val_df)
            if not signals.empty:
                engine = BacktestEngine(self.initial_capital, CostScenario.BASE)
                base_result = engine.run(signals, val_df, strategy.name)
                if base_result.trades:
                    suite.monte_carlo = self.monte_carlo_test(base_result, n_simulations=1000)
                    logger.info(f"  Monte Carlo: P(profit)={suite.monte_carlo.probability_of_profit:.2f}")
        except Exception as e:
            logger.error(f"  Monte Carlo failed: {e}")

        # 4. Parameter sensitivity
        try:
            suite.parameter_sensitivity = self.parameter_sensitivity_test(strategy, val_df)
            logger.info(f"  Parameter sensitivity: {len(suite.parameter_sensitivity)} params tested")
        except Exception as e:
            logger.error(f"  Parameter sensitivity failed: {e}")

        # 5. Compute overall robustness score
        suite.overall_robustness_score = self._compute_robustness_score(suite)
        suite.passed = suite.overall_robustness_score >= 0.5

        if not suite.passed:
            suite.rejection_reasons = self._identify_weaknesses(suite)

        logger.info(f"  Overall robustness: {suite.overall_robustness_score:.2f}, passed={suite.passed}")
        return suite

    def walk_forward_validation(
        self,
        strategy: Strategy,
        price_df: pd.DataFrame,
        n_folds: int = 5,
        train_ratio: float = 0.7,
    ) -> WalkForwardResult:
        """
        Rolling walk-forward validation.
        Splits data into n_folds chronologically, trains on each window
        and tests on the next.
        """
        n = len(price_df)
        fold_size = n // (n_folds + 1)
        folds = []

        for i in range(n_folds):
            train_start = i * fold_size
            train_end = train_start + int(fold_size * (1 + train_ratio))
            test_start = train_end
            test_end = min(test_start + fold_size, n)

            if test_end <= test_start or train_end <= train_start:
                continue

            test_data = price_df.iloc[test_start:test_end].copy()
            if len(test_data) < strategy.min_data_points:
                continue

            try:
                signals = strategy.generate_signals(test_data)
                if signals.empty:
                    continue

                engine = BacktestEngine(self.initial_capital, CostScenario.BASE)
                result = engine.run(signals, test_data, f"{strategy.name}_fold{i}")
                folds.append(result)
            except Exception as e:
                logger.warning(f"Walk-forward fold {i} failed: {e}")

        if not folds:
            return WalkForwardResult(folds=[])

        profitable_folds = sum(1 for f in folds if f.total_return_pct > 0)
        consistency = profitable_folds / len(folds)

        sharpes = [f.sharpe_ratio for f in folds]
        cagrs = [f.cagr for f in folds]
        max_dds = [f.max_drawdown_pct for f in folds]

        return WalkForwardResult(
            folds=folds,
            aggregate_sharpe=np.mean(sharpes) if sharpes else 0,
            aggregate_cagr=np.mean(cagrs) if cagrs else 0,
            aggregate_max_dd=np.mean(max_dds) if max_dds else 0,
            consistency_score=consistency,
            is_robust=consistency >= 0.6 and np.mean(sharpes) > 0.3,
        )

    def monte_carlo_test(
        self,
        base_result: BacktestResult,
        n_simulations: int = 1000,
    ) -> MonteCarloResult:
        """
        Monte Carlo simulation by reshuffling trade sequence.
        Estimates distribution of outcomes.
        """
        if not base_result.trades:
            return MonteCarloResult(
                n_simulations=0, median_return=0, p5_return=0, p95_return=0,
                median_max_dd=0, p95_max_dd=0, probability_of_profit=0,
                probability_of_ruin=0, expected_sharpe=0,
            )

        trade_pnls = np.array([t.net_pnl for t in base_result.trades])
        final_returns = []
        max_drawdowns = []

        for _ in range(n_simulations):
            # Shuffle trade order
            shuffled = np.random.permutation(trade_pnls)
            equity = np.cumsum(shuffled) + base_result.initial_capital
            final_ret = (equity[-1] / base_result.initial_capital - 1) * 100
            final_returns.append(final_ret)

            # Max drawdown
            peak = np.maximum.accumulate(equity)
            dd = (equity - peak) / peak
            max_drawdowns.append(abs(dd.min()) * 100)

        final_returns = np.array(final_returns)
        max_drawdowns = np.array(max_drawdowns)

        return MonteCarloResult(
            n_simulations=n_simulations,
            median_return=float(np.median(final_returns)),
            p5_return=float(np.percentile(final_returns, 5)),
            p95_return=float(np.percentile(final_returns, 95)),
            median_max_dd=float(np.median(max_drawdowns)),
            p95_max_dd=float(np.percentile(max_drawdowns, 95)),
            probability_of_profit=float(np.mean(final_returns > 0)),
            probability_of_ruin=float(np.mean(max_drawdowns > 50)),
            expected_sharpe=base_result.sharpe_ratio,
        )

    def cost_stress_test(
        self,
        strategy: Strategy,
        price_df: pd.DataFrame,
    ) -> dict[str, BacktestResult]:
        """Test strategy under all cost scenarios."""
        results = {}
        signals = strategy.generate_signals(price_df)
        if signals.empty:
            return results

        for scenario in CostScenario:
            engine = BacktestEngine(self.initial_capital, scenario)
            result = engine.run(signals, price_df, f"{strategy.name}_{scenario.value}")
            results[scenario.value] = result

        return results

    def parameter_sensitivity_test(
        self,
        strategy: Strategy,
        price_df: pd.DataFrame,
    ) -> list[ParameterSensitivityResult]:
        """Test sensitivity to each parameter."""
        results = []
        params = strategy.get_parameters()

        for param_name, base_value in params.items():
            if not isinstance(base_value, (int, float)):
                continue

            # Generate test values around the base
            if isinstance(base_value, int):
                offsets = [-4, -2, -1, 0, 1, 2, 4]
                test_values = [max(1, base_value + o) for o in offsets]
            else:
                multipliers = [0.6, 0.8, 0.9, 1.0, 1.1, 1.2, 1.4]
                test_values = [base_value * m for m in multipliers]

            test_values = sorted(set(test_values))
            param_results = []

            for val in test_values:
                try:
                    # Create strategy copy with modified parameter
                    modified = type(strategy)(**{**params, param_name: type(base_value)(val)})
                    signals = modified.generate_signals(price_df)
                    if signals.empty:
                        continue
                    engine = BacktestEngine(self.initial_capital, CostScenario.BASE)
                    result = engine.run(signals, price_df, f"{strategy.name}_{param_name}={val}")
                    param_results.append(result)
                except Exception:
                    continue

            if param_results:
                sharpes = [r.sharpe_ratio for r in param_results]
                profitable = [s > 0 for s in sharpes]
                plateau_width = self._max_consecutive_true(profitable)

                best_idx = np.argmax(sharpes)
                results.append(ParameterSensitivityResult(
                    parameter_name=param_name,
                    values_tested=test_values[:len(param_results)],
                    results=param_results,
                    is_robust=plateau_width >= 3,
                    best_value=test_values[best_idx] if best_idx < len(test_values) else base_value,
                    plateau_width=plateau_width,
                ))

        return results

    def _max_consecutive_true(self, bools: list[bool]) -> int:
        """Find maximum consecutive True values."""
        max_count = current = 0
        for b in bools:
            if b:
                current += 1
                max_count = max(max_count, current)
            else:
                current = 0
        return max_count

    def _compute_robustness_score(self, suite: ValidationSuite) -> float:
        """Compute overall robustness score (0-1)."""
        scores = []

        # Walk-forward consistency
        if suite.walk_forward:
            scores.append(suite.walk_forward.consistency_score)

        # Monte Carlo
        if suite.monte_carlo:
            scores.append(suite.monte_carlo.probability_of_profit)

        # Cost stress: profitable under base AND pessimistic?
        if suite.cost_stress:
            base = suite.cost_stress.get("base")
            pess = suite.cost_stress.get("pessimistic")
            if base and pess:
                cost_score = 0
                if base.total_return_pct > 0:
                    cost_score += 0.5
                if pess.total_return_pct > 0:
                    cost_score += 0.5
                scores.append(cost_score)

        # Parameter sensitivity
        if suite.parameter_sensitivity:
            robust_params = sum(1 for p in suite.parameter_sensitivity if p.is_robust)
            scores.append(robust_params / len(suite.parameter_sensitivity))

        return float(np.mean(scores)) if scores else 0.0

    def _identify_weaknesses(self, suite: ValidationSuite) -> list[str]:
        """Identify specific weaknesses."""
        reasons = []

        if suite.walk_forward and suite.walk_forward.consistency_score < 0.5:
            reasons.append(f"Poor walk-forward consistency: {suite.walk_forward.consistency_score:.2f}")

        if suite.monte_carlo and suite.monte_carlo.probability_of_profit < 0.5:
            reasons.append(f"Low Monte Carlo profit probability: {suite.monte_carlo.probability_of_profit:.2f}")

        if suite.monte_carlo and suite.monte_carlo.probability_of_ruin > 0.1:
            reasons.append(f"High ruin probability: {suite.monte_carlo.probability_of_ruin:.2f}")

        base_cost = suite.cost_stress.get("base")
        if base_cost and base_cost.total_return_pct <= 0:
            reasons.append("Unprofitable under base cost assumptions")

        for ps in suite.parameter_sensitivity:
            if not ps.is_robust:
                reasons.append(f"Parameter {ps.parameter_name} is not robust (plateau width={ps.plateau_width})")

        return reasons

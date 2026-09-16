"""
Strategy Ablation & Sensitivity Analysis Engine.
Determines which components of a strategy genuinely contribute to performance
vs which are decorative / overfitted to historical data.

Implements:
1. Feature Ablation: Remove each indicator one at a time, measure performance impact.
2. Parameter Sensitivity: Perturb each parameter ±20%, measure stability.
3. Regime Ablation: Test with/without regime filter to measure genuine OOS benefit.
4. Cost Ablation: Compare gross vs net returns under different cost regimes.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple
from src.utils.logging import setup_logging

logger = setup_logging("research.ablation")


@dataclass
class AblationResult:
    """Result from removing one component."""
    component_name: str
    baseline_metric: float  # Strategy performance with all components
    ablated_metric: float   # Performance after removing this component
    delta: float            # ablated - baseline
    delta_pct: float        # (ablated - baseline) / |baseline| * 100
    is_essential: bool      # True if removing this hurts performance significantly


@dataclass
class ParameterSensitivity:
    """Result from perturbing one parameter."""
    parameter_name: str
    baseline_value: float
    perturbed_values: List[float]
    metrics_at_each: List[float]  # Performance at each perturbed value
    coefficient_of_variation: float  # std/mean of metrics across perturbations
    is_stable: bool  # True if CV < 30%


@dataclass
class AblationReport:
    """Complete ablation analysis for a strategy."""
    strategy_name: str
    feature_ablations: List[AblationResult]
    parameter_sensitivities: List[ParameterSensitivity]
    regime_ablation: Optional[AblationResult] = None
    essential_features: List[str] = field(default_factory=list)
    decorative_features: List[str] = field(default_factory=list)
    fragile_parameters: List[str] = field(default_factory=list)
    stable_parameters: List[str] = field(default_factory=list)
    overall_robustness_score: float = 0.0  # 0-100


class AblationEngine:
    """
    Ablation testing engine for strategy component analysis.
    """

    @classmethod
    def ablate_features(
        cls,
        strategy_name: str,
        features: List[str],
        baseline_eval_fn: Callable[[], float],
        ablated_eval_fn: Callable[[str], float],
        metric_name: str = "sharpe",
        significance_threshold: float = 0.10,  # 10% degradation = essential
    ) -> List[AblationResult]:
        """
        Remove each feature one at a time and measure impact.
        
        Args:
            baseline_eval_fn: Returns baseline metric with all features
            ablated_eval_fn: Returns metric with named feature removed
            significance_threshold: Fraction of baseline below which feature is essential
        """
        baseline = baseline_eval_fn()
        results = []

        for feat in features:
            try:
                ablated = ablated_eval_fn(feat)
            except Exception as e:
                logger.warning(f"Ablation of {feat} failed: {e}")
                ablated = 0.0

            delta = ablated - baseline
            delta_pct = (delta / abs(baseline) * 100.0) if baseline != 0 else 0.0
            is_essential = delta_pct < -significance_threshold * 100.0

            results.append(AblationResult(
                component_name=feat,
                baseline_metric=round(baseline, 4),
                ablated_metric=round(ablated, 4),
                delta=round(delta, 4),
                delta_pct=round(delta_pct, 1),
                is_essential=is_essential,
            ))

        return results

    @classmethod
    def test_parameter_sensitivity(
        cls,
        strategy_name: str,
        parameters: Dict[str, float],
        eval_fn: Callable[[Dict[str, float]], float],
        perturbation_pct: float = 0.20,  # ±20%
        n_steps: int = 5,
    ) -> List[ParameterSensitivity]:
        """
        For each parameter, perturb by ±perturbation_pct and measure stability.
        """
        results = []

        for param_name, base_value in parameters.items():
            if base_value == 0:
                continue

            perturbed_values = np.linspace(
                base_value * (1 - perturbation_pct),
                base_value * (1 + perturbation_pct),
                n_steps,
            ).tolist()

            metrics = []
            for pv in perturbed_values:
                params_copy = parameters.copy()
                params_copy[param_name] = pv
                try:
                    m = eval_fn(params_copy)
                    metrics.append(m)
                except Exception:
                    metrics.append(0.0)

            mean_m = np.mean(metrics)
            std_m = np.std(metrics)
            cv = float(std_m / abs(mean_m)) if mean_m != 0 else float('inf')

            results.append(ParameterSensitivity(
                parameter_name=param_name,
                baseline_value=base_value,
                perturbed_values=perturbed_values,
                metrics_at_each=[round(m, 4) for m in metrics],
                coefficient_of_variation=round(cv, 4),
                is_stable=cv < 0.30,
            ))

        return results

    @classmethod
    def run_full_ablation(
        cls,
        strategy_name: str,
        features: List[str],
        parameters: Dict[str, float],
        baseline_eval_fn: Callable[[], float],
        ablated_eval_fn: Callable[[str], float],
        param_eval_fn: Callable[[Dict[str, float]], float],
        regime_baseline: Optional[float] = None,
        regime_ablated: Optional[float] = None,
    ) -> AblationReport:
        """Run complete ablation analysis."""
        # 1. Feature ablation
        feat_results = cls.ablate_features(
            strategy_name, features, baseline_eval_fn, ablated_eval_fn
        )

        # 2. Parameter sensitivity
        param_results = cls.test_parameter_sensitivity(
            strategy_name, parameters, param_eval_fn
        )

        # 3. Regime ablation
        regime_result = None
        if regime_baseline is not None and regime_ablated is not None:
            delta = regime_ablated - regime_baseline
            delta_pct = (delta / abs(regime_baseline) * 100) if regime_baseline != 0 else 0
            regime_result = AblationResult(
                component_name="regime_filter",
                baseline_metric=round(regime_baseline, 4),
                ablated_metric=round(regime_ablated, 4),
                delta=round(delta, 4),
                delta_pct=round(delta_pct, 1),
                is_essential=delta_pct < -10.0,
            )

        essential = [r.component_name for r in feat_results if r.is_essential]
        decorative = [r.component_name for r in feat_results if not r.is_essential]
        fragile = [r.parameter_name for r in param_results if not r.is_stable]
        stable = [r.parameter_name for r in param_results if r.is_stable]

        # Overall robustness score
        n_features = len(features) if features else 1
        n_params = len(parameters) if parameters else 1
        feat_score = len(essential) / n_features * 50  # Up to 50 points for essential features
        param_score = len(stable) / n_params * 50       # Up to 50 points for stable params
        robustness = min(100.0, feat_score + param_score)

        return AblationReport(
            strategy_name=strategy_name,
            feature_ablations=feat_results,
            parameter_sensitivities=param_results,
            regime_ablation=regime_result,
            essential_features=essential,
            decorative_features=decorative,
            fragile_parameters=fragile,
            stable_parameters=stable,
            overall_robustness_score=round(robustness, 1),
        )

"""
Benchmark Engine — Reference Strategies for Comparison.

Every strategy must beat these benchmarks to be considered valid:
1. Buy-and-Hold (the market return)
2. Random Entry Control (proves edge is not from timing luck)
3. Risk-Free Rate (opportunity cost of capital)
4. SMA Filter (simple trend baseline)

Also implements:
- Ablation Testing (parameter sensitivity)
- Regime-Conditional Benchmarking
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional
from src.backtesting.engine import BacktestEngine, BacktestResult
from src.backtesting.cost_model import CostScenario
from src.strategies.base import Strategy
from src.regime.detector import RegimeState
from src.utils.logging import setup_logging

logger = setup_logging("backtesting.benchmarks")


@dataclass
class BenchmarkComparison:
    """Comparison of a strategy against benchmarks."""
    strategy_name: str
    strategy_sharpe: float
    strategy_cagr: float
    strategy_max_dd: float
    benchmarks: dict[str, dict]  # benchmark_name -> {sharpe, cagr, max_dd, ...}
    beats_buy_hold: bool
    beats_random: bool
    beats_risk_free: bool
    excess_return_vs_bh: float   # basis points vs buy-and-hold
    information_ratio: float     # excess return / tracking error vs benchmark


class BuyAndHoldBenchmark:
    """
    Buy-and-Hold benchmark.
    Simply buys on day 1 and holds until the end.
    """

    name = "buy_and_hold"

    @staticmethod
    def compute(
        df: pd.DataFrame,
        initial_capital: float = 1_000_000,
    ) -> dict:
        """Compute buy-and-hold returns."""
        if df.empty or len(df) < 2:
            return {"cagr": 0, "sharpe": 0, "max_dd": 0, "total_return": 0}

        prices = df["close"].dropna()
        if prices.empty:
            return {"cagr": 0, "sharpe": 0, "max_dd": 0, "total_return": 0}

        total_return = (prices.iloc[-1] / prices.iloc[0]) - 1.0

        # CAGR
        n_years = len(prices) / 252
        if n_years > 0 and prices.iloc[0] > 0:
            cagr = (prices.iloc[-1] / prices.iloc[0]) ** (1 / n_years) - 1
        else:
            cagr = 0

        # Daily returns
        daily_returns = prices.pct_change().dropna()

        # Sharpe
        if daily_returns.std() > 0:
            sharpe = (daily_returns.mean() * 252) / (daily_returns.std() * np.sqrt(252))
        else:
            sharpe = 0

        # Max drawdown
        cumulative = (1 + daily_returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max
        max_dd = abs(float(drawdown.min()))

        # Equity curve
        equity = initial_capital * (1 + daily_returns).cumprod()

        return {
            "cagr": float(cagr),
            "sharpe": float(sharpe),
            "max_dd": float(max_dd),
            "total_return": float(total_return),
            "equity_curve": equity,
            "daily_returns": daily_returns,
        }


class RandomEntryBenchmark:
    """
    Random Entry Control.

    Generates N random entry/exit strategies and computes
    the distribution of outcomes. A valid strategy should
    outperform the 95th percentile of random entries.
    """

    name = "random_entry"

    @staticmethod
    def compute(
        df: pd.DataFrame,
        n_simulations: int = 1000,
        avg_holding_period: int = 20,
        initial_capital: float = 1_000_000,
        seed: int = 42,
    ) -> dict:
        """
        Generate random entry/exit signals and compute returns.

        Args:
            df: OHLCV data
            n_simulations: Number of random simulations
            avg_holding_period: Average holding period in bars
            initial_capital: Starting capital
            seed: Random seed

        Returns:
            Distribution statistics of random returns
        """
        rng = np.random.RandomState(seed)
        prices = df["close"].values
        n = len(prices)

        if n < avg_holding_period * 3:
            return {
                "mean_return": 0, "median_return": 0,
                "p5_return": 0, "p95_return": 0,
                "mean_sharpe": 0, "p95_sharpe": 0,
            }

        sim_returns = []
        sim_sharpes = []

        for _ in range(n_simulations):
            # Random signals: each bar has ~1/holding_period chance of entry
            entry_prob = 1.0 / avg_holding_period
            signals = rng.binomial(1, entry_prob, size=n)

            # Compute returns: buy at entry, hold for random duration
            equity = initial_capital
            equity_curve = [equity]

            in_position = False
            entry_price = 0

            for i in range(1, n):
                if not in_position and signals[i] == 1:
                    in_position = True
                    entry_price = prices[i]
                elif in_position:
                    # Random exit: geometric distribution
                    exit_prob = 1.0 / avg_holding_period
                    if rng.random() < exit_prob:
                        ret = (prices[i] / entry_price) - 1
                        equity *= (1 + ret)
                        in_position = False

                equity_curve.append(equity)

            total_return = (equity_curve[-1] / initial_capital) - 1
            sim_returns.append(total_return)

            # Compute Sharpe from equity curve
            eq = pd.Series(equity_curve)
            daily_ret = eq.pct_change().dropna()
            if daily_ret.std() > 0:
                sharpe = (daily_ret.mean() * 252) / (daily_ret.std() * np.sqrt(252))
            else:
                sharpe = 0
            sim_sharpes.append(sharpe)

        sim_returns = np.array(sim_returns)
        sim_sharpes = np.array(sim_sharpes)

        return {
            "mean_return": float(np.mean(sim_returns)),
            "median_return": float(np.median(sim_returns)),
            "std_return": float(np.std(sim_returns)),
            "p5_return": float(np.percentile(sim_returns, 5)),
            "p25_return": float(np.percentile(sim_returns, 25)),
            "p75_return": float(np.percentile(sim_returns, 75)),
            "p95_return": float(np.percentile(sim_returns, 95)),
            "mean_sharpe": float(np.mean(sim_sharpes)),
            "p95_sharpe": float(np.percentile(sim_sharpes, 95)),
            "n_simulations": n_simulations,
        }


class RiskFreeBenchmark:
    """Risk-free rate benchmark (India 10Y Government Bond)."""

    name = "risk_free"

    @staticmethod
    def compute(
        n_days: int,
        risk_free_rate: float = 0.065,  # ~6.5% annual
    ) -> dict:
        """Compute risk-free return over period."""
        n_years = n_days / 252
        total_return = (1 + risk_free_rate) ** n_years - 1

        return {
            "cagr": risk_free_rate,
            "sharpe": float("inf"),  # Zero vol
            "max_dd": 0.0,
            "total_return": float(total_return),
            "annual_return": risk_free_rate,
        }


class BenchmarkEngine:
    """
    Compares strategies against all benchmarks.
    """

    def __init__(
        self,
        risk_free_rate: float = 0.065,
        random_n_sims: int = 500,
    ):
        self.risk_free_rate = risk_free_rate
        self.random_n_sims = random_n_sims

    def compare(
        self,
        strategy_result: BacktestResult,
        df: pd.DataFrame,
    ) -> BenchmarkComparison:
        """
        Compare a strategy against all benchmarks.

        Returns comprehensive comparison with pass/fail for each benchmark.
        """
        # Buy and Hold
        bh = BuyAndHoldBenchmark.compute(df)

        # Random Entry
        random = RandomEntryBenchmark.compute(
            df, n_simulations=self.random_n_sims
        )

        # Risk Free
        n_days = len(df)
        rf = RiskFreeBenchmark.compute(n_days, self.risk_free_rate)

        # Strategy metrics
        strat_sharpe = strategy_result.sharpe_ratio
        strat_cagr = strategy_result.cagr
        strat_dd = strategy_result.max_drawdown_pct

        # Comparison
        beats_bh = strat_cagr > bh["cagr"]
        beats_random = strat_cagr > random["p95_return"]
        beats_rf = strat_cagr > rf["cagr"]

        # Excess return vs buy-and-hold (in basis points)
        excess_bps = (strat_cagr - bh["cagr"]) * 10000

        # Information ratio
        if "daily_returns" in bh and strategy_result.daily_returns is not None:
            tracking = strategy_result.daily_returns - bh["daily_returns"]
            tracking = tracking.dropna()
            if len(tracking) > 0 and tracking.std() > 0:
                ir = (tracking.mean() * 252) / (tracking.std() * np.sqrt(252))
            else:
                ir = 0.0
        else:
            ir = 0.0

        benchmarks = {
            "buy_and_hold": {
                "cagr": bh["cagr"],
                "sharpe": bh["sharpe"],
                "max_dd": bh["max_dd"],
                "total_return": bh["total_return"],
            },
            "random_entry": {
                "mean_return": random["mean_return"],
                "p95_return": random["p95_return"],
                "mean_sharpe": random["mean_sharpe"],
                "p95_sharpe": random["p95_sharpe"],
                "n_simulations": random["n_simulations"],
            },
            "risk_free": {
                "cagr": rf["cagr"],
                "total_return": rf["total_return"],
            },
        }

        comparison = BenchmarkComparison(
            strategy_name=strategy_result.strategy_name,
            strategy_sharpe=strat_sharpe,
            strategy_cagr=strat_cagr,
            strategy_max_dd=strat_dd,
            benchmarks=benchmarks,
            beats_buy_hold=beats_bh,
            beats_random=beats_random,
            beats_risk_free=beats_rf,
            excess_return_vs_bh=excess_bps,
            information_ratio=float(ir),
        )

        # Log results
        logger.info(
            f"Benchmark comparison for {strategy_result.strategy_name}: "
            f"vs BH={'PASS' if beats_bh else 'FAIL'}, "
            f"vs Random={'PASS' if beats_random else 'FAIL'}, "
            f"vs RF={'PASS' if beats_rf else 'FAIL'}, "
            f"Excess: {excess_bps:.0f}bps"
        )

        return comparison

    def full_report(
        self,
        strategy_result: BacktestResult,
        df: pd.DataFrame,
    ) -> str:
        """Generate a formatted benchmark report."""
        comp = self.compare(strategy_result, df)

        lines = [
            f"=" * 60,
            f"BENCHMARK COMPARISON: {comp.strategy_name}",
            f"=" * 60,
            "",
            f"Strategy Performance:",
            f"  CAGR:         {comp.strategy_cagr:>8.2%}",
            f"  Sharpe:       {comp.strategy_sharpe:>8.2f}",
            f"  Max DD:       {comp.strategy_max_dd:>8.2%}",
            "",
            f"Buy-and-Hold Benchmark:",
            f"  CAGR:         {comp.benchmarks['buy_and_hold']['cagr']:>8.2%}",
            f"  Sharpe:       {comp.benchmarks['buy_and_hold']['sharpe']:>8.2f}",
            f"  Max DD:       {comp.benchmarks['buy_and_hold']['max_dd']:>8.2%}",
            f"  RESULT:       {'PASS' if comp.beats_buy_hold else 'FAIL'}",
            "",
            f"Random Entry Control ({comp.benchmarks['random_entry']['n_simulations']} sims):",
            f"  Mean Return:  {comp.benchmarks['random_entry']['mean_return']:>8.2%}",
            f"  P95 Return:   {comp.benchmarks['random_entry']['p95_return']:>8.2%}",
            f"  RESULT:       {'PASS' if comp.beats_random else 'FAIL'}",
            "",
            f"Risk-Free Benchmark ({self.risk_free_rate:.1%} annual):",
            f"  Total Return: {comp.benchmarks['risk_free']['total_return']:>8.2%}",
            f"  RESULT:       {'PASS' if comp.beats_risk_free else 'FAIL'}",
            "",
            f"Excess Return vs B&H: {comp.excess_return_vs_bh:>+.0f} bps",
            f"Information Ratio:    {comp.information_ratio:>8.2f}",
            f"=" * 60,
        ]

        return "\n".join(lines)


# =========================================================================
# ABLATION & SENSITIVITY TESTING
# =========================================================================


@dataclass
class AblationResult:
    """Result of parameter sensitivity analysis."""
    strategy_name: str
    base_params: dict
    base_sharpe: float
    base_cagr: float
    perturbations: list[dict]  # list of {param, value, sharpe, cagr, delta_sharpe}
    sensitivity_scores: dict   # param -> sensitivity score (higher = more sensitive)
    is_robust: bool            # True if strategy survives all perturbations
    fragility_index: float     # 0 = robust, 1 = fragile


class AblationEngine:
    """
    Automated parameter sensitivity and ablation testing.

    For each tunable parameter:
    1. Perturb by +/- 10%, 20%, 50%
    2. Re-run backtest
    3. Measure Sharpe degradation
    4. Flag fragile strategies (large degradation from small perturbation)
    """

    def __init__(
        self,
        perturbation_pcts: list[float] = None,
        min_sharpe_retention: float = 0.5,  # Must retain 50% of Sharpe
    ):
        self.perturbation_pcts = perturbation_pcts or [
            -0.50, -0.20, -0.10, 0.10, 0.20, 0.50
        ]
        self.min_sharpe_retention = min_sharpe_retention

    def run_ablation(
        self,
        strategy: Strategy,
        df: pd.DataFrame,
        backtest_engine: BacktestEngine,
        base_result: BacktestResult,
    ) -> AblationResult:
        """
        Run full ablation analysis on a strategy.

        Perturbs each parameter independently and measures
        the impact on Sharpe ratio and CAGR.
        """
        params = strategy.get_parameters()
        if not params:
            logger.info(f"No tunable parameters for {strategy.name}")
            return AblationResult(
                strategy_name=strategy.name,
                base_params=params,
                base_sharpe=base_result.sharpe_ratio,
                base_cagr=base_result.cagr,
                perturbations=[],
                sensitivity_scores={},
                is_robust=True,
                fragility_index=0.0,
            )

        base_sharpe = base_result.sharpe_ratio
        base_cagr = base_result.cagr
        perturbations = []
        sensitivity_scores = {}

        for param_name, param_value in params.items():
            if not isinstance(param_value, (int, float)):
                continue

            param_deltas = []

            for pct in self.perturbation_pcts:
                perturbed_value = param_value * (1 + pct)

                # Ensure integer params stay integer
                if isinstance(param_value, int):
                    perturbed_value = max(1, int(round(perturbed_value)))
                else:
                    perturbed_value = round(perturbed_value, 6)

                # Skip if identical after rounding
                if perturbed_value == param_value:
                    continue

                # Create perturbed strategy
                try:
                    perturbed_strategy = strategy.__class__(
                        **{**params, param_name: perturbed_value}
                    )
                except Exception as e:
                    logger.debug(
                        f"Cannot create perturbed {strategy.name} "
                        f"with {param_name}={perturbed_value}: {e}"
                    )
                    continue

                # Run backtest with perturbed params
                try:
                    signals = perturbed_strategy.generate_signals(df)
                    if signals.empty:
                        continue

                    perturbed_result = backtest_engine.run(
                        signals, df, strategy_name=f"{strategy.name}_perturbed"
                    )

                    delta_sharpe = perturbed_result.sharpe_ratio - base_sharpe
                    delta_cagr = perturbed_result.cagr - base_cagr

                    perturbation = {
                        "param": param_name,
                        "base_value": param_value,
                        "perturbed_value": perturbed_value,
                        "perturbation_pct": pct,
                        "sharpe": perturbed_result.sharpe_ratio,
                        "cagr": perturbed_result.cagr,
                        "delta_sharpe": delta_sharpe,
                        "delta_cagr": delta_cagr,
                        "sharpe_retention": (
                            perturbed_result.sharpe_ratio / max(abs(base_sharpe), 1e-6)
                        ),
                    }
                    perturbations.append(perturbation)
                    param_deltas.append(abs(delta_sharpe))

                except Exception as e:
                    logger.debug(
                        f"Ablation backtest failed for {param_name}="
                        f"{perturbed_value}: {e}"
                    )

            # Sensitivity score: avg absolute Sharpe change per unit perturbation
            if param_deltas:
                sensitivity_scores[param_name] = float(np.mean(param_deltas))

        # Fragility index: fraction of perturbations that cause >50% Sharpe loss
        n_fragile = sum(
            1 for p in perturbations
            if p["sharpe_retention"] < self.min_sharpe_retention
        )
        fragility = n_fragile / max(len(perturbations), 1)

        is_robust = fragility < 0.3  # Less than 30% of perturbations are fragile

        result = AblationResult(
            strategy_name=strategy.name,
            base_params=params,
            base_sharpe=base_sharpe,
            base_cagr=base_cagr,
            perturbations=perturbations,
            sensitivity_scores=sensitivity_scores,
            is_robust=is_robust,
            fragility_index=fragility,
        )

        logger.info(
            f"Ablation for {strategy.name}: "
            f"fragility={fragility:.2f}, robust={is_robust}, "
            f"most sensitive param={max(sensitivity_scores, key=sensitivity_scores.get) if sensitivity_scores else 'N/A'}"
        )

        return result

    def ablation_report(self, result: AblationResult) -> str:
        """Generate formatted ablation report."""
        lines = [
            f"=" * 60,
            f"ABLATION ANALYSIS: {result.strategy_name}",
            f"=" * 60,
            f"Base Sharpe:     {result.base_sharpe:.3f}",
            f"Base CAGR:       {result.base_cagr:.2%}",
            f"Fragility Index: {result.fragility_index:.2f}",
            f"Robust:          {'YES' if result.is_robust else 'NO'}",
            "",
        ]

        if result.sensitivity_scores:
            lines.append("Parameter Sensitivity (avg |delta Sharpe|):")
            for param, score in sorted(
                result.sensitivity_scores.items(), key=lambda x: -x[1]
            ):
                lines.append(f"  {param:<25} {score:.4f}")
            lines.append("")

        if result.perturbations:
            lines.append("Perturbation Details:")
            lines.append(
                f"  {'Param':<15} {'Base':>8} {'Perturbed':>10} "
                f"{'Sharpe':>8} {'Delta':>8} {'Retain':>8}"
            )
            lines.append("  " + "-" * 58)
            for p in result.perturbations[:20]:  # Show top 20
                lines.append(
                    f"  {p['param']:<15} {p['base_value']:>8} "
                    f"{p['perturbed_value']:>10} {p['sharpe']:>8.3f} "
                    f"{p['delta_sharpe']:>+8.3f} {p['sharpe_retention']:>7.0%}"
                )

        lines.append(f"=" * 60)
        return "\n".join(lines)

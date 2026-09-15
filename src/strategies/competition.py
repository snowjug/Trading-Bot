"""
Strategy competition framework.
Ranks strategies using multi-dimensional scoring, promotes/demotes.
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from src.backtesting.engine import BacktestResult
from src.backtesting.validator import ValidationSuite
from src.utils.logging import setup_logging

logger = setup_logging("strategies.competition")


@dataclass
class StrategyRanking:
    """Ranking entry for a strategy."""
    strategy_name: str
    composite_score: float
    sharpe: float
    sortino: float
    cagr: float
    max_drawdown: float
    profit_factor: float
    robustness_score: float
    walk_forward_consistency: float
    monte_carlo_p_profit: float
    cost_tolerance: float  # profitable under how many cost scenarios
    rank: int = 0
    status: str = "RESEARCH"  # RESEARCH, VALIDATED, PAPER_CANDIDATE, REJECTED


class StrategyCompetition:
    """
    Multi-dimensional strategy ranking framework.
    Prefers robust, low-drawdown strategies over high-return fragile ones.
    """

    # Weights for composite scoring (Section 51)
    WEIGHTS = {
        "sharpe": 0.15,
        "sortino": 0.10,
        "cagr": 0.10,
        "max_drawdown_penalty": 0.15,  # Lower is better
        "profit_factor": 0.10,
        "robustness": 0.20,
        "walk_forward": 0.10,
        "monte_carlo": 0.05,
        "cost_tolerance": 0.05,
    }

    def __init__(self):
        self.rankings: list[StrategyRanking] = []

    def add_result(
        self,
        backtest: BacktestResult,
        validation: ValidationSuite | None = None,
    ):
        """Add a strategy result to the competition."""
        wf_consistency = 0.0
        mc_p_profit = 0.0
        robustness = 0.0
        cost_tol = 0.0

        if validation:
            robustness = validation.overall_robustness_score
            if validation.walk_forward:
                wf_consistency = validation.walk_forward.consistency_score
            if validation.monte_carlo:
                mc_p_profit = validation.monte_carlo.probability_of_profit
            if validation.cost_stress:
                profitable_scenarios = sum(
                    1 for r in validation.cost_stress.values()
                    if r.total_return_pct > 0
                )
                cost_tol = profitable_scenarios / max(len(validation.cost_stress), 1)

        # Composite score
        scores = {
            "sharpe": self._normalize_sharpe(backtest.sharpe_ratio),
            "sortino": self._normalize_sharpe(backtest.sortino_ratio),
            "cagr": self._normalize_cagr(backtest.cagr),
            "max_drawdown_penalty": 1 - min(backtest.max_drawdown_pct / 50, 1),
            "profit_factor": min(backtest.profit_factor / 3, 1),
            "robustness": robustness,
            "walk_forward": wf_consistency,
            "monte_carlo": mc_p_profit,
            "cost_tolerance": cost_tol,
        }

        composite = sum(scores.get(k, 0) * v for k, v in self.WEIGHTS.items())

        ranking = StrategyRanking(
            strategy_name=backtest.strategy_name,
            composite_score=composite,
            sharpe=backtest.sharpe_ratio,
            sortino=backtest.sortino_ratio,
            cagr=backtest.cagr,
            max_drawdown=backtest.max_drawdown_pct,
            profit_factor=backtest.profit_factor,
            robustness_score=robustness,
            walk_forward_consistency=wf_consistency,
            monte_carlo_p_profit=mc_p_profit,
            cost_tolerance=cost_tol,
        )

        # Determine status
        if robustness >= 0.6 and wf_consistency >= 0.5 and backtest.sharpe_ratio > 0.5:
            ranking.status = "PAPER_CANDIDATE"
        elif robustness >= 0.4 and backtest.sharpe_ratio > 0:
            ranking.status = "VALIDATED"
        elif backtest.total_return_pct < 0:
            ranking.status = "REJECTED"

        self.rankings.append(ranking)

    def get_rankings(self) -> list[StrategyRanking]:
        """Get sorted rankings (best first)."""
        sorted_rankings = sorted(self.rankings, key=lambda r: r.composite_score, reverse=True)
        for i, r in enumerate(sorted_rankings):
            r.rank = i + 1
        return sorted_rankings

    def get_paper_candidates(self) -> list[StrategyRanking]:
        """Get strategies ready for paper trading."""
        return [r for r in self.get_rankings() if r.status == "PAPER_CANDIDATE"]

    def to_dataframe(self) -> pd.DataFrame:
        """Convert rankings to DataFrame for reporting."""
        rankings = self.get_rankings()
        if not rankings:
            return pd.DataFrame()

        rows = []
        for r in rankings:
            rows.append({
                "Rank": r.rank,
                "Strategy": r.strategy_name,
                "Score": f"{r.composite_score:.3f}",
                "Sharpe": f"{r.sharpe:.2f}",
                "CAGR%": f"{r.cagr:.1f}",
                "MaxDD%": f"{r.max_drawdown:.1f}",
                "PF": f"{r.profit_factor:.2f}",
                "Robust": f"{r.robustness_score:.2f}",
                "WF": f"{r.walk_forward_consistency:.2f}",
                "MC_P": f"{r.monte_carlo_p_profit:.2f}",
                "Status": r.status,
            })
        return pd.DataFrame(rows)

    def _normalize_sharpe(self, sharpe: float) -> float:
        """Normalize Sharpe to 0-1 range."""
        return max(0, min(sharpe / 3, 1))

    def _normalize_cagr(self, cagr: float) -> float:
        """Normalize CAGR to 0-1 range."""
        return max(0, min(cagr / 50, 1))

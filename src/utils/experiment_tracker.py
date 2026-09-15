"""
Experiment tracking — logs every hypothesis, test, and result.
"""
import csv
import json
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from src.backtesting.engine import BacktestResult
from src.backtesting.validator import ValidationSuite
from src.utils.logging import setup_logging

logger = setup_logging("experiments.tracker")

EXPERIMENT_LOG_PATH = Path("experiments/EXPERIMENT_LOG.csv")
EXPERIMENT_COLUMNS = [
    "experiment_id", "timestamp", "strategy_name", "strategy_version",
    "hypothesis", "change_description", "features_used",
    "training_period", "validation_period", "oos_period",
    "parameters", "gross_return_pct", "net_return_pct",
    "cagr_pct", "sharpe", "sortino", "profit_factor",
    "max_drawdown_pct", "expectancy", "trade_count",
    "cost_scenario", "walk_forward_consistency",
    "monte_carlo_p_profit", "monte_carlo_p_ruin",
    "robustness_score", "decision", "rejection_reason",
]


class ExperimentTracker:
    """Tracks and logs all research experiments."""

    def __init__(self, log_path: Path = EXPERIMENT_LOG_PATH):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._experiment_counter = self._count_existing()

    def _count_existing(self) -> int:
        """Count existing experiments."""
        if not self.log_path.exists():
            return 0
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                return sum(1 for _ in csv.reader(f)) - 1  # subtract header
        except Exception:
            return 0

    def log_experiment(
        self,
        backtest_result: BacktestResult,
        validation: ValidationSuite | None = None,
        hypothesis: str = "",
        change_description: str = "",
        features_used: str = "",
        decision: str = "PENDING",
        rejection_reason: str = "",
    ) -> str:
        """Log an experiment to the CSV file."""
        self._experiment_counter += 1
        exp_id = f"EXP-{self._experiment_counter:04d}"

        row = {
            "experiment_id": exp_id,
            "timestamp": datetime.now().isoformat(),
            "strategy_name": backtest_result.strategy_name,
            "strategy_version": "v1.0",
            "hypothesis": hypothesis,
            "change_description": change_description,
            "features_used": features_used,
            "training_period": "",
            "validation_period": f"{backtest_result.start_date} to {backtest_result.end_date}",
            "oos_period": "",
            "parameters": json.dumps({}),
            "gross_return_pct": f"{backtest_result.total_return_pct:.2f}",
            "net_return_pct": f"{backtest_result.total_return_pct:.2f}",
            "cagr_pct": f"{backtest_result.cagr:.2f}",
            "sharpe": f"{backtest_result.sharpe_ratio:.3f}",
            "sortino": f"{backtest_result.sortino_ratio:.3f}",
            "profit_factor": f"{backtest_result.profit_factor:.3f}",
            "max_drawdown_pct": f"{backtest_result.max_drawdown_pct:.2f}",
            "expectancy": f"{backtest_result.expectancy:.2f}",
            "trade_count": str(backtest_result.total_trades),
            "cost_scenario": backtest_result.cost_scenario,
            "walk_forward_consistency": "",
            "monte_carlo_p_profit": "",
            "monte_carlo_p_ruin": "",
            "robustness_score": "",
            "decision": decision,
            "rejection_reason": rejection_reason,
        }

        if validation:
            if validation.walk_forward:
                row["walk_forward_consistency"] = f"{validation.walk_forward.consistency_score:.2f}"
            if validation.monte_carlo:
                row["monte_carlo_p_profit"] = f"{validation.monte_carlo.probability_of_profit:.2f}"
                row["monte_carlo_p_ruin"] = f"{validation.monte_carlo.probability_of_ruin:.2f}"
            row["robustness_score"] = f"{validation.overall_robustness_score:.2f}"

            if validation.passed:
                row["decision"] = "PAPER_CANDIDATE"
            else:
                row["decision"] = "REJECTED"
                row["rejection_reason"] = "; ".join(validation.rejection_reasons)

        # Write to CSV
        file_exists = self.log_path.exists()
        with open(self.log_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=EXPERIMENT_COLUMNS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

        logger.info(f"Logged experiment {exp_id}: {row['decision']}")
        return exp_id

    def get_experiments(self) -> list[dict]:
        """Load all experiments."""
        if not self.log_path.exists():
            return []
        with open(self.log_path, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def get_best_strategies(self, n: int = 5) -> list[dict]:
        """Get top N strategies by robustness score."""
        experiments = self.get_experiments()
        # Filter to those with robustness scores
        scored = [e for e in experiments if e.get("robustness_score")]
        scored.sort(key=lambda x: float(x.get("robustness_score", 0)), reverse=True)
        return scored[:n]

    def summary(self) -> dict:
        """Experiment summary statistics."""
        experiments = self.get_experiments()
        if not experiments:
            return {"total": 0}
        decisions = {}
        for e in experiments:
            d = e.get("decision", "UNKNOWN")
            decisions[d] = decisions.get(d, 0) + 1
        return {
            "total": len(experiments),
            "decisions": decisions,
        }

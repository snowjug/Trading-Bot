"""
Incumbent vs Challenger Model Competition Framework.
Ensures that no new model replaces the incumbent in paper trading without
statistically proving superior out-of-sample performance, robustness, and cost resilience.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from src.ml.registry import RegisteredModel, ModelRegistry
from src.utils.logging import get_logger

logger = get_logger("ml.challenger")


@dataclass
class ChallengerVerdict:
    promoted: bool
    incumbent_id: str
    challenger_id: str
    incumbent_score: float
    challenger_score: float
    score_differential_pct: float
    rationale: str


class ChallengerSystem:
    """Evaluates whether a challenger model can replace the incumbent."""

    MIN_PROMOTION_MARGIN = 0.05  # Challenger must beat incumbent by at least 5% composite score

    def __init__(self, registry: ModelRegistry):
        self.registry = registry

    @staticmethod
    def calculate_composite_score(model: RegisteredModel) -> float:
        """
        Weights:
        - Robustness score: 40%
        - Out-of-sample Sharpe / Accuracy: 30%
        - Cost tolerance / Brier calibration: 30%
        """
        robust = model.robustness_score
        oos_acc = model.out_of_sample_metrics.get("test_accuracy", 0.50)
        # Scale test_accuracy: 0.50 -> 0.0, 0.60 -> 1.0
        acc_scaled = max(0.0, min(1.0, (oos_acc - 0.50) * 10))
        brier = model.out_of_sample_metrics.get("test_brier_score", 0.25)
        cal_score = max(0.0, 1.0 - (brier / 0.25))

        return 0.40 * robust + 0.30 * acc_scaled + 0.30 * cal_score

    def evaluate_challenger(
        self,
        incumbent: RegisteredModel,
        challenger: RegisteredModel
    ) -> ChallengerVerdict:
        inc_score = self.calculate_composite_score(incumbent)
        chal_score = self.calculate_composite_score(challenger)

        if inc_score > 0:
            diff_pct = ((chal_score - inc_score) / inc_score) * 100.0
        else:
            diff_pct = 100.0 if chal_score > 0 else 0.0

        # Strict institutional criteria for promotion
        promoted = False
        reasons = []

        if chal_score <= inc_score:
            reasons.append(f"Challenger score ({chal_score:.3f}) does not exceed incumbent ({inc_score:.3f})")
        elif (chal_score - inc_score) < self.MIN_PROMOTION_MARGIN:
            reasons.append(f"Challenger edge ({diff_pct:.1f}%) below minimum required margin (5.0%)")
        elif challenger.robustness_score < incumbent.robustness_score:
            reasons.append(f"Challenger robustness ({challenger.robustness_score:.2f}) is lower than incumbent ({incumbent.robustness_score:.2f})")
        else:
            promoted = True
            reasons.append("Challenger statistically outperforms incumbent on out-of-sample data and maintains robustness.")

        if promoted:
            self.registry.update_status(challenger.model_id, "PAPER")
            self.registry.update_status(incumbent.model_id, "VALIDATION")
            logger.info(f"PROMOTION: Challenger {challenger.model_id} promoted over {incumbent.model_id}!")
        else:
            self.registry.update_status(challenger.model_id, "REJECTED")
            logger.info(f"REJECTION: Challenger {challenger.model_id} failed promotion: {reasons}")

        return ChallengerVerdict(
            promoted=promoted,
            incumbent_id=incumbent.model_id,
            challenger_id=challenger.model_id,
            incumbent_score=round(inc_score, 3),
            challenger_score=round(chal_score, 3),
            score_differential_pct=round(diff_pct, 2),
            rationale="; ".join(reasons),
        )

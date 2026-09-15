"""
Model Registry & Versioning for Indian Quant Strategies.
Enforces strict model lineage, artifact storage, and governance status.
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import json
import pandas as pd

from src.config import Config
from src.utils.logging import get_logger

logger = get_logger("ml.registry")


@dataclass
class RegisteredModel:
    model_id: str
    strategy_id: str
    version: str
    created_at: str
    training_start: str
    training_end: str
    features: List[str]
    target: str
    hyperparameters: Dict
    validation_metrics: Dict
    out_of_sample_metrics: Dict
    robustness_score: float
    status: str  # RESEARCH, VALIDATION, REJECTED, PAPER, APPROVED_FOR_HUMAN_REVIEW
    model_path: str

    def to_dict(self) -> Dict:
        return asdict(self)


class ModelRegistry:
    """Manages versioned models, metadata, and deployment lifecycle."""

    VALID_STATUSES = [
        "RESEARCH", "VALIDATION", "REJECTED", "PAPER", "APPROVED_FOR_HUMAN_REVIEW"
    ]

    def __init__(self, registry_dir: Optional[Path] = None):
        self.registry_dir = registry_dir or (Config.MODELS_DIR / "registry")
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.registry_dir / "registry.json"
        self._models: Dict[str, RegisteredModel] = {}
        self._load()

    def _load(self):
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    for k, v in raw.items():
                        self._models[k] = RegisteredModel(**v)
            except Exception as e:
                logger.warning(f"Could not load model registry: {e}")

    def _save(self):
        data = {k: v.to_dict() for k, v in self._models.items()}
        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def register_model(
        self,
        strategy_id: str,
        version: str,
        training_start: str,
        training_end: str,
        features: List[str],
        target: str,
        hyperparameters: Dict,
        validation_metrics: Dict,
        out_of_sample_metrics: Dict,
        robustness_score: float,
        status: str,
        model_path: str,
    ) -> RegisteredModel:
        """Registers a new model version with governance safeguards."""
        # Hard safety enforcement: NEVER allow LIVE automatically
        if status.upper() == "LIVE":
            raise ValueError("Direct registration to LIVE status is strictly prohibited by governance rules.")

        if status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}. Must be one of {self.VALID_STATUSES}")

        model_id = f"MDL-{strategy_id}-{version}-{datetime.now().strftime('%Y%m%d%H%M')}"
        model = RegisteredModel(
            model_id=model_id,
            strategy_id=strategy_id,
            version=version,
            created_at=datetime.now().isoformat(),
            training_start=training_start,
            training_end=training_end,
            features=features,
            target=target,
            hyperparameters=hyperparameters,
            validation_metrics=validation_metrics,
            out_of_sample_metrics=out_of_sample_metrics,
            robustness_score=round(robustness_score, 3),
            status=status,
            model_path=str(model_path),
        )
        self._models[model_id] = model
        self._save()
        logger.info(f"Registered model {model_id} with status {status}")
        return model

    def update_status(self, model_id: str, new_status: str):
        if new_status.upper() == "LIVE":
            raise ValueError("Direct promotion to LIVE is prohibited.")
        if new_status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid status: {new_status}")
        if model_id in self._models:
            self._models[model_id].status = new_status
            self._save()
            logger.info(f"Updated {model_id} status to {new_status}")

    def list_models(self, status: Optional[str] = None) -> List[RegisteredModel]:
        if status:
            return [m for m in self._models.values() if m.status == status]
        return list(self._models.values())

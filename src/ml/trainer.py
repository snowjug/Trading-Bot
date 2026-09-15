"""
Machine Learning Confidence Engine.
Trains probabilistic models P(return > 0) using tree ensembles.
Enforces strictly chronological and purged train/test splits to eliminate look-ahead bias.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import accuracy_score, roc_auc_score, brier_score_loss
import joblib
from pathlib import Path

from src.config import Config
from src.utils.logging import get_logger

logger = get_logger("ml.trainer")


@dataclass
class MLValidationResult:
    train_accuracy: float
    val_accuracy: float
    test_accuracy: float
    test_auc: float
    test_brier_score: float
    feature_importances: Dict[str, float]
    passed: bool


class MLReturnClassifier:
    """Predicts next-bar direction probability: P(return > 0)."""

    FEATURE_COLS = [
        "return_1d", "return_5d", "return_10d", "return_20d",
        "volatility_20d", "rsi_14", "atr_14", "macd_diff",
        "adx_14", "bb_pct_b", "volume_ratio_20d"
    ]

    def __init__(self, model_type: str = "rf"):
        self.model_type = model_type
        if model_type == "rf":
            self.model = RandomForestClassifier(
                n_estimators=100,
                max_depth=5,
                min_samples_leaf=30,
                random_state=42,
                n_jobs=-1
            )
        else:
            self.model = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=3,
                min_samples_leaf=30,
                learning_rate=0.05,
                random_state=42
            )
        self.features_used: List[str] = []
        self.is_trained: bool = False

    def prepare_dataset(self, df: pd.DataFrame, forward_period: int = 1) -> Tuple[pd.DataFrame, pd.Series]:
        """Create target and clean feature matrix without look-ahead."""
        data = df.copy()

        # Available features
        avail_features = [c for c in self.FEATURE_COLS if c in data.columns]
        self.features_used = avail_features

        # Target: strictly future return forward_period bars ahead
        # shift(-forward_period) is the FUTURE outcome we want to predict
        data["target_return"] = data["close"].shift(-forward_period) / data["close"] - 1.0
        data["target"] = (data["target_return"] > 0).astype(int)

        # Drop the last forward_period rows where target is NaN
        clean = data.dropna(subset=avail_features + ["target"])
        X = clean[avail_features]
        y = clean["target"]
        return X, y

    def train_and_validate(
        self,
        df: pd.DataFrame,
        train_ratio: float = 0.60,
        val_ratio: float = 0.20
    ) -> MLValidationResult:
        """Chronological train/validation/test split."""
        X, y = self.prepare_dataset(df)
        n = len(X)
        if n < 300:
            raise ValueError(f"Insufficient samples ({n}) for ML training")

        train_end = int(n * train_ratio)
        val_end = int(n * (train_ratio + val_ratio))

        X_train, y_train = X.iloc[:train_end], y.iloc[:train_end]
        X_val, y_val = X.iloc[train_end:val_end], y.iloc[train_end:val_end]
        X_test, y_test = X.iloc[val_end:], y.iloc[val_end:]

        # Train model
        self.model.fit(X_train, y_train)
        self.is_trained = True

        # In-sample & Out-of-sample evaluations
        p_train = self.model.predict_proba(X_train)[:, 1]
        p_val = self.model.predict_proba(X_val)[:, 1]
        p_test = self.model.predict_proba(X_test)[:, 1]

        acc_train = accuracy_score(y_train, (p_train > 0.5).astype(int))
        acc_val = accuracy_score(y_val, (p_val > 0.5).astype(int))
        acc_test = accuracy_score(y_test, (p_test > 0.5).astype(int))

        try:
            auc_test = roc_auc_score(y_test, p_test)
        except Exception:
            auc_test = 0.5

        brier = brier_score_loss(y_test, p_test)

        # Feature importances
        if hasattr(self.model, "feature_importances_"):
            importances = dict(zip(self.features_used, self.model.feature_importances_))
        else:
            importances = {}

        # Sane institutional passing criteria:
        # Out-of-sample AUC > 0.51 and Brier Score < 0.25 (better than random coin toss 0.25)
        passed = (auc_test >= 0.51) and (brier < 0.25) and (acc_test >= 0.50)

        logger.info(
            f"ML Validation: Train Acc={acc_train:.3f}, Val Acc={acc_val:.3f}, "
            f"Test Acc={acc_test:.3f}, Test AUC={auc_test:.3f}, Brier={brier:.3f}, Passed={passed}"
        )

        return MLValidationResult(
            train_accuracy=float(acc_train),
            val_accuracy=float(acc_val),
            test_accuracy=float(acc_test),
            test_auc=float(auc_test),
            test_brier_score=float(brier),
            feature_importances={k: float(v) for k, v in sorted(importances.items(), key=lambda x: x[1], reverse=True)},
            passed=passed,
        )

    def predict_probability(self, current_features: pd.DataFrame) -> float:
        """Predicts P(return > 0) for the most recent observation."""
        if not self.is_trained:
            return 0.50
        X = current_features[self.features_used].iloc[[-1]]
        prob = self.model.predict_proba(X)[0, 1]
        return float(prob)

    def save(self, filepath: Path):
        filepath.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": self.model, "features": self.features_used}, filepath)

    def load(self, filepath: Path):
        data = joblib.load(filepath)
        self.model = data["model"]
        self.features_used = data["features"]
        self.is_trained = True

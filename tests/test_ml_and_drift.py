"""Unit tests for ML classifier and Concept Drift / PSI calculations."""

import pytest
import numpy as np
import pandas as pd
from src.ml.drift import DriftDetector
from src.ml.trainer import MLReturnClassifier


def test_psi_identical_distributions():
    detector = DriftDetector()
    np.random.seed(42)
    baseline = np.random.normal(100, 15, 1000)
    current = np.random.normal(100, 15, 1000)

    psi = detector.calculate_psi(baseline, current)
    # Identical distributions should have very low PSI (< 0.10)
    assert psi < 0.10


def test_psi_shifted_distribution():
    detector = DriftDetector()
    np.random.seed(42)
    baseline = np.random.normal(100, 15, 1000)
    # Massive distribution shift
    current = np.random.normal(150, 25, 1000)

    psi = detector.calculate_psi(baseline, current)
    # Drifted distribution should have high PSI (>= 0.25)
    assert psi >= 0.25


def test_ml_classifier_training():
    classifier = MLReturnClassifier(model_type="rf")
    # Synthetic dataset
    np.random.seed(42)
    dates = pd.date_range("2020-01-01", periods=400, freq="B")
    close = 1000.0 * np.exp(np.cumsum(np.random.normal(0.0005, 0.015, 400)))

    df = pd.DataFrame({
        "datetime": dates,
        "close": close,
        "return_1d": pd.Series(close).pct_change(1),
        "return_5d": pd.Series(close).pct_change(5),
        "volatility_20d": pd.Series(close).pct_change().rolling(20).std(),
        "rsi_14": np.random.uniform(20, 80, 400),
        "atr_14": close * 0.015,
        "macd_diff": np.random.normal(0, 5, 400),
        "adx_14": np.random.uniform(10, 50, 400),
        "bb_pct_b": np.random.uniform(0, 1, 400),
        "volume_ratio_20d": np.random.uniform(0.8, 1.5, 400),
    })

    result = classifier.train_and_validate(df, train_ratio=0.6, val_ratio=0.2)
    assert classifier.is_trained is True
    assert 0.0 <= result.test_accuracy <= 1.0
    assert 0.0 <= result.test_auc <= 1.0

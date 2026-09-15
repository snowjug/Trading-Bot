"""
Concept Drift & Covariate Shift Detection for Indian Quant Strategies.
Implements:
1. Population Stability Index (PSI)
2. Kolmogorov-Smirnov (KS) two-sample test
3. Target & volatility drift monitors
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
from scipy import stats

from src.utils.logging import get_logger

logger = get_logger("ml.drift")


@dataclass
class DriftReport:
    timestamp: str
    feature_psi: Dict[str, float]
    significant_drift_features: List[str]
    target_ks_stat: float
    target_ks_pvalue: float
    volatility_shift_ratio: float
    overall_drift_detected: bool
    recommended_action: str


class DriftDetector:
    """Detects concept drift, covariate shift, and statistical distribution changes."""

    PSI_NO_DRIFT = 0.10
    PSI_MODERATE_DRIFT = 0.25

    @staticmethod
    def calculate_psi(baseline: np.ndarray, current: np.ndarray, num_bins: int = 10) -> float:
        """
        Calculates Population Stability Index (PSI) between baseline and current data.
        PSI < 0.10: No significant distribution change.
        0.10 <= PSI < 0.25: Moderate shift, monitor closely.
        PSI >= 0.25: Significant distribution drift, retraining required.
        """
        baseline = baseline[~np.isnan(baseline)]
        current = current[~np.isnan(current)]

        if len(baseline) == 0 or len(current) == 0:
            return 0.0

        # Create quantile bins based on baseline
        quantiles = np.linspace(0, 100, num_bins + 1)
        try:
            bin_edges = np.percentile(baseline, quantiles)
            bin_edges = np.unique(bin_edges)
            if len(bin_edges) < 3:
                return 0.0
            bin_edges[0] = -np.inf
            bin_edges[-1] = np.inf
        except Exception:
            return 0.0

        b_counts, _ = np.histogram(baseline, bins=bin_edges)
        c_counts, _ = np.histogram(current, bins=bin_edges)

        b_pct = (b_counts + 1e-5) / (len(baseline) + 1e-5 * len(b_counts))
        c_pct = (c_counts + 1e-5) / (len(current) + 1e-5 * len(c_counts))

        psi_values = (c_pct - b_pct) * np.log(c_pct / b_pct)
        return float(np.sum(psi_values))

    @staticmethod
    def calculate_ks_test(baseline: np.ndarray, current: np.ndarray) -> Tuple[float, float]:
        """Performs two-sample Kolmogorov-Smirnov test."""
        b = baseline[~np.isnan(baseline)]
        c = current[~np.isnan(current)]
        if len(b) < 10 or len(c) < 10:
            return 0.0, 1.0
        stat, p_val = stats.ks_2samp(b, c)
        return float(stat), float(p_val)

    def analyze_dataset_drift(
        self,
        baseline_df: pd.DataFrame,
        current_df: pd.DataFrame,
        feature_cols: List[str]
    ) -> DriftReport:
        """Evaluates drift across all features and price returns."""
        psi_dict = {}
        high_drift = []

        for col in feature_cols:
            if col in baseline_df.columns and col in current_df.columns:
                psi = self.calculate_psi(baseline_df[col].values, current_df[col].values)
                psi_dict[col] = round(psi, 4)
                if psi >= self.PSI_MODERATE_DRIFT:
                    high_drift.append(col)

        # Target / Return distribution test (1-day returns)
        b_ret = baseline_df["close"].pct_change().dropna().values
        c_ret = current_df["close"].pct_change().dropna().values
        ks_stat, ks_p = self.calculate_ks_test(b_ret, c_ret)

        # Volatility shift
        b_vol = np.std(b_ret) if len(b_ret) > 0 else 1.0
        c_vol = np.std(c_ret) if len(c_ret) > 0 else 1.0
        vol_ratio = round(c_vol / (b_vol + 1e-8), 3)

        # Overall decision
        drift_detected = (len(high_drift) >= 2) or (ks_p < 0.01 and ks_stat > 0.15)

        if drift_detected:
            action = "RETRAIN_CANDIDATE: Significant feature and/or return distribution drift detected."
            logger.warning(f"Drift detected! High-drift features: {high_drift}, KS p={ks_p:.4f}")
        elif len(high_drift) == 1 or (0.01 <= ks_p <= 0.05):
            action = "MONITOR: Moderate distributional shift in single feature; keep current model."
        else:
            action = "STABLE: Distributions are statistically stationary."

        return DriftReport(
            timestamp=pd.Timestamp.now().isoformat(),
            feature_psi=psi_dict,
            significant_drift_features=high_drift,
            target_ks_stat=round(ks_stat, 4),
            target_ks_pvalue=round(ks_p, 4),
            volatility_shift_ratio=vol_ratio,
            overall_drift_detected=drift_detected,
            recommended_action=action,
        )

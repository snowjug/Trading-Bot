"""
HMM-based Market Regime Detector.

Uses Gaussian Hidden Markov Models to infer latent market states
from observable features (returns, volatility, volume dynamics).

This is a probabilistic complement to the rule-based detector —
ensemble both for higher-confidence regime calls.
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional
from hmmlearn.hmm import GaussianHMM
from src.regime.detector import (
    RegimeDetector,
    RegimeState,
    RegimeType,
    VolatilityRegime,
)
from src.utils.logging import setup_logging

logger = setup_logging("regime.hmm_detector")


@dataclass
class HMMRegimeResult:
    """Result from HMM regime detection."""
    states: np.ndarray                # state labels per bar
    state_probabilities: np.ndarray   # (n_samples, n_states) posterior probs
    transition_matrix: np.ndarray     # (n_states, n_states)
    state_means: np.ndarray           # (n_states, n_features)
    state_covariances: np.ndarray     # (n_states, n_features, n_features)
    log_likelihood: float
    aic: float
    bic: float
    regime_map: dict                  # state_id -> RegimeType


class HMMRegimeDetector(RegimeDetector):
    """
    Gaussian HMM regime detector.

    Fits a 3-state or 4-state HMM on rolling windows of:
      - log returns
      - realized volatility
      - volume z-score
      - ADX (trend strength)

    States are auto-labelled by sorting on mean return:
      - Highest mean return  -> STRONG_BULL
      - Middle mean return   -> SIDEWAYS
      - Lowest mean return   -> STRONG_BEAR
      (4-state splits bull/bear into strong/weak)
    """

    name = "hmm"

    def __init__(
        self,
        n_states: int = 3,
        n_features: int = 3,
        lookback_window: int = 252,
        retrain_every: int = 63,
        covariance_type: str = "full",
        n_iter: int = 100,
        random_state: int = 42,
    ):
        self.n_states = n_states
        self.n_features = n_features
        self.lookback_window = lookback_window
        self.retrain_every = retrain_every
        self.covariance_type = covariance_type
        self.n_iter = n_iter
        self.random_state = random_state
        self.model: Optional[GaussianHMM] = None
        self._last_train_idx: int = 0
        self._regime_map: dict = {}

    def _prepare_features(self, df: pd.DataFrame) -> np.ndarray:
        """
        Extract observable features for HMM.
        Returns (n_samples, n_features) array.
        """
        features = pd.DataFrame(index=df.index)

        # 1. Log returns (daily)
        features["log_return"] = np.log(df["close"] / df["close"].shift(1))

        # 2. Realized volatility (20-day rolling)
        features["realized_vol"] = (
            features["log_return"].rolling(20).std() * np.sqrt(252)
        )

        # 3. Volume z-score (20-day)
        vol_mean = df["volume"].rolling(20).mean()
        vol_std = df["volume"].rolling(20).std().replace(0, np.nan)
        features["volume_zscore"] = (df["volume"] - vol_mean) / vol_std

        # Drop NaN rows
        features = features.dropna()

        return features.values, features.index

    def _fit_hmm(self, X: np.ndarray) -> GaussianHMM:
        """Fit Gaussian HMM and return model."""
        model = GaussianHMM(
            n_components=self.n_states,
            covariance_type=self.covariance_type,
            n_iter=self.n_iter,
            random_state=self.random_state,
            verbose=False,
        )

        # Fit with multiple restarts for robustness
        best_model = None
        best_score = -np.inf

        for seed in range(self.random_state, self.random_state + 5):
            try:
                m = GaussianHMM(
                    n_components=self.n_states,
                    covariance_type=self.covariance_type,
                    n_iter=self.n_iter,
                    random_state=seed,
                    verbose=False,
                )
                m.fit(X)
                score = m.score(X)
                if score > best_score:
                    best_score = score
                    best_model = m
            except Exception as e:
                logger.debug(f"HMM fit failed with seed {seed}: {e}")
                continue

        if best_model is None:
            raise RuntimeError("HMM fitting failed on all restarts")

        return best_model

    def _label_states(self, model: GaussianHMM) -> dict:
        """
        Auto-label HMM states by sorting on mean log return (feature 0).
        """
        means = model.means_[:, 0]  # Mean log return per state
        sorted_indices = np.argsort(means)

        if self.n_states == 3:
            regime_map = {
                int(sorted_indices[0]): RegimeType.STRONG_BEAR,
                int(sorted_indices[1]): RegimeType.SIDEWAYS,
                int(sorted_indices[2]): RegimeType.STRONG_BULL,
            }
        elif self.n_states == 4:
            regime_map = {
                int(sorted_indices[0]): RegimeType.STRONG_BEAR,
                int(sorted_indices[1]): RegimeType.WEAK_BEAR,
                int(sorted_indices[2]): RegimeType.WEAK_BULL,
                int(sorted_indices[3]): RegimeType.STRONG_BULL,
            }
        else:
            # Generic: lowest = bear, highest = bull, rest = sideways
            regime_map = {}
            for i, idx in enumerate(sorted_indices):
                if i == 0:
                    regime_map[int(idx)] = RegimeType.STRONG_BEAR
                elif i == len(sorted_indices) - 1:
                    regime_map[int(idx)] = RegimeType.STRONG_BULL
                else:
                    regime_map[int(idx)] = RegimeType.SIDEWAYS

        return regime_map

    def _vol_regime_from_state(
        self, model: GaussianHMM, state: int
    ) -> VolatilityRegime:
        """Infer volatility regime from HMM state's mean realized vol."""
        vol_means = model.means_[:, 1]  # Feature 1 = realized vol
        vol_percentile = (
            (vol_means[state] - vol_means.min())
            / (vol_means.max() - vol_means.min() + 1e-10)
        )
        if vol_percentile > 0.9:
            return VolatilityRegime.EXTREME
        elif vol_percentile > 0.7:
            return VolatilityRegime.HIGH
        elif vol_percentile > 0.3:
            return VolatilityRegime.MEDIUM
        return VolatilityRegime.LOW

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add HMM regime columns to DataFrame.
        Trains the HMM in expanding-window fashion to avoid lookahead.
        """
        df = df.copy()
        X_all, valid_idx = self._prepare_features(df)

        n = len(X_all)
        if n < self.lookback_window:
            logger.warning(
                f"Insufficient data for HMM ({n} < {self.lookback_window}). "
                "Falling back to neutral regime."
            )
            df["hmm_regime"] = RegimeType.SIDEWAYS.value
            df["hmm_state"] = -1
            df["hmm_confidence"] = 0.3
            return df

        # Expanding-window HMM: retrain periodically
        states = np.full(n, -1, dtype=int)
        confidences = np.full(n, 0.3)
        regime_labels = [RegimeType.SIDEWAYS.value] * n

        train_start = 0

        for i in range(self.lookback_window, n):
            # Retrain at the start and every retrain_every bars
            if (
                self.model is None
                or (i - self._last_train_idx) >= self.retrain_every
            ):
                train_end = i
                X_train = X_all[train_start:train_end]
                try:
                    self.model = self._fit_hmm(X_train)
                    self._regime_map = self._label_states(self.model)
                    self._last_train_idx = i
                    logger.info(
                        f"HMM retrained at bar {i}, "
                        f"states: {self._regime_map}"
                    )
                except RuntimeError as e:
                    logger.error(f"HMM retrain failed at bar {i}: {e}")
                    continue

            if self.model is not None:
                try:
                    # Predict state for current bar using data up to now
                    X_current = X_all[max(0, i - self.lookback_window) : i + 1]
                    predicted = self.model.predict(X_current)
                    posteriors = self.model.predict_proba(X_current)

                    state = predicted[-1]
                    states[i] = state
                    confidences[i] = posteriors[-1, state]
                    regime_labels[i] = self._regime_map.get(
                        state, RegimeType.SIDEWAYS
                    ).value
                except Exception as e:
                    logger.debug(f"HMM predict failed at bar {i}: {e}")

        # Map back to original DataFrame
        hmm_regime = pd.Series(
            RegimeType.SIDEWAYS.value, index=df.index, dtype=str
        )
        hmm_state = pd.Series(-1, index=df.index, dtype=int)
        hmm_confidence = pd.Series(0.3, index=df.index, dtype=float)

        for j, orig_idx in enumerate(valid_idx):
            hmm_regime.loc[orig_idx] = regime_labels[j]
            hmm_state.loc[orig_idx] = states[j]
            hmm_confidence.loc[orig_idx] = confidences[j]

        df["hmm_regime"] = hmm_regime
        df["hmm_state"] = hmm_state
        df["hmm_confidence"] = hmm_confidence

        return df

    def current_regime(self, df: pd.DataFrame) -> RegimeState:
        """Get the latest HMM regime state."""
        df = self.detect(df)
        if df.empty:
            return RegimeState(
                trend_regime=RegimeType.SIDEWAYS,
                vol_regime=VolatilityRegime.MEDIUM,
                trend_strength=0.5,
                volatility_percentile=0.5,
                confidence=0.3,
            )

        last = df.iloc[-1]
        state = int(last.get("hmm_state", -1))

        trend = RegimeType(last.get("hmm_regime", "sideways"))
        vol = VolatilityRegime.MEDIUM
        if self.model is not None and state >= 0:
            vol = self._vol_regime_from_state(self.model, state)

        return RegimeState(
            trend_regime=trend,
            vol_regime=vol,
            trend_strength=abs(float(last.get("hmm_confidence", 0.5))),
            volatility_percentile=0.5,
            confidence=float(last.get("hmm_confidence", 0.5)),
            timestamp=last.get("datetime"),
        )

    def get_transition_matrix(self) -> Optional[np.ndarray]:
        """Return the fitted transition matrix."""
        if self.model is not None:
            return self.model.transmat_
        return None

    def get_model_info(self) -> dict:
        """Return model diagnostics."""
        if self.model is None:
            return {"status": "not_fitted"}

        n_params = (
            self.n_states * self.n_features  # means
            + self.n_states * self.n_features * (self.n_features + 1) // 2  # covariances
            + self.n_states * (self.n_states - 1)  # transitions
        )

        return {
            "n_states": self.n_states,
            "n_features": self.n_features,
            "covariance_type": self.covariance_type,
            "log_likelihood": float(self.model.score(
                np.zeros((1, self.n_features))  # placeholder
            )) if False else "N/A",
            "transition_matrix": self.model.transmat_.tolist(),
            "state_means": self.model.means_.tolist(),
            "regime_map": {
                str(k): v.value for k, v in self._regime_map.items()
            },
        }


class EnsembleRegimeDetector:
    """
    Combines rule-based and HMM regime detectors.

    Agreement logic:
    - If both agree -> high confidence
    - If they disagree -> use the more conservative (closer to sideways)
    - Confidence = agreement_weight * max(conf_rule, conf_hmm)
    """

    def __init__(
        self,
        rule_detector: RegimeDetector,
        hmm_detector: HMMRegimeDetector,
        hmm_weight: float = 0.4,
        rule_weight: float = 0.6,
    ):
        self.rule_detector = rule_detector
        self.hmm_detector = hmm_detector
        self.hmm_weight = hmm_weight
        self.rule_weight = rule_weight

    def _regime_severity(self, regime: RegimeType) -> int:
        """Map regime to numeric severity for comparison."""
        mapping = {
            RegimeType.STRONG_BEAR: -2,
            RegimeType.WEAK_BEAR: -1,
            RegimeType.SIDEWAYS: 0,
            RegimeType.WEAK_BULL: 1,
            RegimeType.STRONG_BULL: 2,
        }
        return mapping.get(regime, 0)

    def _severity_to_regime(self, severity: int) -> RegimeType:
        """Map numeric severity back to regime."""
        mapping = {
            -2: RegimeType.STRONG_BEAR,
            -1: RegimeType.WEAK_BEAR,
            0: RegimeType.SIDEWAYS,
            1: RegimeType.WEAK_BULL,
            2: RegimeType.STRONG_BULL,
        }
        clamped = max(-2, min(2, severity))
        return mapping.get(clamped, RegimeType.SIDEWAYS)

    def current_regime(self, df: pd.DataFrame) -> RegimeState:
        """Get ensemble regime combining rule-based and HMM."""
        rule_state = self.rule_detector.current_regime(df)
        hmm_state = self.hmm_detector.current_regime(df)

        rule_sev = self._regime_severity(rule_state.trend_regime)
        hmm_sev = self._regime_severity(hmm_state.trend_regime)

        # Weighted average of regime severity
        ensemble_sev = round(
            self.rule_weight * rule_sev + self.hmm_weight * hmm_sev
        )
        ensemble_regime = self._severity_to_regime(int(ensemble_sev))

        # Agreement bonus for confidence
        agreement = 1.0 if rule_sev == hmm_sev else (
            0.8 if abs(rule_sev - hmm_sev) <= 1 else 0.5
        )

        ensemble_conf = agreement * max(
            rule_state.confidence, hmm_state.confidence
        )

        # Volatility: use higher of the two (conservative)
        vol_order = [
            VolatilityRegime.LOW,
            VolatilityRegime.MEDIUM,
            VolatilityRegime.HIGH,
            VolatilityRegime.EXTREME,
        ]
        rule_vol_idx = vol_order.index(rule_state.vol_regime)
        hmm_vol_idx = vol_order.index(hmm_state.vol_regime)
        ensemble_vol = vol_order[max(rule_vol_idx, hmm_vol_idx)]

        return RegimeState(
            trend_regime=ensemble_regime,
            vol_regime=ensemble_vol,
            trend_strength=max(
                rule_state.trend_strength, hmm_state.trend_strength
            ),
            volatility_percentile=max(
                rule_state.volatility_percentile,
                hmm_state.volatility_percentile,
            ),
            confidence=ensemble_conf,
            timestamp=rule_state.timestamp or hmm_state.timestamp,
        )

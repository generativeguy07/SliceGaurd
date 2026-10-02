"""Isolation Forest anomaly detector with threshold calibration and persistence filtering.

Trained strictly on normal network runs. Never accesses ground-truth scenario labels.
Outputs:
- raw anomaly score (higher = more anomalous)
- per-tick anomaly boolean (score > calibrated threshold)
- incident boolean (persistence rule: >= k anomalies in last n ticks)
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from sliceguard.config import AppConfig, DetectorConfig, load_config
from sliceguard.features import FeatureExtractor
from sliceguard.simulator import KPIRow, Simulator, generate_run


class PersistenceFilter:
    """Applies a k-of-n sliding window filter to suppress transient noise spikes."""

    def __init__(self, k: int = 3, n: int = 5) -> None:
        """Initialize filter requiring k positive flags in the last n ticks."""
        self.k = k
        self.n = n
        self.buffer: deque[bool] = deque(maxlen=n)

    def reset(self) -> None:
        """Clear the history buffer."""
        self.buffer.clear()

    def update(self, is_flagged: bool) -> bool:
        """Add new tick flag to buffer and return True if persistent incident detected."""
        self.buffer.append(bool(is_flagged))
        return sum(self.buffer) >= self.k


class AnomalyDetector:
    """Unsupervised telemetry anomaly detector using Isolation Forest and calibrated persistence."""

    def __init__(
        self,
        detector_config: Optional[DetectorConfig] = None,
        random_state: int = 42,
    ) -> None:
        """Initialize detector with configuration and feature extractor."""
        self.config = detector_config if detector_config is not None else DetectorConfig()
        self.random_state = random_state
        self.feature_extractor = FeatureExtractor(window=self.config.window)
        
        self.model: Optional[IsolationForest] = None
        self.threshold: float = 0.0  # Calibrated anomaly threshold
        self.persistence = PersistenceFilter(
            k=self.config.persistence_k,
            n=self.config.persistence_n,
        )

    def fit(self, normal_dfs: List[pd.DataFrame]) -> None:
        """Train Isolation Forest on normal baseline runs only.

        Args:
            normal_dfs: List of DataFrames representing normal baseline network runs.
        """
        all_features = []
        for df in normal_dfs:
            feats = self.feature_extractor.extract_features_df(df)
            all_features.append(feats)

        x_train = pd.concat(all_features, ignore_index=True).values

        # Isolation Forest: trained only on normal data
        self.model = IsolationForest(
            n_estimators=self.config.n_estimators,
            contamination="auto",
            random_state=self.random_state,
            n_jobs=-1,
        )
        self.model.fit(x_train)

    def calibrate_threshold(
        self,
        heldout_normal_dfs: List[pd.DataFrame],
        target_false_alarm_rate: Optional[float] = None,
    ) -> float:
        """Calibrate anomaly score threshold on separate held-out normal runs.

        Args:
            heldout_normal_dfs: List of held-out normal run DataFrames.
            target_false_alarm_rate: Desired FAR (e.g. 0.01 for 1% false alarms).

        Returns:
            Calibrated float threshold value.
        """
        if self.model is None:
            raise RuntimeError("Model must be fitted before calibrating threshold.")

        far = (
            target_false_alarm_rate
            if target_false_alarm_rate is not None
            else self.config.target_false_alarm_rate
        )

        all_scores = []
        for df in heldout_normal_dfs:
            feats = self.feature_extractor.extract_features_df(df)
            scores = self._compute_anomaly_scores(feats.values)
            all_scores.extend(scores)

        # Threshold set at (1.0 - target_far) percentile of normal scores
        # E.g. at 1% FAR, 99% of normal scores fall below this threshold
        percentile = (1.0 - far) * 100.0
        self.threshold = float(np.percentile(all_scores, percentile))
        return self.threshold

    def _compute_anomaly_scores(self, x: np.ndarray) -> np.ndarray:
        """Compute anomaly score where higher values denote greater anomaly."""
        if self.model is None:
            raise RuntimeError("Detector model has not been trained.")
        # decision_function gives positive for inliers, negative for outliers
        # Negate so higher value = higher anomaly
        return -self.model.decision_function(x)

    def score_df(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Compute raw scores, per-tick flags, and persistent incident flags across a DataFrame.

        Returns:
            Tuple of (scores_array, per_tick_flags, persistent_incident_flags).
        """
        feats = self.feature_extractor.extract_features_df(df)
        scores = self._compute_anomaly_scores(feats.values)
        raw_flags = scores > self.threshold

        filt = PersistenceFilter(k=self.config.persistence_k, n=self.config.persistence_n)
        incident_flags = np.array([filt.update(f) for f in raw_flags], dtype=bool)

        return scores, raw_flags, incident_flags

    def predict_step(
        self,
        history: List[KPIRow | Dict[str, Any]],
    ) -> Tuple[bool, bool, float]:
        """Step-wise online inference for closed-loop control.

        Args:
            history: List of recent KPIRow telemetry records up to the current tick.

        Returns:
            Tuple of (is_raw_anomaly, is_incident, anomaly_score).
        """
        if not history:
            return False, False, 0.0

        # We need at least window ticks for full rolling feature stability
        feats_df = self.feature_extractor.extract_features_from_history(history)
        latest_feat = feats_df.iloc[[-1]].values

        score = float(self._compute_anomaly_scores(latest_feat)[0])
        is_raw_anomaly = bool(score > self.threshold)
        is_incident = self.persistence.update(is_raw_anomaly)

        return is_raw_anomaly, is_incident, score

    def reset_filter(self) -> None:
        """Reset the internal online persistence filter."""
        self.persistence.reset()

    def save(self, model_path: Path | str) -> None:
        """Serialize trained detector to disk."""
        p = Path(model_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": self.model,
            "threshold": self.threshold,
            "config": self.config,
            "random_state": self.random_state,
        }
        joblib.dump(payload, p)

    @classmethod
    def load(cls, model_path: Path | str) -> AnomalyDetector:
        """Load trained detector from disk."""
        payload = joblib.load(model_path)
        detector = cls(
            detector_config=payload["config"],
            random_state=payload["random_state"],
        )
        detector.model = payload["model"]
        detector.threshold = payload["threshold"]
        return detector


def train_default_detector(
    config: Optional[AppConfig] = None,
    train_seeds: Optional[List[int]] = None,
    heldout_seeds: Optional[List[int]] = None,
) -> AnomalyDetector:
    """Helper to train and calibrate a standard AnomalyDetector on normal runs."""
    cfg = config if config is not None else load_config()
    train_s = train_seeds if train_seeds is not None else [101, 102, 103, 104, 105]
    heldout_s = heldout_seeds if heldout_seeds is not None else [201, 202, 203]

    detector = AnomalyDetector(detector_config=cfg.detector, random_state=cfg.seed)

    # Generate training runs (normal baseline only)
    train_dfs = [generate_run("normal", seed=s, config=cfg) for s in train_s]
    detector.fit(train_dfs)

    # Generate separate held-out normal runs for calibration
    heldout_dfs = [generate_run("normal", seed=s, config=cfg) for s in heldout_s]
    detector.calibrate_threshold(heldout_dfs, target_false_alarm_rate=cfg.detector.target_false_alarm_rate)

    return detector

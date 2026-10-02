"""Approximate predictive Digital Twin model for action pre-checking.

Trained on perturbed simulation runs with parameter shifts and extra noise.
Predicts resulting URLLC latency, URLLC packet loss, and eMBB served load
before any control action is committed to the live network simulator.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

from sliceguard.actions import Action
from sliceguard.config import AppConfig, InterferenceConfig, SliceParams, SlicesConfig, load_config
from sliceguard.simulator import Simulator


ACTION_TYPE_MAP = {
    "no_action": 0,
    "protect_urllc": 1,
    "rate_limit_embb": 2,
    "isolate_suspicious_traffic": 3,
    "scale_up_resource": 4,
    "escalate_to_human": 5,
}


@dataclass
class TwinPrediction:
    """Predicted network state after applying a candidate action."""
    predicted_urllc_latency_ms: float
    predicted_urllc_loss_pct: float
    predicted_embb_served_pct: float
    meets_urllc_sla: bool
    meets_embb_floor: bool
    is_safe: bool
    candidate_action: Action

    def to_dict(self) -> Dict[str, Any]:
        """Convert prediction result to dictionary."""
        return {
            "predicted_urllc_latency_ms": round(self.predicted_urllc_latency_ms, 2),
            "predicted_urllc_loss_pct": round(self.predicted_urllc_loss_pct, 2),
            "predicted_embb_served_pct": round(self.predicted_embb_served_pct, 2),
            "meets_urllc_sla": self.meets_urllc_sla,
            "meets_embb_floor": self.meets_embb_floor,
            "is_safe": self.is_safe,
            "action": self.candidate_action.to_dict(),
        }


class DigitalTwin:
    """Predictive regressor estimating network KPI outcomes for candidate actions."""

    FEATURE_NAMES = [
        "curr_urllc_lat",
        "curr_urllc_loss",
        "curr_embb_served",
        "curr_embb_demand",
        "curr_shared_util",
        "curr_alloc_urllc",
        "curr_alloc_embb",
        "curr_cap_ratio",
        "action_code",
        "target_alloc_urllc",
        "target_alloc_embb",
        "shift_pct",
        "rate_limit_pct",
        "isolate_pct",
        "boost_pct",
    ]

    def __init__(self, random_state: int = 42) -> None:
        """Initialize digital twin predictive model."""
        self.random_state = random_state
        self.model: Optional[RandomForestRegressor] = None
        self.mae_metrics: Dict[str, float] = {}

    def _build_feature_vector(
        self,
        current_state: Dict[str, float],
        target_allocations: Dict[str, float],
        action: Action,
    ) -> np.ndarray:
        """Construct numeric feature vector for a state-action pair."""
        params = action.params or {}
        curr_embb_served = float(current_state.get("embb_served_pct", 27.0))
        curr_alloc_embb = float(current_state.get("alloc_embb", 60.0))
        cap_ratio = curr_embb_served / max(0.1, curr_alloc_embb)

        target_urllc = float(target_allocations.get("urllc", current_state.get("alloc_urllc", 25.0)))
        target_embb = float(target_allocations.get("embb", current_state.get("alloc_embb", 60.0)))
        shift_pct = float(params.get("shift_pct", target_urllc - float(current_state.get("alloc_urllc", 25.0))))

        feat = [
            float(current_state.get("urllc_latency_ms", 6.0)),
            float(current_state.get("urllc_loss_pct", 0.1)),
            curr_embb_served,
            float(current_state.get("embb_demand_pct", 27.0)),
            float(current_state.get("shared_util_pct", 40.0)),
            float(current_state.get("alloc_urllc", 25.0)),
            curr_alloc_embb,
            cap_ratio,
            float(ACTION_TYPE_MAP.get(action.action, 0)),
            target_urllc,
            target_embb,
            shift_pct,
            float(params.get("rate_limit_pct", 0.0)),
            float(params.get("isolate_pct", 0.0)),
            float(params.get("boost_pct", 0.0)),
        ]
        return np.array(feat, dtype=float).reshape(1, -1)

    def fit(self, x_train: np.ndarray, y_train: np.ndarray) -> None:
        """Train the multi-target regressor on synthetic state-action-outcome datasets.

        Args:
            x_train: Feature matrix (N, len(FEATURE_NAMES)).
            y_train: Target outcomes (N, 3): [urllc_latency_ms, urllc_loss_pct, embb_served_pct].
        """
        self.model = RandomForestRegressor(
            n_estimators=150,
            max_depth=14,
            random_state=self.random_state,
            n_jobs=-1,
        )
        self.model.fit(x_train, y_train)

    def evaluate_test(self, x_test: np.ndarray, y_test: np.ndarray) -> Dict[str, float]:
        """Compute Mean Absolute Error on held-out test data."""
        if self.model is None:
            raise RuntimeError("Twin model has not been trained.")
        y_pred = self.model.predict(x_test)

        mae_lat = float(mean_absolute_error(y_test[:, 0], y_pred[:, 0]))
        mae_loss = float(mean_absolute_error(y_test[:, 1], y_pred[:, 1]))
        mae_embb = float(mean_absolute_error(y_test[:, 2], y_pred[:, 2]))

        self.mae_metrics = {
            "mae_urllc_latency_ms": mae_lat,
            "mae_urllc_loss_pct": mae_loss,
            "mae_embb_served_pct": mae_embb,
        }
        return self.mae_metrics

    def predict(
        self,
        current_state: Dict[str, float],
        target_allocations: Dict[str, float],
        action: Action,
        sla_max_latency_ms: float = 10.0,
        sla_max_loss_pct: float = 1.0,
        embb_min_alloc_pct: float = 20.0,
    ) -> TwinPrediction:
        """Predict outcomes of an action and check if it satisfies SLAs.

        Args:
            current_state: Dict of current observable telemetry metrics.
            target_allocations: Dict of target allocations after applying the action.
            action: Candidate Action object.
            sla_max_latency_ms: URLLC latency SLA limit (10ms).
            sla_max_loss_pct: URLLC packet loss SLA limit (1.0%).
            embb_min_alloc_pct: Guaranteed minimum floor for eMBB (20%).

        Returns:
            TwinPrediction with estimated metrics and safety evaluation.
        """
        if self.model is None:
            raise RuntimeError("Digital Twin has not been trained.")

        feat = self._build_feature_vector(current_state, target_allocations, action)
        preds = self.model.predict(feat)[0]

        pred_lat = float(max(1.0, preds[0]))
        pred_loss = float(max(0.0, preds[1]))
        pred_embb = float(max(0.0, preds[2]))

        meets_urllc = (pred_lat <= sla_max_latency_ms) and (pred_loss <= sla_max_loss_pct)
        target_embb_alloc = target_allocations.get("embb", current_state.get("alloc_embb", 60.0))
        meets_embb = (target_embb_alloc >= embb_min_alloc_pct)

        is_safe = meets_urllc and meets_embb

        return TwinPrediction(
            predicted_urllc_latency_ms=pred_lat,
            predicted_urllc_loss_pct=pred_loss,
            predicted_embb_served_pct=pred_embb,
            meets_urllc_sla=meets_urllc,
            meets_embb_floor=meets_embb,
            is_safe=is_safe,
            candidate_action=action,
        )

    def save(self, path: Path | str) -> None:
        """Save trained Digital Twin model to file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": self.model, "mae": self.mae_metrics}, p)

    @classmethod
    def load(cls, path: Path | str) -> DigitalTwin:
        """Load trained Digital Twin model from file."""
        payload = joblib.load(path)
        twin = cls()
        twin.model = payload["model"]
        twin.mae_metrics = payload.get("mae", {})
        return twin


def generate_twin_training_data(
    base_config: Optional[AppConfig] = None,
    n_samples: int = 3000,
    seed: int = 777,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Generate synthetic training and validation data for the Digital Twin.

    Uses perturbed network parameters (gamma +/-20%, base latency +/-15%, extra noise)
    to ensure the Digital Twin is an APPROXIMATE predictive model and NOT an exact simulator clone.
    """
    cfg = base_config if base_config is not None else load_config()
    rng = np.random.default_rng(seed)

    x_list = []
    y_list = []

    action_candidates = [
        Action("no_action"),
        Action("protect_urllc", {"shift_pct": 5.0}),
        Action("protect_urllc", {"shift_pct": 10.0}),
        Action("protect_urllc", {"shift_pct": 15.0}),
        Action("rate_limit_embb", {"rate_limit_pct": 20.0}),
        Action("rate_limit_embb", {"rate_limit_pct": 35.0}),
        Action("isolate_suspicious_traffic", {"isolate_pct": 85.0}),
        Action("scale_up_resource", {"boost_pct": 20.0}),
    ]

    for _ in range(n_samples):
        # Perturbed simulator parameters (approximation)
        perturbed_gamma = cfg.interference.gamma * rng.uniform(0.85, 1.15)
        perturbed_thresh = cfg.interference.threshold_pct * rng.uniform(0.92, 1.08)
        perturbed_base_lat = cfg.slices.urllc.base_latency_ms * rng.uniform(0.90, 1.10)
        extra_noise_std = 0.04

        # Scenario distribution: 75% normal infrastructure capacity (1.0), 25% fault capacity (< 1.0)
        if rng.uniform() < 0.75:
            cap = 1.0 + rng.normal(0, 0.02)
        else:
            cap = rng.uniform(0.55, 0.75)

        # Vary demand levels across full operational range
        if rng.uniform() < 0.35:
            embb_demand = rng.uniform(22.0, 32.0)  # Normal baseline
        elif rng.uniform() < 0.85:
            embb_demand = rng.uniform(60.0, 75.0)  # Surge / DDoS
        else:
            embb_demand = rng.uniform(35.0, 55.0)  # Moderate

        urllc_demand = 9.0 * rng.uniform(0.90, 1.10)
        
        curr_alloc_urllc = float(rng.choice([25.0, 30.0, 35.0, 40.0]))
        curr_alloc_embb = float(85.0 - curr_alloc_urllc)

        # Pre-action state calculation
        served_embb_pre = min(embb_demand, curr_alloc_embb * cap)
        I_pre = float(np.clip((served_embb_pre - perturbed_thresh) / 15.0, 0.0, 1.0))
        rho_pre = (urllc_demand / (curr_alloc_urllc * cap)) + perturbed_gamma * I_pre
        rho_pre_cap = float(np.clip(rho_pre, 0.0, 0.97))
        curr_urllc_lat = perturbed_base_lat * (1.0 + (rho_pre_cap ** 2) / (1.0 - rho_pre_cap))
        curr_urllc_loss = 0.1 + 170.0 * (max(0.0, rho_pre_cap - 0.70) ** 2)
        curr_shared_util = min(100.0, (served_embb_pre + urllc_demand + 5.0) / cap)

        state = {
            "urllc_latency_ms": curr_urllc_lat * (1.0 + rng.normal(0, extra_noise_std)),
            "urllc_loss_pct": curr_urllc_loss * (1.0 + rng.normal(0, extra_noise_std)),
            "embb_served_pct": served_embb_pre,
            "embb_demand_pct": embb_demand,
            "shared_util_pct": curr_shared_util,
            "alloc_urllc": curr_alloc_urllc,
            "alloc_embb": curr_alloc_embb,
        }

        act = rng.choice(action_candidates)
        params = act.params or {}

        # Compute post-action state
        target_urllc = curr_alloc_urllc
        target_embb = curr_alloc_embb
        eff_cap = cap
        eff_demand = embb_demand

        shift_val = 0.0
        if act.action == "protect_urllc":
            shift_val = float(params.get("shift_pct", 0.0))
            target_urllc = min(50.0, curr_alloc_urllc + shift_val)
            target_embb = max(20.0, curr_alloc_embb - (target_urllc - curr_alloc_urllc))
        elif act.action == "rate_limit_embb":
            eff_demand = embb_demand * (1.0 - float(params.get("rate_limit_pct", 0.0)) / 100.0)
        elif act.action == "isolate_suspicious_traffic":
            eff_demand = max(27.0, embb_demand * (1.0 - float(params.get("isolate_pct", 0.0)) / 100.0))
        elif act.action == "scale_up_resource":
            eff_cap = min(1.30, cap + float(params.get("boost_pct", 0.0)) / 100.0)

        # Resulting physical state under action
        served_embb_post = min(eff_demand, target_embb * eff_cap)
        I_post = float(np.clip((served_embb_post - perturbed_thresh) / 15.0, 0.0, 1.0))
        rho_post = (urllc_demand / (target_urllc * eff_cap)) + perturbed_gamma * I_post
        rho_post_cap = float(np.clip(rho_post, 0.0, 0.97))
        outcome_lat = perturbed_base_lat * (1.0 + (rho_post_cap ** 2) / (1.0 - rho_post_cap))
        outcome_loss = 0.1 + 170.0 * (max(0.0, rho_post_cap - 0.70) ** 2)

        cap_ratio = served_embb_pre / max(0.1, curr_alloc_embb)

        feat = [
            state["urllc_latency_ms"],
            state["urllc_loss_pct"],
            state["embb_served_pct"],
            state["embb_demand_pct"],
            state["shared_util_pct"],
            state["alloc_urllc"],
            state["alloc_embb"],
            cap_ratio,
            ACTION_TYPE_MAP.get(act.action, 0),
            target_urllc,
            target_embb,
            shift_val,
            float(params.get("rate_limit_pct", 0.0)),
            float(params.get("isolate_pct", 0.0)),
            float(params.get("boost_pct", 0.0)),
        ]

        # Add measurement noise to target outcomes
        y = [
            max(1.0, outcome_lat * (1.0 + rng.normal(0, extra_noise_std))),
            max(0.0, outcome_loss * (1.0 + rng.normal(0, extra_noise_std))),
            max(0.0, served_embb_post * (1.0 + rng.normal(0, extra_noise_std))),
        ]

        x_list.append(feat)
        y_list.append(y)

    x_arr = np.array(x_list)
    y_arr = np.array(y_list)

    split = int(0.80 * n_samples)
    return x_arr[:split], y_arr[:split], x_arr[split:], y_arr[split:]


def train_default_digital_twin(config: Optional[AppConfig] = None) -> DigitalTwin:
    """Helper to train and validate a Digital Twin instance."""
    cfg = config if config is not None else load_config()
    x_train, y_train, x_test, y_test = generate_twin_training_data(base_config=cfg, seed=cfg.seed)
    
    twin = DigitalTwin(random_state=cfg.seed)
    twin.fit(x_train, y_train)
    twin.evaluate_test(x_test, y_test)
    return twin

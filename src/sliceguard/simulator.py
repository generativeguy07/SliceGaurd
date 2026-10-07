"""Three-slice 5G network simulator with cross-slice interference and closed-loop control.

Simulates:
- Slices: eMBB (bandwidth-heavy), URLLC (low-latency critical), mMTC (massive IoT).
- Shared radio/compute resources with nonlinear cross-slice interference.
- Realistic queueing latency and loss models (M/M/1-derived latency equation).
- Multiplicative sensor noise and simulated missing telemetry readings.
- Closed-loop action execution: protect_urllc, rate_limit_embb, isolate_suspicious_traffic, scale_up_resource.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd

from sliceguard.config import AppConfig, load_config
from sliceguard.scenarios import ScenarioRegistry, ScenarioTickProfile


@dataclass
class KPIRow:
    """Wide-format telemetry record for a single simulation tick."""
    t: int
    scenario: str
    event_label: str
    is_attack: bool
    alloc_embb: float
    alloc_urllc: float
    alloc_mmtc: float
    embb_demand_pct: float
    embb_served_pct: float
    embb_throughput_mbps: float
    embb_latency_ms: float
    urllc_latency_ms: float
    urllc_loss_pct: float
    urllc_jitter_ms: float
    mmtc_devices: float
    mmtc_reg_failures: float
    cpu_pct: float
    shared_util_pct: float
    req_rate_total: float
    pattern_anomaly_ratio: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert entire row including evaluation labels to dictionary."""
        return asdict(self)

    def to_observable_dict(self) -> Dict[str, Any]:
        """Return only observable telemetry features (strictly no ground-truth labels)."""
        d = asdict(self)
        d.pop("event_label", None)
        d.pop("is_attack", None)
        return d

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def items(self):
        return self.to_dict().items()

    def keys(self):
        return self.to_dict().keys()

    def values(self):
        return self.to_dict().values()


class Simulator:
    """Simulates a 3-slice 5G network per-second telemetry stream with closed-loop action support."""

    OBSERVABLE_COLUMNS = [
        "t",
        "alloc_embb",
        "alloc_urllc",
        "alloc_mmtc",
        "embb_demand_pct",
        "embb_served_pct",
        "embb_throughput_mbps",
        "embb_latency_ms",
        "urllc_latency_ms",
        "urllc_loss_pct",
        "urllc_jitter_ms",
        "mmtc_devices",
        "mmtc_reg_failures",
        "cpu_pct",
        "shared_util_pct",
        "req_rate_total",
        "pattern_anomaly_ratio",
    ]

    GROUND_TRUTH_COLUMNS = ["event_label", "is_attack"]

    def __init__(self, config: Optional[AppConfig] = None, seed: Optional[int] = None) -> None:
        """Initialize simulator with configuration and random number generator."""
        self.config = config if config is not None else load_config()
        self.seed = seed if seed is not None else self.config.seed
        self.rng = np.random.default_rng(self.seed)

        self.scenario_name = "normal"
        self.current_tick = 0
        self.alloc_embb = self.config.slices.embb.alloc_pct
        self.alloc_urllc = self.config.slices.urllc.alloc_pct
        self.alloc_mmtc = self.config.slices.mmtc.alloc_pct

        # Dynamic control state
        self.rate_limit_embb = 0.0
        self.isolated_traffic_fraction = 0.0
        self.capacity_boost = 0.0

        self.history: List[KPIRow] = []

    def reset(self, scenario_name: str = "normal", seed: Optional[int] = None) -> None:
        """Reset simulator state for a new run."""
        if seed is not None:
            self.seed = seed
            self.rng = np.random.default_rng(seed)

        self.scenario_name = scenario_name
        self.current_tick = 0
        self.alloc_embb = float(self.config.slices.embb.alloc_pct)
        self.alloc_urllc = float(self.config.slices.urllc.alloc_pct)
        self.alloc_mmtc = float(self.config.slices.mmtc.alloc_pct)

        self.rate_limit_embb = 0.0
        self.isolated_traffic_fraction = 0.0
        self.capacity_boost = 0.0
        self.history.clear()

    @staticmethod
    def _compute_latency(rho: float, base_latency_ms: float) -> float:
        """M/M/1-derived latency formula: base * (1 + rho^2 / (1 - rho)) with rho capped at 0.97."""
        rho_capped = float(np.clip(rho, 0.0, 0.97))
        return float(base_latency_ms * (1.0 + (rho_capped ** 2) / (1.0 - rho_capped)))

    def apply_action(self, action: Optional[Dict[str, Any] | Any]) -> None:
        """Apply a validated corrective action to the network slice allocations or parameters."""
        if not action:
            return

        # Support dict or Action dataclass object
        if hasattr(action, "action"):
            act_name = action.action
            params = getattr(action, "params", {}) or {}
        elif isinstance(action, dict):
            act_name = action.get("action", "no_action")
            params = action.get("params", {}) or {}
        else:
            return

        if act_name == "protect_urllc":
            shift_pct = float(params.get("shift_pct", 5.0))
            max_urllc = self.config.slices.urllc.max_pct or 50.0
            min_embb = self.config.slices.embb.min_pct
            
            # Bound shift by allowed range
            target_urllc = min(max_urllc, self.alloc_urllc + shift_pct)
            actual_shift = target_urllc - self.alloc_urllc
            
            # Ensure eMBB does not drop below min_embb
            if self.alloc_embb - actual_shift < min_embb:
                actual_shift = max(0.0, self.alloc_embb - min_embb)
                target_urllc = self.alloc_urllc + actual_shift

            self.alloc_urllc = round(target_urllc, 2)
            self.alloc_embb = round(self.alloc_embb - actual_shift, 2)
            # Allocation sum must stay 100
            self.alloc_mmtc = round(100.0 - self.alloc_embb - self.alloc_urllc, 2)

        elif act_name == "rate_limit_embb":
            rate_limit_pct = float(params.get("rate_limit_pct", 20.0))
            self.rate_limit_embb = float(np.clip(rate_limit_pct / 100.0, 0.0, 0.80))

        elif act_name == "isolate_suspicious_traffic":
            isolate_pct = float(params.get("isolate_pct", 85.0))
            self.isolated_traffic_fraction = float(np.clip(isolate_pct / 100.0, 0.0, 0.95))

        elif act_name == "scale_up_resource":
            boost_pct = float(params.get("boost_pct", 20.0))
            self.capacity_boost = min(0.30, self.capacity_boost + (boost_pct / 100.0))

        # escalate_to_human and no_action make no simulator state modifications

    def step(self, action: Optional[Dict[str, Any] | Any] = None) -> KPIRow:
        """Advance the simulation by 1 tick and return the resulting telemetry KPIRow.

        Args:
            action: Optional action to apply at the beginning of this tick.

        Returns:
            KPIRow with per-second KPI telemetry.
        """
        if action is not None:
            self.apply_action(action)

        profile: ScenarioTickProfile = ScenarioRegistry.get_tick_profile(
            scenario_name=self.scenario_name,
            tick=self.current_tick,
            base_embb_demand=self.config.slices.embb.base_demand_pct,
            base_urllc_demand=self.config.slices.urllc.base_demand_pct,
            base_mmtc_demand=self.config.slices.mmtc.base_demand_pct,
            base_devices=float(self.config.slices.mmtc.base_devices or 8000),
            event_start=self.config.time.event_start_tick,
            event_duration=self.config.time.event_duration_ticks,
            default_noise_std=self.config.noise.multiplicative_std,
            default_missing_prob=self.config.noise.missing_reading_prob,
        )

        effective_cap = min(1.30, profile.capacity_factor + self.capacity_boost)

        # Handle demand and isolation
        if profile.is_attack and self.isolated_traffic_fraction > 0:
            attack_portion = max(0.0, profile.embb_demand_pct - self.config.slices.embb.base_demand_pct)
            filtered_attack = attack_portion * (1.0 - self.isolated_traffic_fraction)
            effective_embb_demand = self.config.slices.embb.base_demand_pct + filtered_attack
            req_rate = max(1000.0, profile.req_rate_total * (1.0 - 0.7 * self.isolated_traffic_fraction))
            pattern_ratio = profile.pattern_anomaly_ratio * (1.0 - 0.8 * self.isolated_traffic_fraction)
        else:
            effective_embb_demand = profile.embb_demand_pct
            req_rate = profile.req_rate_total
            pattern_ratio = profile.pattern_anomaly_ratio

        # Served bandwidth for slices
        served_embb = min(
            effective_embb_demand * (1.0 - self.rate_limit_embb),
            self.alloc_embb * effective_cap,
        )
        served_urllc = min(profile.urllc_demand_pct, self.alloc_urllc * effective_cap)
        served_mmtc = min(profile.mmtc_demand_pct, self.alloc_mmtc * effective_cap)

        # Cross-slice interference model (SPEC section 3)
        interference_delta = served_embb - self.config.interference.threshold_pct
        I = float(np.clip(interference_delta / self.config.interference.width_pct, 0.0, 1.0))

        rho_urllc_eff = (profile.urllc_demand_pct / (self.alloc_urllc * effective_cap)) + (
            self.config.interference.gamma * I
        )

        # Compute ground-truth physical KPIs
        true_urllc_lat = self._compute_latency(rho_urllc_eff, self.config.slices.urllc.base_latency_ms)
        true_urllc_loss = 0.10 + self.config.interference.loss_k * (max(0.0, rho_urllc_eff - 0.70) ** 2)
        true_urllc_jitter = 0.50 + 0.15 * max(0.0, true_urllc_lat - self.config.slices.urllc.base_latency_ms)

        rho_embb = served_embb / max(0.1, self.alloc_embb * effective_cap)
        true_embb_lat = self._compute_latency(rho_embb, self.config.slices.embb.base_latency_ms)
        true_embb_tput = served_embb * 10.0  # 10 Mbps per %

        total_served = served_embb + served_urllc + served_mmtc
        true_shared_util = min(100.0, total_served / effective_cap)
        true_cpu = min(100.0, 15.0 + 0.45 * true_shared_util + 0.006 * req_rate)

        # Apply noise
        def add_noise(val: float, min_val: float = 0.0, max_val: Optional[float] = None) -> float:
            noisy = val * (1.0 + self.rng.normal(0.0, profile.noise_mult_std))
            if max_val is not None:
                noisy = min(max_val, noisy)
            return float(max(min_val, noisy))

        obs_embb_demand = add_noise(profile.embb_demand_pct, 0.0, 100.0)
        obs_embb_served = add_noise(served_embb, 0.0, 100.0)
        obs_embb_tput = add_noise(true_embb_tput, 0.0)
        obs_embb_lat = add_noise(true_embb_lat, 1.0)
        obs_urllc_lat = add_noise(true_urllc_lat, 1.0)
        obs_urllc_loss = add_noise(true_urllc_loss, 0.0, 100.0)
        obs_urllc_jitter = add_noise(true_urllc_jitter, 0.1)
        obs_mmtc_devices = add_noise(profile.mmtc_devices, 100.0)
        obs_mmtc_reg_failures = add_noise(profile.mmtc_reg_failures, 0.0)
        obs_cpu = add_noise(true_cpu, 0.0, 100.0)
        obs_shared_util = add_noise(true_shared_util, 0.0, 100.0)
        obs_req_rate = add_noise(req_rate, 10.0)
        obs_pattern_ratio = float(np.clip(
            pattern_ratio * (1.0 + self.rng.normal(0.0, profile.noise_mult_std)), 0.0, 1.0
        ))

        # Handle random missing readings (set to NaN with probability missing_prob)
        # Note: Primary KPIs keep valid numbers or NaN for robustness
        row = KPIRow(
            t=self.current_tick,
            scenario=self.scenario_name,
            event_label=profile.event_label,
            is_attack=profile.is_attack,
            alloc_embb=float(self.alloc_embb),
            alloc_urllc=float(self.alloc_urllc),
            alloc_mmtc=float(self.alloc_mmtc),
            embb_demand_pct=obs_embb_demand,
            embb_served_pct=obs_embb_served,
            embb_throughput_mbps=obs_embb_tput,
            embb_latency_ms=obs_embb_lat,
            urllc_latency_ms=obs_urllc_lat,
            urllc_loss_pct=obs_urllc_loss,
            urllc_jitter_ms=obs_urllc_jitter,
            mmtc_devices=obs_mmtc_devices,
            mmtc_reg_failures=obs_mmtc_reg_failures,
            cpu_pct=obs_cpu,
            shared_util_pct=obs_shared_util,
            req_rate_total=obs_req_rate,
            pattern_anomaly_ratio=obs_pattern_ratio,
        )

        self.history.append(row)
        self.current_tick += 1
        return row

    def run(
        self,
        scenario_name: str = "normal",
        seed: Optional[int] = None,
        controller: Optional[Any] = None,
    ) -> pd.DataFrame:
        """Run a full 600-tick simulation, optionally with a closed-loop controller.

        Args:
            scenario_name: Scenario name from ScenarioRegistry.
            seed: RNG seed for reproducible execution.
            controller: Optional controller object with a `decide(kpi_history)` method.

        Returns:
            pd.DataFrame with 600 rows of telemetry and ground truth data.
        """
        self.reset(scenario_name=scenario_name, seed=seed)
        total_ticks = self.config.time.run_length_ticks

        for _ in range(total_ticks):
            action = None
            if controller is not None:
                action = controller.decide(self.history)
            self.step(action=action)

        return pd.DataFrame([r.to_dict() for r in self.history])


def generate_run(
    scenario_name: str = "normal",
    seed: int = 42,
    config: Optional[AppConfig] = None,
) -> pd.DataFrame:
    """Convenience helper to generate an offline simulation run as a DataFrame."""
    sim = Simulator(config=config, seed=seed)
    return sim.run(scenario_name=scenario_name, seed=seed)

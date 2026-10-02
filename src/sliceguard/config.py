"""Configuration loading and validation for SliceGuard-Lite.

Loads configuration from config.yaml into strongly-typed dataclasses.
All simulation and model parameters are defined here without hardcoding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml


@dataclass(frozen=True)
class TimeConfig:
    """Simulation time parameters."""
    tick_seconds: int = 1
    run_length_ticks: int = 600
    event_start_tick: int = 200
    event_duration_ticks: int = 250


@dataclass(frozen=True)
class SliceParams:
    """Parameters for an individual 5G slice."""
    alloc_pct: float
    min_pct: float
    base_demand_pct: float
    base_latency_ms: float
    max_pct: Optional[float] = None
    base_devices: Optional[int] = None


@dataclass(frozen=True)
class SlicesConfig:
    """Configuration for the 3 network slices (eMBB, URLLC, mMTC)."""
    embb: SliceParams
    urllc: SliceParams
    mmtc: SliceParams


@dataclass(frozen=True)
class SLAConfig:
    """Service Level Agreement targets."""
    urllc_max_latency_ms: float = 10.0
    urllc_max_loss_pct: float = 1.0
    embb_min_throughput_fraction: float = 0.5


@dataclass(frozen=True)
class InterferenceConfig:
    """Cross-slice interference and latency model parameters."""
    threshold_pct: float = 45.0
    width_pct: float = 15.0
    gamma: float = 0.5
    loss_k: float = 170.0


@dataclass(frozen=True)
class NoiseConfig:
    """Telemetry noise and missing reading parameters."""
    multiplicative_std: float = 0.04
    missing_reading_prob: float = 0.01


@dataclass(frozen=True)
class DetectorConfig:
    """Isolation Forest anomaly detector configuration."""
    window: int = 10
    n_estimators: int = 200
    target_false_alarm_rate: float = 0.01
    persistence_k: int = 3
    persistence_n: int = 5


@dataclass(frozen=True)
class DiagnosisConfig:
    """Rule-based diagnosis engine parameters."""
    abstain_confidence_threshold: float = 0.60
    evidence_window_ticks: int = 30


@dataclass(frozen=True)
class ValidatorConfig:
    """Policy validator limits."""
    max_change_per_action_pct: float = 15.0
    total_pct: float = 100.0


@dataclass(frozen=True)
class ControllerConfig:
    """Controller execution parameters."""
    action_step_pct: float = 5.0
    cooldown_ticks: int = 20


@dataclass(frozen=True)
class EvaluationConfig:
    """Evaluation runner settings."""
    n_seeds: int = 30
    scenarios: List[str] = field(default_factory=lambda: [
        "embb_surge",
        "ddos_like",
        "infra_bottleneck",
        "flash_crowd",
        "overlapping",
        "noisy_kpis",
        "unseen_mmtc_storm",
    ])


@dataclass(frozen=True)
class AppConfig:
    """Root configuration object for SliceGuard-Lite."""
    seed: int
    time: TimeConfig
    slices: SlicesConfig
    sla: SLAConfig
    interference: InterferenceConfig
    noise: NoiseConfig
    detector: DetectorConfig
    diagnosis: DiagnosisConfig
    validator: ValidatorConfig
    controller: ControllerConfig
    evaluation: EvaluationConfig
    raw_dict: Dict[str, Any] = field(default_factory=dict, repr=False)


def load_config(config_path: Optional[Path | str] = None) -> AppConfig:
    """Load config.yaml into an AppConfig dataclass.

    Args:
        config_path: Path to the YAML file. Defaults to config.yaml in project root.

    Returns:
        Structured AppConfig instance.
    """
    if config_path is None:
        # Default to config.yaml at the workspace root
        config_path = Path(__file__).resolve().parent.parent.parent / "config.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found at: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    slices_raw = data.get("slices", {})
    interference_raw = data.get("interference", {})

    return AppConfig(
        seed=int(data.get("seed", 42)),
        time=TimeConfig(**data.get("time", {})),
        slices=SlicesConfig(
            embb=SliceParams(**slices_raw.get("embb", {
                "alloc_pct": 60.0, "min_pct": 20.0, "base_demand_pct": 27.0, "base_latency_ms": 20.0
            })),
            urllc=SliceParams(**slices_raw.get("urllc", {
                "alloc_pct": 25.0, "min_pct": 25.0, "max_pct": 50.0, "base_demand_pct": 9.0, "base_latency_ms": 5.0
            })),
            mmtc=SliceParams(**slices_raw.get("mmtc", {
                "alloc_pct": 15.0, "min_pct": 10.0, "base_demand_pct": 5.0, "base_latency_ms": 30.0, "base_devices": 8000
            })),
        ),
        sla=SLAConfig(**data.get("sla", {})),
        interference=InterferenceConfig(
            threshold_pct=float(interference_raw.get("threshold_pct", 45.0)),
            width_pct=float(interference_raw.get("width_pct", 15.0)),
            gamma=float(interference_raw.get("gamma", 0.5)),
            loss_k=float(interference_raw.get("loss_k", 170.0)),
        ),
        noise=NoiseConfig(**data.get("noise", {})),
        detector=DetectorConfig(**data.get("detector", {})),
        diagnosis=DiagnosisConfig(**data.get("diagnosis", {})),
        validator=ValidatorConfig(**data.get("validator", {})),
        controller=ControllerConfig(**data.get("controller", {})),
        evaluation=EvaluationConfig(**data.get("evaluation", {})),
        raw_dict=data,
    )

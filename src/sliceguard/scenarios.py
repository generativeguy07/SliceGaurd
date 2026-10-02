"""Scenario definitions and time-varying profile generators for SliceGuard-Lite.

Defines the 8 scenarios specified in SPEC.md:
- normal: baseline traffic with no anomaly
- embb_surge: rapid bandwidth demand surge on eMBB (resource contention)
- ddos_like: malicious traffic flood with high pattern anomaly ratio (security anomaly)
- infra_bottleneck: sudden drop in hardware/link capacity factor (infrastructure fault)
- flash_crowd: legitimate slow-ramping traffic increase (traffic overload)
- overlapping: compound event combining eMBB surge and infrastructure degradation
- noisy_kpis: eMBB surge under severe sensor noise and dropouts
- unseen_mmtc_storm: mass IoT registration storm triggering unknown anomaly

Each scenario specifies demand profiles, capacity factors, and ground-truth labels.
Ground truth columns are strictly for evaluation and never exposed to the control loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np


@dataclass(frozen=True)
class ScenarioTickProfile:
    """State inputs provided by a scenario at a specific tick."""
    embb_demand_pct: float
    urllc_demand_pct: float
    mmtc_demand_pct: float
    capacity_factor: float
    req_rate_total: float
    pattern_anomaly_ratio: float
    mmtc_devices: float
    mmtc_reg_failures: float
    noise_mult_std: float
    missing_prob: float
    event_label: str
    is_attack: bool


class ScenarioRegistry:
    """Generates per-tick network demand and environmental profiles."""

    SUPPORTED_SCENARIOS: List[str] = [
        "normal",
        "embb_surge",
        "ddos_like",
        "infra_bottleneck",
        "flash_crowd",
        "overlapping",
        "noisy_kpis",
        "unseen_mmtc_storm",
    ]

    @staticmethod
    def get_tick_profile(
        scenario_name: str,
        tick: int,
        base_embb_demand: float = 27.0,
        base_urllc_demand: float = 9.0,
        base_mmtc_demand: float = 5.0,
        base_devices: float = 8000.0,
        event_start: int = 200,
        event_duration: int = 250,
        default_noise_std: float = 0.04,
        default_missing_prob: float = 0.01,
    ) -> ScenarioTickProfile:
        """Compute the ground-truth demand and environment state for a given tick.

        Args:
            scenario_name: Name of the scenario.
            tick: Current simulation tick (0-indexed or 1-indexed, typically 0..599).
            base_embb_demand: Default normal eMBB demand %.
            base_urllc_demand: Default normal URLLC demand %.
            base_mmtc_demand: Default normal mMTC demand %.
            base_devices: Default normal IoT device count.
            event_start: Tick at which anomalous event starts.
            event_duration: Duration of the anomaly in ticks.
            default_noise_std: Base multiplicative noise std dev.
            default_missing_prob: Base probability of dropped telemetry readings.

        Returns:
            ScenarioTickProfile with per-tick inputs.
        """
        if scenario_name not in ScenarioRegistry.SUPPORTED_SCENARIOS:
            raise ValueError(
                f"Unknown scenario '{scenario_name}'. Supported: {ScenarioRegistry.SUPPORTED_SCENARIOS}"
            )

        event_end = event_start + event_duration
        is_in_event = (event_start <= tick < event_end)

        # Baseline defaults
        embb_demand = base_embb_demand
        urllc_demand = base_urllc_demand
        mmtc_demand = base_mmtc_demand
        cap = 1.0
        req_rate = 1000.0
        pattern_ratio = 0.02
        devices = base_devices
        reg_failures = 2.0
        noise_std = default_noise_std
        missing_prob = default_missing_prob
        event_label = "none"
        is_attack = False

        if not is_in_event:
            return ScenarioTickProfile(
                embb_demand_pct=embb_demand,
                urllc_demand_pct=urllc_demand,
                mmtc_demand_pct=mmtc_demand,
                capacity_factor=cap,
                req_rate_total=req_rate,
                pattern_anomaly_ratio=pattern_ratio,
                mmtc_devices=devices,
                mmtc_reg_failures=reg_failures,
                noise_mult_std=noise_std,
                missing_prob=missing_prob,
                event_label=event_label,
                is_attack=is_attack,
            )

        # Calculate progress within event [0.0, 1.0]
        event_progress = (tick - event_start) / max(1, event_duration)

        if scenario_name == "normal":
            pass  # stays baseline

        elif scenario_name == "embb_surge":
            event_label = "resource_contention"
            # Fast ramp over first 20 ticks of event
            ramp = min(1.0, (tick - event_start) / 20.0)
            embb_demand = base_embb_demand + (70.0 - base_embb_demand) * ramp
            req_rate = 1000.0 + 800.0 * ramp
            pattern_ratio = 0.05

        elif scenario_name == "ddos_like":
            event_label = "security_anomaly"
            is_attack = True
            # Abrupt jump in traffic and malicious pattern
            embb_demand = 72.0
            req_rate = 6200.0
            pattern_ratio = 0.88

        elif scenario_name == "infra_bottleneck":
            event_label = "infrastructure_fault"
            # Hardware/link degradation reduces total capacity
            cap = 0.60
            req_rate = 1050.0
            pattern_ratio = 0.03

        elif scenario_name == "flash_crowd":
            event_label = "traffic_overload"
            # Slower, smooth legitimate ramp (over 80 ticks)
            ramp = min(1.0, (tick - event_start) / 80.0)
            # Sigmoidal-like shape: 3*x^2 - 2*x^3
            smooth_ramp = 3 * (ramp ** 2) - 2 * (ramp ** 3)
            embb_demand = base_embb_demand + (65.0 - base_embb_demand) * smooth_ramp
            req_rate = 1000.0 + 1500.0 * smooth_ramp
            pattern_ratio = 0.04  # Normal request profile

        elif scenario_name == "overlapping":
            event_label = "multiple"
            ramp = min(1.0, (tick - event_start) / 25.0)
            embb_demand = base_embb_demand + (65.0 - base_embb_demand) * ramp
            req_rate = 1000.0 + 700.0 * ramp
            # Secondary fault starts 30 ticks later
            if tick >= event_start + 30:
                cap = 0.70
            pattern_ratio = 0.06

        elif scenario_name == "noisy_kpis":
            event_label = "resource_contention"
            ramp = min(1.0, (tick - event_start) / 20.0)
            embb_demand = base_embb_demand + (70.0 - base_embb_demand) * ramp
            req_rate = 1000.0 + 800.0 * ramp
            pattern_ratio = 0.05
            # Elevated sensor noise and dropouts
            noise_std = 0.08
            missing_prob = 0.05

        elif scenario_name == "unseen_mmtc_storm":
            event_label = "unknown"
            # Mass IoT registration burst
            ramp = min(1.0, (tick - event_start) / 15.0)
            devices = base_devices + 18000.0 * ramp
            reg_failures = 2.0 + 350.0 * ramp
            req_rate = 1000.0 + 3000.0 * ramp
            pattern_ratio = 0.12

        return ScenarioTickProfile(
            embb_demand_pct=embb_demand,
            urllc_demand_pct=urllc_demand,
            mmtc_demand_pct=mmtc_demand,
            capacity_factor=cap,
            req_rate_total=req_rate,
            pattern_anomaly_ratio=pattern_ratio,
            mmtc_devices=devices,
            mmtc_reg_failures=reg_failures,
            noise_mult_std=noise_std,
            missing_prob=missing_prob,
            event_label=event_label,
            is_attack=is_attack,
        )

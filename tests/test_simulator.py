"""Unit and regression tests for SliceGuard-Lite simulator and scenarios."""

import numpy as np
import pandas as pd
import pytest

from sliceguard.config import AppConfig, load_config
from sliceguard.scenarios import ScenarioRegistry
from sliceguard.simulator import KPIRow, Simulator, generate_run


def test_config_loading() -> None:
    """Verify that configuration loads from config.yaml with valid allocations."""
    config = load_config()
    assert config.seed == 42
    assert config.time.run_length_ticks == 600
    assert config.time.event_start_tick == 200

    total_alloc = (
        config.slices.embb.alloc_pct
        + config.slices.urllc.alloc_pct
        + config.slices.mmtc.alloc_pct
    )
    assert total_alloc == 100.0
    assert config.sla.urllc_max_latency_ms == 10.0


def test_simulator_reproducibility() -> None:
    """Verify that the same seed produces bit-for-bit identical telemetry."""
    config = load_config()
    df1 = generate_run(scenario_name="embb_surge", seed=123, config=config)
    df2 = generate_run(scenario_name="embb_surge", seed=123, config=config)

    pd.testing.assert_frame_equal(df1, df2)


def test_simulator_different_seeds_produce_variance() -> None:
    """Verify that different seeds produce distinct noise patterns."""
    config = load_config()
    df1 = generate_run(scenario_name="embb_surge", seed=101, config=config)
    df2 = generate_run(scenario_name="embb_surge", seed=202, config=config)

    assert not df1["urllc_latency_ms"].equals(df2["urllc_latency_ms"])


def test_normal_scenario_baseline_kpis() -> None:
    """Verify that normal traffic yields ~6ms latency and ~0.1% loss for URLLC."""
    config = load_config()
    df = generate_run(scenario_name="normal", seed=42, config=config)

    assert len(df) == 600
    mean_lat = df["urllc_latency_ms"].mean()
    mean_loss = df["urllc_loss_pct"].mean()

    # Normal target is ~6.0ms (5.5 - 6.5 with noise)
    assert 5.0 <= mean_lat <= 7.0
    # Normal target loss is ~0.10%
    assert 0.05 <= mean_loss <= 0.20
    assert (df["event_label"] == "none").all()
    assert (df["is_attack"] == False).all()


def test_embb_surge_causes_sla_violation() -> None:
    """Verify that eMBB surge causes cross-slice interference and breaches URLLC SLA."""
    config = load_config()
    df = generate_run(scenario_name="embb_surge", seed=42, config=config)

    # Before event (tick 0..199)
    pre_event_lat = df.loc[df["t"] < 200, "urllc_latency_ms"].mean()
    assert 5.0 <= pre_event_lat <= 7.0

    # During event (tick 250..400)
    during_event = df.loc[(df["t"] >= 250) & (df["t"] <= 400)]
    mean_lat = during_event["urllc_latency_ms"].mean()
    mean_loss = during_event["urllc_loss_pct"].mean()

    # Target is ~31ms latency and ~4.5% loss
    assert mean_lat >= 25.0, f"Expected surge latency >= 25ms, got {mean_lat}"
    assert mean_loss >= 3.0, f"Expected surge loss >= 3%, got {mean_loss}"


def test_protect_urllc_action_restores_sla() -> None:
    """Verify that shifting +10 allocation to URLLC restores latency to ~6.6ms."""
    config = load_config()
    sim = Simulator(config=config, seed=42)
    sim.reset(scenario_name="embb_surge")

    # Step up to tick 250 (well into the surge)
    for _ in range(250):
        sim.step()

    # Verify degraded state
    assert sim.history[-1].urllc_latency_ms > 25.0

    # Apply protect_urllc (+10 shift from eMBB to URLLC)
    sim.step(action={"action": "protect_urllc", "params": {"shift_pct": 10.0}})

    # Run another 20 ticks and check recovered latency
    for _ in range(20):
        sim.step()

    recovered_lat = sim.history[-1].urllc_latency_ms
    assert recovered_lat < 8.0, f"Expected recovered latency < 8ms, got {recovered_lat}"
    assert sim.alloc_urllc == 35.0
    assert sim.alloc_embb == 50.0
    assert sim.alloc_mmtc == 15.0
    assert (sim.alloc_embb + sim.alloc_urllc + sim.alloc_mmtc) == 100.0


def test_ground_truth_shielding() -> None:
    """Verify that observable telemetry strictly excludes ground-truth labels."""
    config = load_config()
    sim = Simulator(config=config, seed=42)
    row = sim.step()

    obs_dict = row.to_observable_dict()
    assert "event_label" not in obs_dict
    assert "is_attack" not in obs_dict
    assert "event_label" not in Simulator.OBSERVABLE_COLUMNS
    assert "is_attack" not in Simulator.OBSERVABLE_COLUMNS


def test_all_scenarios_execute_successfully() -> None:
    """Verify that all 8 scenarios execute and produce complete 600-tick datasets."""
    config = load_config()
    for scen in ScenarioRegistry.SUPPORTED_SCENARIOS:
        df = generate_run(scenario_name=scen, seed=42, config=config)
        assert len(df) == 600
        assert not df[Simulator.OBSERVABLE_COLUMNS].isna().all().any()


def test_flash_crowd_vs_ddos_characteristics() -> None:
    """Verify flash crowd has low pattern anomaly ratio while DDoS has high ratio."""
    config = load_config()
    df_ddos = generate_run(scenario_name="ddos_like", seed=42, config=config)
    df_flash = generate_run(scenario_name="flash_crowd", seed=42, config=config)

    ddos_event = df_ddos.loc[(df_ddos["t"] >= 250) & (df_ddos["t"] <= 400)]
    flash_event = df_flash.loc[(df_flash["t"] >= 250) & (df_flash["t"] <= 400)]

    assert ddos_event["pattern_anomaly_ratio"].mean() > 0.70
    assert ddos_event["is_attack"].all() == True

    assert flash_event["pattern_anomaly_ratio"].mean() < 0.10
    assert flash_event["is_attack"].all() == False


def test_unseen_mmtc_storm_characteristics() -> None:
    """Verify unseen_mmtc_storm triggers massive registration failure surge."""
    config = load_config()
    df = generate_run(scenario_name="unseen_mmtc_storm", seed=42, config=config)

    storm_event = df.loc[(df["t"] >= 250) & (df["t"] <= 400)]
    assert storm_event["mmtc_reg_failures"].mean() > 200.0
    assert (storm_event["event_label"] == "unknown").all()

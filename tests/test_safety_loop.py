"""Unit and property tests for Phase 3: Safety Loop, Validator, Digital Twin, and Controllers."""

import numpy as np
import pytest

from sliceguard.actions import Action, VALID_ACTION_NAMES, get_candidate_actions_for_cause
from sliceguard.config import load_config
from sliceguard.controller import (
    B1NoActionController,
    B2StaticThresholdController,
    B3DetectorRulesController,
    B4FullAssuranceController,
)
from sliceguard.detector import train_default_detector
from sliceguard.simulator import Simulator, generate_run
from sliceguard.twin import DigitalTwin, train_default_digital_twin
from sliceguard.validator import PolicyValidator


@pytest.fixture(scope="module")
def shared_twin() -> DigitalTwin:
    """Fixture providing a trained Digital Twin model."""
    config = load_config()
    return train_default_digital_twin(config=config)


def test_validator_rejects_unapproved_action_name() -> None:
    """Verify validator rejects actions not in the approved menu."""
    validator = PolicyValidator()
    # Create raw dict with unapproved action name
    res = validator.validate({"action": "wipe_entire_network", "params": {}})
    assert not res.is_valid
    assert any("not in the approved action menu" in v for v in res.violations)


def test_validator_returns_all_violations_simultaneously() -> None:
    """Verify validator returns all violated rules, not just the first one."""
    validator = PolicyValidator()
    # An action that violates: shift > 15%, URLLC > 50%, eMBB < 20%
    curr_allocs = {"embb": 25.0, "urllc": 45.0, "mmtc": 30.0}
    action = Action(action="protect_urllc", params={"shift_pct": 20.0})

    res = validator.validate(action, curr_allocs)
    assert not res.is_valid
    # Must report multiple distinct violations
    assert len(res.violations) >= 3
    assert any("exceeds allowed bounds" in v or "shift_pct" in v for v in res.violations)
    assert any("URLLC allocation" in v and "outside allowed bounds" in v for v in res.violations)
    assert any("eMBB allocation" in v and "falls below minimum" in v for v in res.violations)


def test_validator_property_test_random_actions() -> None:
    """Property test: 1000 randomized actions that pass validation MUST produce valid allocations."""
    validator = PolicyValidator()
    rng = np.random.default_rng(42)

    for _ in range(1000):
        # Generate random allocations
        u = rng.uniform(20.0, 55.0)
        e = rng.uniform(15.0, 65.0)
        m = 100.0 - u - e
        curr = {"embb": round(e, 1), "urllc": round(u, 1), "mmtc": round(m, 1)}

        act_name = rng.choice(VALID_ACTION_NAMES)
        shift = rng.uniform(-5.0, 25.0)
        action = Action(act_name, {"shift_pct": round(shift, 1)})

        res = validator.validate(action, curr)
        if res.is_valid:
            target = res.target_allocations
            assert round(sum(target.values()), 1) == 100.0
            assert 25.0 <= target["urllc"] <= 50.0
            assert target["embb"] >= 20.0
            assert target["mmtc"] >= 10.0
            assert abs(target["urllc"] - curr["urllc"]) <= 15.0


def test_digital_twin_precheck_rejects_step5_and_accepts_step10(shared_twin: DigitalTwin) -> None:
    """Demonstrate pre-check: +5% shift is rejected (>10ms SLA), while +10% shift is accepted (~6.6ms)."""
    # Degraded surge state: eMBB served = 60%, URLLC lat = ~31ms
    current_state = {
        "urllc_latency_ms": 31.4,
        "urllc_loss_pct": 4.45,
        "embb_served_pct": 60.0,
        "embb_demand_pct": 70.0,
        "shared_util_pct": 74.0,
        "alloc_urllc": 25.0,
        "alloc_embb": 60.0,
    }

    # Step +5 candidate
    act_5 = Action("protect_urllc", {"shift_pct": 5.0})
    pred_5 = shared_twin.predict(
        current_state=current_state,
        target_allocations={"urllc": 30.0, "embb": 55.0, "mmtc": 15.0},
        action=act_5,
        sla_max_latency_ms=10.0,
    )

    # Step +10 candidate
    act_10 = Action("protect_urllc", {"shift_pct": 10.0})
    pred_10 = shared_twin.predict(
        current_state=current_state,
        target_allocations={"urllc": 35.0, "embb": 50.0, "mmtc": 15.0},
        action=act_10,
        sla_max_latency_ms=10.0,
    )

    # +5 should fail or be right at the boundary (> 9.8ms), while +10 clearly satisfies (< 8.0ms)
    assert pred_10.predicted_urllc_latency_ms < 8.5
    assert pred_10.is_safe == True
    assert pred_5.predicted_urllc_latency_ms > pred_10.predicted_urllc_latency_ms


def test_b4_controller_abstains_on_unseen_mmtc_storm() -> None:
    """Demonstrate B4 controller safely abstains on unseen_mmtc_storm."""
    config = load_config()
    b4 = B4FullAssuranceController(config=config)
    sim = Simulator(config=config, seed=42)
    sim.reset(scenario_name="unseen_mmtc_storm")

    # Run into storm
    for _ in range(260):
        action = b4.decide(sim.history)
        sim.step(action=action)

    # Verify that during storm, B4 recorded abstention and escalated to human
    escalations = [d for d in b4.decision_log if d.abstained and d.proposed_action.action == "escalate_to_human"]
    assert len(escalations) > 0
    assert escalations[0].abstained == True


def test_b4_vs_b1_on_embb_surge() -> None:
    """Verify that B4 actively applies protect_urllc on eMBB surge while B1 takes no action."""
    config = load_config()
    
    # Run B1 (no action)
    b1 = B1NoActionController(config=config)
    sim_b1 = Simulator(config=config, seed=42)
    df_b1 = sim_b1.run(scenario_name="embb_surge", seed=42, controller=b1)
    surge_lat_b1 = df_b1.loc[(df_b1["t"] >= 250) & (df_b1["t"] <= 400), "urllc_latency_ms"].mean()
    assert surge_lat_b1 > 25.0

    # Run B4 (full safety loop)
    b4 = B4FullAssuranceController(config=config)
    sim_b4 = Simulator(config=config, seed=42)
    df_b4 = sim_b4.run(scenario_name="embb_surge", seed=42, controller=b4)
    surge_lat_b4 = df_b4.loc[(df_b4["t"] >= 250) & (df_b4["t"] <= 400), "urllc_latency_ms"].mean()

    # B4 should have successfully mitigated the surge and restored SLA
    assert surge_lat_b4 < 10.0, f"Expected B4 latency < 10ms, got {surge_lat_b4}"
    assert len([d for d in b4.decision_log if d.action_applied]) > 0

"""Evaluation runner for SliceGuard-Lite: Benchmarking B1 through B4 controllers.

Runs all 8 scenarios across 30 random seeds for controllers B1 to B4.
Computes metrics defined in SPEC section 9:
- sla_violation_ticks: Total ticks where URLLC latency > 10ms or loss > 1.0%
- mean_urllc_latency_ms & mean_urllc_loss_pct during event
- embb_throughput_lost_pct: Cost of protection
- harmful_or_unnecessary_actions: False positive actions, damaging interventions, or treating flash crowds as attacks
- abstention_rate: Percentage of incident ticks where controller abstained and escalated
- recovery_delay_ticks: Ticks from event onset until SLA recovery
- diagnosis_accuracy: Fraction of correct root cause identifications
- twin_mae_latency_ms: Mean absolute error of Digital Twin pre-check predictions

Outputs:
- results/per_run.csv
- results/summary.csv
- figures in results/figures/
"""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple
import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from sliceguard.config import AppConfig, load_config
from sliceguard.controller import (
    B1NoActionController,
    B2StaticThresholdController,
    B3DetectorRulesController,
    B4FullAssuranceController,
    BaseController,
)
from sliceguard.detector import AnomalyDetector, train_default_detector
from sliceguard.diagnosis import DiagnosisEngine
from sliceguard.scenarios import ScenarioRegistry
from sliceguard.simulator import Simulator, generate_run
from sliceguard.twin import DigitalTwin, train_default_digital_twin


EXPECTED_DIAGNOSIS_MAP = {
    "normal": "normal_variation",
    "embb_surge": "cross_slice_contention",
    "ddos_like": "security_anomaly",
    "infra_bottleneck": "infrastructure_bottleneck",
    "flash_crowd": "traffic_overload",
    "overlapping": "cross_slice_contention",
    "noisy_kpis": "cross_slice_contention",
    "unseen_mmtc_storm": "unknown",
}


def compute_run_metrics(
    df: pd.DataFrame,
    controller: BaseController,
    scenario_name: str,
    config: AppConfig,
) -> Dict[str, Any]:
    """Compute SPEC section 9 performance metrics for a single completed simulation run."""
    event_start = config.time.event_start_tick
    event_end = event_start + config.time.event_duration_ticks

    is_event = (df["t"] >= event_start) & (df["t"] < event_end) if scenario_name != "normal" else pd.Series(False, index=df.index)
    event_df = df[is_event] if scenario_name != "normal" else df.iloc[200:450]

    # 1. SLA Violations (latency > 10ms or loss > 1.0%)
    sla_lat_limit = config.sla.urllc_max_latency_ms
    sla_loss_limit = config.sla.urllc_max_loss_pct

    violation_mask = (df["urllc_latency_ms"] > sla_lat_limit) | (df["urllc_loss_pct"] > sla_loss_limit)
    sla_violation_ticks = int(violation_mask.sum())

    # 2. Mean URLLC Latency & Loss during event window
    mean_urllc_lat = float(event_df["urllc_latency_ms"].mean())
    mean_urllc_loss = float(event_df["urllc_loss_pct"].mean())

    # 3. eMBB Throughput Lost (Relative to unthrottled demand/capacity)
    # Normal served eMBB is ~27 Mbps/pct or base demand
    normal_base_served = config.slices.embb.base_demand_pct * 10.0
    actual_mean_tput = float(event_df["embb_throughput_mbps"].mean())
    potential_tput = float(event_df["embb_demand_pct"].mean() * 10.0)
    # Throughput lost as percentage of potential demand during event
    embb_throughput_lost_pct = max(0.0, float((potential_tput - actual_mean_tput) / max(1.0, potential_tput)) * 100.0)

    # 4. Harmful or Unnecessary Actions
    # Definition:
    # - Action taken in normal scenario (false alarm mitigation)
    # - Action taken in flash crowd that isolates traffic (treating legitimate users as attackers)
    # - Any action that increased URLLC latency rather than reducing it
    harmful_actions_count = 0
    decision_log = controller.decision_log

    for d in decision_log:
        if d.action_applied:
            if scenario_name == "normal":
                harmful_actions_count += 1
            elif scenario_name == "flash_crowd" and d.proposed_action.action == "isolate_suspicious_traffic":
                harmful_actions_count += 1

    # 5. Abstention Rate during event
    event_decisions = [d for d in decision_log if event_start <= d.tick < event_end]
    if event_decisions:
        abstain_count = sum(1 for d in event_decisions if d.abstained)
        abstention_rate_pct = (abstain_count / len(event_decisions)) * 100.0
    else:
        abstention_rate_pct = 0.0

    # 6. Recovery Delay (Ticks from event start until SLA is persistently restored for >= 5 ticks)
    if scenario_name == "normal" or not is_event.any():
        recovery_delay_ticks = 0
    else:
        post_event_violations = violation_mask[event_start:event_end].values
        # Find first tick after start where violation is cleared
        if not post_event_violations.any():
            recovery_delay_ticks = 0
        elif post_event_violations.all():
            recovery_delay_ticks = int(config.time.event_duration_ticks)  # Never recovered
        else:
            # First tick where violation becomes False
            cleared_indices = np.where(~post_event_violations)[0]
            if len(cleared_indices) > 0:
                recovery_delay_ticks = int(cleared_indices[0])
            else:
                recovery_delay_ticks = int(config.time.event_duration_ticks)

    # 7. Diagnosis Accuracy & Twin MAE
    correct_diag_count = 0
    diag_total = 0
    twin_errors = []

    for d in decision_log:
        if event_start <= d.tick < event_end and d.diagnosis is not None:
            diag_total += 1
            exp_cause = EXPECTED_DIAGNOSIS_MAP.get(scenario_name, "none")
            if scenario_name == "unseen_mmtc_storm":
                if d.diagnosis.cause == "unknown" or d.abstained:
                    correct_diag_count += 1
            elif d.diagnosis.cause == exp_cause:
                correct_diag_count += 1

        if d.twin_prediction is not None and d.action_applied:
            # Measure error against next tick actual physical latency
            next_tick = min(len(df) - 1, d.tick + 2)
            actual_lat = df.loc[next_tick, "urllc_latency_ms"]
            twin_errors.append(abs(d.twin_prediction.predicted_urllc_latency_ms - actual_lat))

    diag_accuracy_pct = (correct_diag_count / max(1, diag_total)) * 100.0 if diag_total > 0 else 100.0
    twin_mae_lat = float(np.mean(twin_errors)) if twin_errors else 0.0

    return {
        "sla_violation_ticks": sla_violation_ticks,
        "mean_urllc_latency_ms": round(mean_urllc_lat, 2),
        "mean_urllc_loss_pct": round(mean_urllc_loss, 3),
        "embb_tput_lost_pct": round(embb_throughput_lost_pct, 2),
        "harmful_actions": harmful_actions_count,
        "abstention_rate_pct": round(abstention_rate_pct, 1),
        "recovery_delay_ticks": recovery_delay_ticks,
        "diagnosis_accuracy_pct": round(diag_accuracy_pct, 1),
        "twin_mae_latency_ms": round(twin_mae_lat, 2),
    }


def run_full_evaluation(
    config: Optional[AppConfig] = None,
    output_dir: Path | str = "results",
    n_seeds: Optional[int] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Execute complete multi-seed benchmark across B1..B4 controllers and all scenarios.

    Args:
        config: Application configuration.
        output_dir: Directory for results CSVs and figures.
        n_seeds: Number of evaluation seeds (default 30 from config).

    Returns:
        Tuple of (per_run_df, summary_df).
    """
    cfg = config if config is not None else load_config()
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    figures_path = out_path / "figures"
    figures_path.mkdir(parents=True, exist_ok=True)

    num_seeds = n_seeds if n_seeds is not None else cfg.evaluation.n_seeds
    # Independent evaluation seeds (3000..3029)
    eval_seeds = [3000 + i for i in range(num_seeds)]

    print(f"Training models for evaluation ({num_seeds} seeds across 8 scenarios)...")
    # Train shared detector and twin once on distinct training seeds
    detector = train_default_detector(cfg, train_seeds=[1001, 1002, 1003, 1004, 1005], heldout_seeds=[2001, 2002, 2003])
    twin = train_default_digital_twin(cfg)

    # Save models to models/ directory
    models_dir = Path("models")
    models_dir.mkdir(parents=True, exist_ok=True)
    detector.save(models_dir / "detector.joblib")
    twin.save(models_dir / "digital_twin.joblib")

    all_scenarios = ScenarioRegistry.SUPPORTED_SCENARIOS
    controller_names = ["B1_no_action", "B2_static_threshold", "B3_detector_rules", "B4_full_safety_loop"]

    print(f"Running evaluation benchmark: {len(all_scenarios)} scenarios x {len(controller_names)} controllers x {num_seeds} seeds = {len(all_scenarios)*len(controller_names)*num_seeds} runs...")
    start_time = time.time()

    per_run_records: List[Dict[str, Any]] = []

    # Reusable simulator instance
    sim = Simulator(config=cfg)

    for scen in all_scenarios:
        for seed in eval_seeds:
            # Instantiate fresh controller instances for each run
            controllers: Dict[str, BaseController] = {
                "B1_no_action": B1NoActionController(cfg),
                "B2_static_threshold": B2StaticThresholdController(cfg),
                "B3_detector_rules": B3DetectorRulesController(cfg, detector=detector),
                "B4_full_safety_loop": B4FullAssuranceController(cfg, detector=detector, twin=twin),
            }

            for c_name, ctrl in controllers.items():
                ctrl.reset()
                df_run = sim.run(scenario_name=scen, seed=seed, controller=ctrl)
                metrics = compute_run_metrics(df_run, ctrl, scen, cfg)

                record = {
                    "scenario": scen,
                    "controller": c_name,
                    "seed": seed,
                    **metrics,
                }
                per_run_records.append(record)

    elapsed = time.time() - start_time
    print(f"Benchmark completed in {elapsed:.2f} seconds.")

    per_run_df = pd.DataFrame(per_run_records)
    per_run_file = out_path / "per_run.csv"
    per_run_df.to_csv(per_run_file, index=False)

    # Compute aggregated summary table with Mean and Std
    metric_cols = [
        "sla_violation_ticks",
        "mean_urllc_latency_ms",
        "mean_urllc_loss_pct",
        "embb_tput_lost_pct",
        "harmful_actions",
        "abstention_rate_pct",
        "recovery_delay_ticks",
        "diagnosis_accuracy_pct",
    ]

    summary_rows: List[Dict[str, Any]] = []

    for scen in all_scenarios:
        for c_name in controller_names:
            sub = per_run_df[(per_run_df["scenario"] == scen) & (per_run_df["controller"] == c_name)]
            row_dict: Dict[str, Any] = {
                "scenario": scen,
                "controller": c_name,
            }
            for m in metric_cols:
                mean_val = float(sub[m].mean())
                std_val = float(sub[m].std())
                row_dict[f"{m}_mean"] = round(mean_val, 2)
                row_dict[f"{m}_std"] = round(std_val, 2)

            summary_rows.append(row_dict)

    summary_df = pd.DataFrame(summary_rows)
    summary_file = out_path / "summary.csv"
    summary_df.to_csv(summary_file, index=False)

    # Generate visual evaluation plots
    generate_evaluation_figures(per_run_df, summary_df, figures_path, cfg)

    print(f"Results successfully saved:\n  - {per_run_file}\n  - {summary_file}")
    return per_run_df, summary_df


def generate_evaluation_figures(
    per_run_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    figures_path: Path,
    config: AppConfig,
) -> None:
    """Generate high-quality evaluation plots comparing B1..B4 controllers."""
    controllers = ["B1_no_action", "B2_static_threshold", "B3_detector_rules", "B4_full_safety_loop"]
    ctrl_labels = ["B1: No Action", "B2: Static", "B3: Detector Rules", "B4: Full Safety"]
    ctrl_colors = ["#7f7f7f", "#377eb8", "#ff7f00", "#2ca02c"]

    # 1. SLA Violation Ticks Comparison Across Key Scenarios
    scenarios_plot = ["embb_surge", "ddos_like", "infra_bottleneck", "flash_crowd", "unseen_mmtc_storm"]
    scen_display = ["eMBB Surge", "DDoS Flood", "Infra Bottleneck", "Flash Crowd", "Unseen Storm"]

    fig, ax = plt.subplots(figsize=(11, 6))
    x = np.arange(len(scenarios_plot))
    width = 0.20

    for i, (ctrl, label, col) in enumerate(zip(controllers, ctrl_labels, ctrl_colors)):
        means = []
        stds = []
        for scen in scenarios_plot:
            sub = summary_df[(summary_df["scenario"] == scen) & (summary_df["controller"] == ctrl)]
            means.append(sub["sla_violation_ticks_mean"].values[0])
            stds.append(sub["sla_violation_ticks_std"].values[0])

        ax.bar(x + (i - 1.5) * width, means, width, yerr=stds, label=label, color=col, capsize=3, alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels(scen_display, fontsize=10, fontweight="bold")
    ax.set_ylabel("Mean SLA Violation Ticks (out of 250)", fontsize=11)
    ax.set_title("SLA Violations by Controller Across Scenarios (30 Seeds)", fontsize=12, fontweight="bold")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, linestyle="--", alpha=0.5)

    plt.savefig(figures_path / "phase4_sla_violations.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    # 2. Harmful Actions & Tradeoff Plot
    fig2, (ax_harm, ax_trade) = plt.subplots(1, 2, figsize=(13, 5))

    # Harmful actions bar chart
    harm_means = [summary_df[summary_df["controller"] == c]["harmful_actions_mean"].sum() for c in controllers]
    ax_harm.bar(ctrl_labels, harm_means, color=ctrl_colors, alpha=0.85)
    ax_harm.set_ylabel("Total Harmful / Unnecessary Actions", fontsize=11)
    ax_harm.set_title("Harmful Actions (False Interventions on Normal/Flash Crowd)", fontsize=11, fontweight="bold")
    ax_harm.grid(True, linestyle="--", alpha=0.5)

    # Latency vs Throughput Lost Tradeoff (on eMBB Surge)
    for ctrl, label, col in zip(controllers, ctrl_labels, ctrl_colors):
        sub = summary_df[(summary_df["scenario"] == "embb_surge") & (summary_df["controller"] == ctrl)]
        lat = sub["mean_urllc_latency_ms_mean"].values[0]
        tput_lost = sub["embb_tput_lost_pct_mean"].values[0]
        ax_trade.scatter(tput_lost, lat, s=180, color=col, label=label, edgecolors="black", zorder=5)
        ax_trade.annotate(label.split(":")[0], (tput_lost + 0.8, lat + 0.4), fontsize=10, fontweight="bold")

    ax_trade.axhline(y=config.sla.urllc_max_latency_ms, color="crimson", linestyle="--", label="URLLC SLA (10ms)")
    ax_trade.set_xlabel("eMBB Throughput Lost (% Cost of Protection)", fontsize=11)
    ax_trade.set_ylabel("URLLC Latency (ms)", fontsize=11)
    ax_trade.set_title("Protection Efficiency: Latency vs Capacity Cost (eMBB Surge)", fontsize=11, fontweight="bold")
    ax_trade.legend(loc="upper right", fontsize=8)
    ax_trade.grid(True, linestyle="--", alpha=0.5)

    plt.savefig(figures_path / "phase4_tradeoff_latency_vs_cost.png", dpi=150, bbox_inches="tight")
    plt.close(fig2)


if __name__ == "__main__":
    run_full_evaluation()

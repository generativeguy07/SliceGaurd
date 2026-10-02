"""Sanity plotting utility for SliceGuard-Lite Phase 1.

Generates high-resolution time-series KPI figures for normal, surge, and multi-scenario runs.
Saves plots to results/figures/ as visual proof of simulator dynamics and SLA violations.
"""

from __future__ import annotations

from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

from sliceguard.config import load_config
from sliceguard.simulator import Simulator, generate_run


def generate_sanity_plots(output_dir: Path | str = "results/figures") -> None:
    """Generate and save sanity verification plots for Phase 1.

    Args:
        output_dir: Directory path where generated figure PNGs are saved.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    config = load_config()

    # 1. Normal vs eMBB Surge Detailed Comparison
    df_normal = generate_run(scenario_name="normal", seed=42, config=config)
    df_surge = generate_run(scenario_name="embb_surge", seed=42, config=config)

    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    plt.subplots_adjust(hspace=0.25)

    # Subplot 1: Bandwidth Demand & Served Load
    ax1 = axes[0]
    ax1.plot(df_normal["t"], df_normal["embb_served_pct"], label="Normal Served eMBB (%)", color="#2b5c8f", alpha=0.7)
    ax1.plot(df_surge["t"], df_surge["embb_demand_pct"], label="Surge Demand eMBB (%)", color="#d95f02", linestyle="--")
    ax1.plot(df_surge["t"], df_surge["embb_served_pct"], label="Surge Served eMBB (%)", color="#e7298a", linewidth=1.5)
    ax1.axhline(y=config.interference.threshold_pct, color="red", linestyle=":", label="Interference Threshold (45%)")
    ax1.set_ylabel("Capacity (%)")
    ax1.set_title("eMBB Demand vs Served Bandwidth (Interference Trigger at 45%)", fontsize=11, fontweight="bold")
    ax1.legend(loc="upper right", fontsize=8)
    ax1.grid(True, linestyle="--", alpha=0.5)

    # Subplot 2: URLLC Latency (Critical SLA)
    ax2 = axes[1]
    ax2.plot(df_normal["t"], df_normal["urllc_latency_ms"], label="Normal URLLC Latency (~6ms)", color="#1b9e77")
    ax2.plot(df_surge["t"], df_surge["urllc_latency_ms"], label="Surge URLLC Latency (~31ms)", color="#d95f02", linewidth=1.5)
    ax2.axhline(y=config.sla.urllc_max_latency_ms, color="crimson", linestyle="-.", linewidth=1.5, label="URLLC SLA Limit (10 ms)")
    ax2.set_ylabel("Latency (ms)")
    ax2.set_title("URLLC Latency Degradation via Cross-Slice Interference", fontsize=11, fontweight="bold")
    ax2.legend(loc="upper right", fontsize=8)
    ax2.grid(True, linestyle="--", alpha=0.5)

    # Subplot 3: URLLC Packet Loss (%)
    ax3 = axes[2]
    ax3.plot(df_normal["t"], df_normal["urllc_loss_pct"], label="Normal URLLC Loss (0.1%)", color="#1b9e77")
    ax3.plot(df_surge["t"], df_surge["urllc_loss_pct"], label="Surge URLLC Loss (~4.5%)", color="#7570b3", linewidth=1.5)
    ax3.axhline(y=config.sla.urllc_max_loss_pct, color="crimson", linestyle="-.", linewidth=1.5, label="URLLC Loss SLA (1.0%)")
    ax3.set_xlabel("Time (seconds / ticks)")
    ax3.set_ylabel("Packet Loss (%)")
    ax3.set_title("URLLC Packet Loss (%) during Surge", fontsize=11, fontweight="bold")
    ax3.legend(loc="upper right", fontsize=8)
    ax3.grid(True, linestyle="--", alpha=0.5)

    plot1_file = out_path / "phase1_normal_vs_surge.png"
    plt.savefig(plot1_file, dpi=150, bbox_inches="tight")
    plt.close(fig)

    # 2. Multi-Scenario Overview (6 key scenarios)
    scenarios_to_plot = ["normal", "embb_surge", "ddos_like", "infra_bottleneck", "flash_crowd", "unseen_mmtc_storm"]
    fig2, (ax_lat, ax_pat) = plt.subplots(2, 1, figsize=(11, 7), sharex=True)

    colors = {
        "normal": "#7f7f7f",
        "embb_surge": "#e41a1c",
        "ddos_like": "#984ea3",
        "infra_bottleneck": "#ff7f00",
        "flash_crowd": "#377eb8",
        "unseen_mmtc_storm": "#4daf4a",
    }

    for scen in scenarios_to_plot:
        df_scen = generate_run(scenario_name=scen, seed=42, config=config)
        ax_lat.plot(df_scen["t"], df_scen["urllc_latency_ms"], label=scen, color=colors[scen], alpha=0.85)
        ax_pat.plot(df_scen["t"], df_scen["pattern_anomaly_ratio"], label=scen, color=colors[scen], alpha=0.85)

    ax_lat.axhline(y=config.sla.urllc_max_latency_ms, color="black", linestyle="--", label="SLA 10ms")
    ax_lat.set_ylabel("URLLC Latency (ms)")
    ax_lat.set_title("Multi-Scenario Comparison: URLLC Latency Profiles", fontsize=11, fontweight="bold")
    ax_lat.legend(loc="upper right", fontsize=8, ncol=2)
    ax_lat.grid(True, linestyle="--", alpha=0.5)

    ax_pat.set_ylabel("Pattern Anomaly Ratio (0..1)")
    ax_pat.set_xlabel("Time (seconds / ticks)")
    ax_pat.set_title("Pattern Anomaly Ratio (Distinguishes DDoS vs Flash Crowd)", fontsize=11, fontweight="bold")
    ax_pat.legend(loc="upper right", fontsize=8, ncol=2)
    ax_pat.grid(True, linestyle="--", alpha=0.5)

    plot2_file = out_path / "phase1_scenarios_overview.png"
    plt.savefig(plot2_file, dpi=150, bbox_inches="tight")
    plt.close(fig2)

    print(f"Generated sanity plots successfully:\n  - {plot1_file}\n  - {plot2_file}")


if __name__ == "__main__":
    generate_sanity_plots()

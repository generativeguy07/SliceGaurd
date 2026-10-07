"""Streamlit Interactive Assurance Dashboard for SliceGuard-Lite.

Provides real-time interactive telemetry visualization, closed-loop event injection,
explainable diagnosis logs, Digital Twin pre-check audits, and empirical benchmark tables.
Runs fully offline with free Python libraries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from sliceguard.actions import Action
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
from sliceguard.simulator import KPIRow, Simulator
from sliceguard.twin import DigitalTwin, train_default_digital_twin


st.set_page_config(
    page_title="SliceGuard-Lite | 5G Slice Assurance",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def get_cached_models(config: AppConfig) -> Tuple[AnomalyDetector, DigitalTwin]:
    """Train or load shared detector and digital twin models."""
    models_dir = Path("models")
    det_path = models_dir / "detector.joblib"
    twin_path = models_dir / "digital_twin.joblib"

    if det_path.exists():
        detector = AnomalyDetector.load(det_path)
    else:
        detector = train_default_detector(config)

    if twin_path.exists():
        twin = DigitalTwin.load(twin_path)
    else:
        twin = train_default_digital_twin(config)

    return detector, twin


def init_session_state(config: AppConfig) -> None:
    """Initialize session state for simulator and controllers."""
    if "config" not in st.session_state:
        st.session_state.config = config

    detector, twin = get_cached_models(config)

    if "detector" not in st.session_state:
        st.session_state.detector = detector
    if "twin" not in st.session_state:
        st.session_state.twin = twin

    if "sim" not in st.session_state:
        st.session_state.sim = Simulator(config=config, seed=config.seed)

    if "scenario" not in st.session_state:
        st.session_state.scenario = "embb_surge"

    if "controller_id" not in st.session_state:
        st.session_state.controller_id = "B4_full"

    if "controller" not in st.session_state:
        st.session_state.controller = B4FullAssuranceController(
            config=config,
            detector=detector,
            twin=twin,
        )

    # Automatically advance to tick 250 on initial load so the dashboard is immediately populated
    if len(st.session_state.sim.history) == 0:
        step_sim(250)


def reset_simulation(scenario: str, controller_id: str, seed: int, start_ticks: int = 250) -> None:
    """Reset simulation with chosen scenario, controller, seed, and optional initial fast-forward."""
    cfg = st.session_state.config
    det = st.session_state.detector
    twin = st.session_state.twin

    st.session_state.sim = Simulator(config=cfg, seed=seed)
    st.session_state.sim.reset(scenario_name=scenario, seed=seed)
    st.session_state.scenario = scenario
    st.session_state.controller_id = controller_id

    if controller_id == "B1_no_action":
        ctrl = B1NoActionController(cfg)
    elif controller_id == "B2_static":
        ctrl = B2StaticThresholdController(cfg)
    elif controller_id == "B3_rules":
        ctrl = B3DetectorRulesController(cfg, detector=det)
    else:
        ctrl = B4FullAssuranceController(cfg, detector=det, twin=twin)

    st.session_state.controller = ctrl

    if start_ticks > 0:
        step_sim(start_ticks)


def step_sim(n_steps: int = 1) -> None:
    """Advance simulation by n ticks."""
    sim: Simulator = st.session_state.sim
    ctrl: BaseController = st.session_state.controller

    for _ in range(n_steps):
        if sim.current_tick >= sim.config.time.run_length_ticks:
            break
        action = ctrl.decide(sim.history)
        sim.step(action=action)


def run_full_scenario() -> None:
    """Fast-forward simulation through all 600 ticks."""
    sim: Simulator = st.session_state.sim
    remaining = sim.config.time.run_length_ticks - sim.current_tick
    if remaining > 0:
        step_sim(remaining)


def main() -> None:
    """Main Streamlit application interface."""
    config = load_config()
    init_session_state(config)

    # --- TOP HEADER & SIMULATION BADGE ---
    header_col1, header_col2 = st.columns([3, 1])
    with header_col1:
        st.title("🛡️ SliceGuard-Lite: Safety-First 5G Slice Assurance")
        st.caption("Simulation-Based Autonomous Assurance with Predictive Digital Twin Pre-Checking & Abstention")
    with header_col2:
        st.warning("⚠️ **SIMULATION PROTOTYPE**\n\nProof-of-Concept for Nokia Shark Tank (AI in Telecom)")

    # --- SIDEBAR CONTROLS ---
    with st.sidebar:
        st.header("⚙️ Simulation Controls")
        
        selected_seed = st.number_input("Random Seed", value=int(config.seed), min_value=1, max_value=99999, step=1)
        
        st.subheader("🎯 Active Controller")
        controller_options = {
            "B4_full": "B4: Full Safety Loop (Twin + Abstain)",
            "B3_rules": "B3: Detector + Rules (No Twin)",
            "B2_static": "B2: Static Threshold (Reactive)",
            "B1_no_action": "B1: No Action (Passive Baseline)",
        }
        chosen_ctrl = st.selectbox(
            "Select Controller",
            options=list(controller_options.keys()),
            format_func=lambda k: controller_options[k],
            index=list(controller_options.keys()).index(st.session_state.controller_id),
        )

        # If user changed controller, reset and apply
        if chosen_ctrl != st.session_state.controller_id:
            reset_simulation(st.session_state.scenario, chosen_ctrl, selected_seed, start_ticks=st.session_state.sim.current_tick or 250)
            st.rerun()

        st.subheader("⚡ Event Injection (Click to Inject & Jump to Event)")
        scenario_buttons = {
            "embb_surge": ("⚠️ Inject eMBB Surge (Contention)", "embb_surge", 250),
            "ddos_like": ("🔴 Inject DDoS Attack (Security)", "ddos_like", 250),
            "infra_bottleneck": ("🟠 Inject Hardware Fault (Infra)", "infra_bottleneck", 250),
            "flash_crowd": ("🔵 Inject Flash Crowd (Legit)", "flash_crowd", 300),
            "unseen_mmtc_storm": ("🟣 Inject Unknown IoT Storm (Abstain)", "unseen_mmtc_storm", 250),
            "normal": ("🟢 Normal Baseline (No Event)", "normal", 200),
        }

        for scen_key, (label, scen_val, jump_tick) in scenario_buttons.items():
            if st.button(label, use_container_width=True):
                reset_simulation(scen_val, chosen_ctrl, selected_seed, start_ticks=jump_tick)
                st.rerun()

        st.divider()
        st.subheader("⏩ Step & Navigation Controls")
        btn_c1, btn_c2 = st.columns(2)
        with btn_c1:
            if st.button("➕ Step +10s", use_container_width=True):
                step_sim(10)
                st.rerun()
        with btn_c2:
            if st.button("⏩ Step +50s", use_container_width=True):
                step_sim(50)
                st.rerun()

        if st.button("🏁 Run Full 600s Run", use_container_width=True):
            run_full_scenario()
            st.rerun()

        if st.button("🔄 Reset to 0s (Start of Run)", use_container_width=True):
            reset_simulation(st.session_state.scenario, chosen_ctrl, selected_seed, start_ticks=0)
            st.rerun()

    # --- MAIN CONTENT TABS ---
    tab_live, tab_bench, tab_arch = st.tabs([
        "🔴 Live Closed-Loop Dashboard",
        "📊 Multi-Seed Benchmark (B1–B4)",
        "💡 System Architecture & Safety",
    ])

    sim: Simulator = st.session_state.sim
    ctrl: BaseController = st.session_state.controller
    history = sim.history
    current_scenario = st.session_state.scenario

    scenario_labels_map = {
        "normal": ("Normal Baseline Traffic", "No anomalous event injected. All slices operate at baseline."),
        "embb_surge": ("eMBB Bandwidth Demand Surge", "eMBB demand jumps to 70% at 200s, causing cross-slice buffer contention on URLLC."),
        "ddos_like": ("DDoS-Like Flood Attack", "Malicious request flood jumps to 6200 req/s with abnormal packet pattern ratio (0.88)."),
        "infra_bottleneck": ("Infrastructure Hardware Fault", "Capacity factor drops to 0.60 at 200s, throttling throughput and increasing delay."),
        "flash_crowd": ("Legitimate Flash Crowd Surge", "Organic user traffic smoothly ramps to 65%. Packet pattern ratio stays strictly normal (<0.15)."),
        "unseen_mmtc_storm": ("Unseen Massive IoT Storm (Zero-Day)", "IoT registration attempts spike to 350/s. Unmodeled state triggers safety abstention."),
    }
    scen_title, scen_desc = scenario_labels_map.get(current_scenario, ("Active Scenario", ""))

    with tab_live:
        # 1. SCENARIO BANNER
        event_start = config.time.event_start_tick
        event_end = event_start + config.time.event_duration_ticks
        is_in_event_window = (event_start <= sim.current_tick <= event_end) and current_scenario != "normal"
        
        status_bg = "#3d1414" if is_in_event_window else "#142d14"
        event_badge = f"🔥 EVENT ACTIVE (Window: {event_start}s – {event_end}s)" if is_in_event_window else ("🟢 PRE-EVENT / BASELINE" if sim.current_tick < event_start else "✅ POST-EVENT RECOVERY")
        
        st.info(f"📍 **Active Scenario**: **{scen_title}** | **Status**: {event_badge} | **Active Controller**: `{controller_options[st.session_state.controller_id]}`\n\n_{scen_desc}_")

        # 2. LIVE STATUS METRICS BAR
        current_tick = sim.current_tick
        total_ticks = config.time.run_length_ticks
        
        if history:
            latest = history[-1]
            lat_val = latest.urllc_latency_ms
            loss_val = latest.urllc_loss_pct
            embb_val = latest.embb_served_pct
            alloc_u = latest.alloc_urllc
            alloc_e = latest.alloc_embb
            is_breaching = (lat_val > config.sla.urllc_max_latency_ms) or (loss_val > config.sla.urllc_max_loss_pct)
        else:
            lat_val, loss_val, embb_val, alloc_u, alloc_e = 6.0, 0.1, 27.0, 25.0, 60.0
            is_breaching = False

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("⏱️ Simulation Time", f"{current_tick}s / {total_ticks}s")
        m2.metric(
            "⚡ URLLC Latency",
            f"{lat_val:.1f} ms",
            delta=f"SLA Target: <=10ms",
            delta_color="normal" if lat_val <= 10.0 else "inverse",
        )
        m3.metric(
            "📉 URLLC Loss",
            f"{loss_val:.2f} %",
            delta=f"SLA Target: <=1.0%",
            delta_color="normal" if loss_val <= 1.0 else "inverse",
        )
        m4.metric("📊 eMBB Served Load", f"{embb_val:.1f} %", f"Alloc: {alloc_e:.1f}%")
        m5.metric("🎯 URLLC Capacity", f"{alloc_u:.1f} %", f"Min Floor: 25%")

        # 3. STATUS BANNER
        latest_dec = ctrl.latest_decision
        if latest_dec and latest_dec.is_incident:
            if latest_dec.abstained:
                st.error(f"🛑 **SAFETY ABSTENTION ACTIVE (Tick {current_tick}s)**: Diagnosis confidence below safety threshold or unmodeled anomaly signature (`{latest_dec.diagnosis.cause if latest_dec.diagnosis else 'unknown'}`). Escalated to human operator without automated modification.")
            elif latest_dec.action_applied:
                st.success(f"✅ **ACTION APPLIED (Tick {latest_dec.tick}s)**: `{latest_dec.proposed_action.action}` ({latest_dec.proposed_action.params}) passed Policy Validation and Digital Twin Pre-Check. SLA Restored!")
            else:
                st.warning(f"⚠️ **INCIDENT DETECTED (Tick {current_tick}s)**: Incident active. Cooldown or monitoring in progress.")
        else:
            st.info("🟢 **NORMAL OPERATION**: Telemetry within healthy parameters.")

        # 4. LIVE TELEMETRY CHARTS
        if history:
            df_hist = pd.DataFrame([r.to_dict() for r in history])
            
            c_left, c_right = st.columns(2)
            with c_left:
                st.markdown("#### ⚡ URLLC Latency (ms) vs. 10ms SLA Target")
                chart_lat = df_hist[["t", "urllc_latency_ms"]].copy()
                chart_lat["SLA_Limit_10ms"] = config.sla.urllc_max_latency_ms
                st.line_chart(chart_lat.set_index("t"), color=["#d95f02", "#e41a1c"])

                st.markdown("#### 🍰 Slice Dynamic Allocations (%)")
                st.line_chart(df_hist[["t", "alloc_embb", "alloc_urllc", "alloc_mmtc"]].set_index("t"))

            with c_right:
                st.markdown("#### 📉 Packet Loss (%) & 1.0% SLA Target")
                chart_loss = df_hist[["t", "urllc_loss_pct"]].copy()
                chart_loss["Loss_SLA_1pct"] = config.sla.urllc_max_loss_pct
                st.line_chart(chart_loss.set_index("t"), color=["#7570b3", "#e41a1c"])

                st.markdown("#### 🔍 Pattern Anomaly Ratio (DDoS vs Flash Crowd)")
                st.line_chart(df_hist[["t", "pattern_anomaly_ratio"]].set_index("t"), color=["#1b9e77"])
        else:
            st.info("Simulation at 0s. Click **➕ Step +10s** or **⏩ Step +50s** in the sidebar to advance telemetry.")

        # 5. SAFETY PRE-CHECK & DECISION PANEL
        st.divider()
        st.subheader("🛡️ Safety Pre-Check & Decision Explainability Panel")
        
        p_col1, p_col2 = st.columns([1, 1])
        with p_col1:
            st.markdown("##### 🩺 Causal Diagnosis & Evidence")
            # Find recent diagnosis if available
            recent_diag_dec = next((d for d in reversed(ctrl.decision_log) if d.diagnosis is not None), latest_dec)
            if recent_diag_dec and recent_diag_dec.diagnosis:
                diag = recent_diag_dec.diagnosis
                st.write(f"**Diagnosed Cause:** `{diag.cause}`")
                st.write(f"**Confidence:** `{diag.confidence*100:.1f}%` (Abstain Threshold: 60%)")
                st.write("**Evaluated Evidence Propositions:**")
                for ev in diag.evidence_details[:4]:
                    icon = "✅" if ev.is_satisfied else "❌"
                    st.write(f"{icon} {ev.description} (Observed: `{ev.observed_value:.1f}`)")
            else:
                st.write("No active anomaly diagnosed. All evidence within normal operating bands.")

        with p_col2:
            st.markdown("##### 🔮 Digital Twin Pre-Check Evaluation")
            recent_twin_dec = next((d for d in reversed(ctrl.decision_log) if d.twin_prediction is not None), latest_dec)
            if recent_twin_dec and recent_twin_dec.twin_prediction:
                twin_p = recent_twin_dec.twin_prediction
                st.write(f"**Tested Action:** `{twin_p.candidate_action.action}` ({twin_p.candidate_action.params})")
                st.write(f"**Predicted URLLC Latency:** `{twin_p.predicted_urllc_latency_ms:.2f} ms` (SLA: <=10.0ms)")
                st.write(f"**Predicted URLLC Loss:** `{twin_p.predicted_urllc_loss_pct:.2f} %` (SLA: <=1.0%)")
                st.write(f"**Policy Validator:** {'✅ PASSED (Within bounds)' if recent_twin_dec.validation and recent_twin_dec.validation.is_valid else '❌ REJECTED'}")
                st.write(f"**Pre-Check Result:** {'✅ PASSED & APPLIED' if twin_p.is_safe else '❌ REJECTED (Unsafe for SLA)'}")
            else:
                st.write("Digital Twin Pre-Check idle (no pending action candidate).")

        if latest_dec:
            st.text_area("📝 Plain-Language Decision Explanation", value=latest_dec.explanation, height=110)

        # 6. RECENT DECISION LOG
        if ctrl.decision_log:
            with st.expander("📋 View Full Decision Log Table", expanded=True):
                log_data = []
                for d in ctrl.decision_log:
                    log_data.append({
                        "Tick (s)": d.tick,
                        "Incident": "⚠️ YES" if d.is_incident else "No",
                        "Diagnosis": d.diagnosis.cause if d.diagnosis else "none",
                        "Confidence": f"{d.diagnosis.confidence*100:.1f}%" if d.diagnosis else "-",
                        "Proposed Action": d.proposed_action.action,
                        "Parameters": str(d.proposed_action.params),
                        "Twin Pred Latency": f"{d.twin_prediction.predicted_urllc_latency_ms:.2f}ms" if d.twin_prediction else "-",
                        "Applied": "✅ YES" if d.action_applied else "No",
                        "Abstained": "🛑 ABSTAINED" if d.abstained else "No",
                    })
                st.dataframe(pd.DataFrame(log_data).tail(15), use_container_width=True)

    with tab_bench:
        st.subheader("📊 Multi-Seed Empirical Evaluation Results (30 Independent Seeds)")
        summary_csv = Path("results/summary.csv")
        
        if summary_csv.exists():
            df_sum = pd.read_csv(summary_csv)
            st.dataframe(df_sum, use_container_width=True)

            b_col1, b_col2 = st.columns(2)
            with b_col1:
                fig1 = Path("results/figures/phase4_sla_violations.png")
                if fig1.exists():
                    st.image(str(fig1), caption="SLA Violations by Controller Across 8 Scenarios (30 Seeds)")
            with b_col2:
                fig2 = Path("results/figures/phase4_tradeoff_latency_vs_cost.png")
                if fig2.exists():
                    st.image(str(fig2), caption="Harmful Actions & Efficiency Tradeoff")
        else:
            st.warning("`results/summary.csv` not found. Please run `python -m sliceguard.evaluate` first.")

    with tab_arch:
        st.subheader("💡 SliceGuard-Lite Architecture & Design Principles")
        st.markdown(r"""
        ### Core Principles
        1. **Simulation-Based Ground Truth**: Evaluated purely in mathematical simulation without claiming vendor integration.
        2. **Ground-Truth Shielding**: The detector, diagnosis, and controller never read ground-truth labels.
        3. **No LLM in the Control Loop**: Actions come strictly from a fixed action catalog verified by deterministic validators.
        4. **Predictive Digital Twin Pre-Check**: Candidate actions are pre-tested on an independent approximate model to prove safety before application.
        5. **Abstention When Uncertain**: When confidence drops below $60\%$ or novel anomalies occur (e.g. unseen IoT storm), the system safely escalates to humans.
        """)


if __name__ == "__main__":
    main()

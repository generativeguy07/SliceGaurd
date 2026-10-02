"""Streamlit Interactive Assurance Dashboard for SliceGuard-Lite.

Provides real-time interactive telemetry visualization, closed-loop event injection,
explainable diagnosis logs, Digital Twin pre-check audits, and empirical benchmark tables.
Runs fully offline with free Python libraries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
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
        st.session_state.scenario = "normal"

    if "controller_id" not in st.session_state:
        st.session_state.controller_id = "B4_full"

    if "controller" not in st.session_state:
        st.session_state.controller = B4FullAssuranceController(
            config=config,
            detector=detector,
            twin=twin,
        )


def reset_simulation(scenario: str, controller_id: str, seed: int) -> None:
    """Reset simulation with chosen scenario, controller, and seed."""
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


def step_sim(n_steps: int = 1) -> None:
    """Advance simulation by n ticks."""
    sim: Simulator = st.session_state.sim
    ctrl: BaseController = st.session_state.controller

    for _ in range(n_steps):
        if sim.current_tick >= sim.config.time.run_length_ticks:
            break
        action = ctrl.decide(sim.history)
        sim.step(action=action)


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
            "B1_no_action": "B1: No Action (Passive)",
        }
        chosen_ctrl = st.selectbox(
            "Select Controller",
            options=list(controller_options.keys()),
            format_func=lambda k: controller_options[k],
            index=0,
        )

        st.subheader("⚡ Event Injection")
        scenario_buttons = {
            "normal": ("🟢 Normal Baseline", "normal"),
            "embb_surge": ("⚠️ Inject eMBB Surge", "embb_surge"),
            "ddos_like": ("🔴 Inject DDoS Attack", "ddos_like"),
            "infra_bottleneck": ("🟠 Inject Hardware Fault", "infra_bottleneck"),
            "flash_crowd": ("🔵 Inject Flash Crowd", "flash_crowd"),
            "unseen_mmtc_storm": ("🟣 Inject Unknown IoT Storm", "unseen_mmtc_storm"),
        }

        for scen_key, (label, scen_val) in scenario_buttons.items():
            if st.button(label, use_container_width=True):
                reset_simulation(scen_val, chosen_ctrl, selected_seed)
                st.rerun()

        st.divider()
        st.subheader("⏩ Step Controls")
        btn_c1, btn_c2, btn_c3 = st.columns(3)
        with btn_c1:
            if st.button("+1s", use_container_width=True):
                step_sim(1)
        with btn_c2:
            if st.button("+10s", use_container_width=True):
                step_sim(10)
        with btn_c3:
            if st.button("+50s", use_container_width=True):
                step_sim(50)

        if st.button("🔄 Reset Current Run", use_container_width=True):
            reset_simulation(st.session_state.scenario, chosen_ctrl, selected_seed)
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

    with tab_live:
        # 1. LIVE STATUS METRICS BAR
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
        m1.metric("⏱️ Sim Time", f"{current_tick}s / {total_ticks}s")
        m2.metric(
            "⚡ URLLC Latency",
            f"{lat_val:.1f} ms",
            delta=f"SLA: <=10ms",
            delta_color="normal" if lat_val <= 10.0 else "inverse",
        )
        m3.metric(
            "📉 URLLC Loss",
            f"{loss_val:.2f} %",
            delta=f"SLA: <=1.0%",
            delta_color="normal" if loss_val <= 1.0 else "inverse",
        )
        m4.metric("📊 eMBB Served", f"{embb_val:.1f} %", f"Alloc: {alloc_e}%")
        m5.metric("🎯 URLLC Alloc", f"{alloc_u:.1f} %", f"Floor: 25%")

        # 2. STATUS BANNER
        latest_dec = ctrl.latest_decision
        if latest_dec and latest_dec.is_incident:
            if latest_dec.abstained:
                st.error(f"🛑 **SAFETY ABSTENTION**: Confidence low or novel event signature. Escalated to human operators. (Tick {current_tick}s)")
            elif latest_dec.action_applied:
                st.success(f"✅ **ACTION APPLIED**: {latest_dec.proposed_action.action} ({latest_dec.proposed_action.params}) passed Policy & Digital Twin Pre-Check.")
            else:
                st.warning(f"⚠️ **INCIDENT DETECTED**: Monitoring / Cooldown active.")
        else:
            st.info("🟢 **NORMAL OPERATION**: Telemetry within healthy parameters.")

        # 3. LIVE CHARTS
        if history:
            df_hist = pd.DataFrame([r.to_dict() for r in history])
            
            c_left, c_right = st.columns(2)
            with c_left:
                st.markdown("#### ⚡ URLLC Latency & SLA Target")
                chart_lat = df_hist[["t", "urllc_latency_ms"]].copy()
                chart_lat["SLA_Limit_10ms"] = config.sla.urllc_max_latency_ms
                st.line_chart(chart_lat.set_index("t"), color=["#d95f02", "#e41a1c"])

                st.markdown("#### 🍰 Slice Allocations (%)")
                st.line_chart(df_hist[["t", "alloc_embb", "alloc_urllc", "alloc_mmtc"]].set_index("t"))

            with c_right:
                st.markdown("#### 📉 Packet Loss & Throughput")
                chart_loss = df_hist[["t", "urllc_loss_pct"]].copy()
                chart_loss["Loss_SLA_1pct"] = config.sla.urllc_max_loss_pct
                st.line_chart(chart_loss.set_index("t"), color=["#7570b3", "#e41a1c"])

                st.markdown("#### 🔍 Pattern Anomaly Ratio & Request Rate")
                st.line_chart(df_hist[["t", "pattern_anomaly_ratio"]].set_index("t"), color=["#1b9e77"])
        else:
            st.info("Click **+10s** or **+50s** in the sidebar to run telemetry.")

        # 4. SAFETY PRE-CHECK & DECISION PANEL
        st.divider()
        st.subheader("🛡️ Safety Pre-Check & Explainability Log")
        
        p_col1, p_col2 = st.columns([1, 1])
        with p_col1:
            st.markdown("##### 🩺 Latest Causal Diagnosis")
            if latest_dec and latest_dec.diagnosis:
                diag = latest_dec.diagnosis
                st.write(f"**Diagnosed Cause:** `{diag.cause}`")
                st.write(f"**Confidence:** `{diag.confidence*100:.1f}%`")
                st.write("**Evaluated Evidence:**")
                for ev in diag.evidence_details[:4]:
                    icon = "✅" if ev.is_satisfied else "❌"
                    st.write(f"{icon} {ev.description} (Observed: `{ev.observed_value:.1f}`)")
            else:
                st.write("No active anomaly diagnosed.")

        with p_col2:
            st.markdown("##### 🔮 Digital Twin Pre-Check Audit")
            if latest_dec and latest_dec.twin_prediction:
                twin_p = latest_dec.twin_prediction
                st.write(f"**Tested Action:** `{twin_p.candidate_action.action}` ({twin_p.candidate_action.params})")
                st.write(f"**Predicted URLLC Latency:** `{twin_p.predicted_urllc_latency_ms:.2f} ms` (SLA: <=10ms)")
                st.write(f"**Predicted URLLC Loss:** `{twin_p.predicted_urllc_loss_pct:.2f} %` (SLA: <=1.0%)")
                st.write(f"**Pre-Check Result:** {'✅ PASSED (SAFE)' if twin_p.is_safe else '❌ REJECTED (UNSAFE)'}")
            else:
                st.write("Digital Twin Pre-Check idle.")

        if latest_dec:
            st.text_area("📝 Plain-Language Decision Explanation", value=latest_dec.explanation, height=110)

        # 5. RECENT DECISION LOG
        if ctrl.decision_log:
            with st.expander("📋 View Full Decision Log Table", expanded=False):
                log_data = []
                for d in ctrl.decision_log:
                    log_data.append({
                        "Tick": d.tick,
                        "Incident": d.is_incident,
                        "Diagnosis": d.diagnosis.cause if d.diagnosis else "none",
                        "Confidence": f"{d.diagnosis.confidence*100:.1f}%" if d.diagnosis else "-",
                        "Action": d.proposed_action.action,
                        "Params": str(d.proposed_action.params),
                        "Twin Predicted Lat": f"{d.twin_prediction.predicted_urllc_latency_ms:.1f}ms" if d.twin_prediction else "-",
                        "Applied": d.action_applied,
                        "Abstained": d.abstained,
                    })
                st.dataframe(pd.DataFrame(log_data).tail(20), use_container_width=True)

    with tab_bench:
        st.subheader("📊 Empirical Evaluation Results (30 Independent Seeds)")
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

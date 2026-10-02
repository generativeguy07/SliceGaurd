"""Evaluation runner for Phase 2: Anomaly Detection and Diagnosis Benchmarking.

Evaluates the Isolation Forest detector and rule-based diagnosis engine across all 8 scenarios.
Computes:
- Detection delay (ticks to first alarm after event start)
- False alarm rate (outside event window)
- Precision & Recall
- Diagnosis accuracy & confidence
- Abstention rate (specifically verifying flash crowd and unseen mMTC storm behaviors)
"""

from __future__ import annotations

from typing import Any, Dict, List
import numpy as np
import pandas as pd

from sliceguard.config import AppConfig, load_config
from sliceguard.detector import AnomalyDetector, train_default_detector
from sliceguard.diagnosis import DiagnosisEngine, DiagnosisResult
from sliceguard.scenarios import ScenarioRegistry
from sliceguard.simulator import KPIRow, generate_run


# Ground truth mapping to expected diagnosis causes
EXPECTED_DIAGNOSIS_MAP = {
    "normal": "normal_variation",
    "embb_surge": "cross_slice_contention",
    "ddos_like": "security_anomaly",
    "infra_bottleneck": "infrastructure_bottleneck",
    "flash_crowd": "traffic_overload",
    "overlapping": "cross_slice_contention",  # Primary contention
    "noisy_kpis": "cross_slice_contention",
    "unseen_mmtc_storm": "unknown",           # Must trigger unknown/abstention
}


def evaluate_phase2_performance(
    config: Optional[AppConfig] = None,
    seeds: Optional[List[int]] = None,
) -> pd.DataFrame:
    """Run Phase 2 evaluation across all scenarios and seeds.

    Args:
        config: Application configuration.
        seeds: List of random seeds for evaluation runs.

    Returns:
        pd.DataFrame summarizing metrics per scenario.
    """
    cfg = config if config is not None else load_config()
    eval_seeds = seeds if seeds is not None else [42, 43, 44, 45, 46]

    detector = train_default_detector(config=cfg)
    diagnosis_engine = DiagnosisEngine(cfg.diagnosis)

    results: List[Dict[str, Any]] = []

    event_start = cfg.time.event_start_tick
    event_end = event_start + cfg.time.event_duration_ticks

    for scenario_name in ScenarioRegistry.SUPPORTED_SCENARIOS:
        delays = []
        fars = []
        precisions = []
        recalls = []
        confidences = []
        abstention_rates = []
        correct_diagnoses = []
        diagnosed_causes_list = []

        for s in eval_seeds:
            df = generate_run(scenario_name=scenario_name, seed=s, config=cfg)
            scores, raw_flags, incident_flags = detector.score_df(df)

            is_event = (df["t"] >= event_start) & (df["t"] < event_end)
            if scenario_name == "normal":
                is_event = pd.Series(False, index=df.index)

            # False Alarm Rate (ticks outside event that flagged incident)
            non_event_mask = ~is_event
            non_event_count = non_event_mask.sum()
            fa_count = (incident_flags & non_event_mask).sum()
            far = fa_count / max(1, non_event_count)
            fars.append(far)

            # Precision & Recall
            if scenario_name == "normal":
                precision = 1.0 if incident_flags.sum() == 0 else 0.0
                recall = 1.0  # No events to recall
                delay = 0.0
            else:
                tp = (incident_flags & is_event).sum()
                fp = (incident_flags & ~is_event).sum()
                fn = (~incident_flags & is_event).sum()

                precision = tp / max(1, (tp + fp))
                recall = tp / max(1, (tp + fn))

                # Detection delay (first flag at or after event_start)
                event_flags = incident_flags[event_start:event_end]
                if event_flags.any():
                    first_flag_idx = np.argmax(event_flags)
                    delay = float(first_flag_idx)
                else:
                    delay = float(cfg.time.event_duration_ticks)  # Max delay if missed

                delays.append(delay)

            precisions.append(precision)
            recalls.append(recall)

            # Diagnosis evaluation during active event window (or mid-run for normal)
            diag_start = event_start + 40 if scenario_name != "normal" else 250
            diag_end = diag_start + 60
            window_rows = df.iloc[diag_start:diag_end].to_dict(orient="records")

            diag_res = diagnosis_engine.diagnose_window(window_rows, is_detector_incident=True)
            confidences.append(diag_res.confidence)
            abstention_rates.append(1.0 if diag_res.should_abstain else 0.0)
            diagnosed_causes_list.append(diag_res.cause)

            expected_cause = EXPECTED_DIAGNOSIS_MAP[scenario_name]
            if scenario_name == "unseen_mmtc_storm":
                # For unseen storm, success is defined as abstention / unknown cause
                is_correct = (diag_res.cause == "unknown" or diag_res.should_abstain)
            else:
                is_correct = (diag_res.cause == expected_cause)
            correct_diagnoses.append(1.0 if is_correct else 0.0)

        # Aggregate across seeds
        avg_delay = np.mean(delays) if delays else 0.0
        most_common_cause = max(set(diagnosed_causes_list), key=diagnosed_causes_list.count)

        results.append({
            "Scenario": scenario_name,
            "Expected Cause": EXPECTED_DIAGNOSIS_MAP[scenario_name],
            "Diagnosed Cause": most_common_cause,
            "Delay (s)": round(avg_delay, 1),
            "FAR (%)": round(np.mean(fars) * 100.0, 2),
            "Precision (%)": round(np.mean(precisions) * 100.0, 1),
            "Recall (%)": round(np.mean(recalls) * 100.0, 1),
            "Mean Conf (%)": round(np.mean(confidences) * 100.0, 1),
            "Abstain Rate (%)": round(np.mean(abstention_rates) * 100.0, 1),
            "Diag Accuracy (%)": round(np.mean(correct_diagnoses) * 100.0, 1),
        })

    summary_df = pd.DataFrame(results)
    return summary_df


if __name__ == "__main__":
    df_results = evaluate_phase2_performance()
    print("\n=================== PHASE 2 DETECTION & DIAGNOSIS BENCHMARK ===================")
    print(df_results.to_string(index=False))
    print("===============================================================================\n")

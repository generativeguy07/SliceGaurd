"""Rule-based root-cause diagnosis engine with confidence scoring and abstention.

Evaluates evidence across an observational telemetry window without reading ground-truth labels.
Supports candidate causes:
- normal_variation
- cross_slice_contention
- security_anomaly
- infrastructure_bottleneck
- traffic_overload (flash crowd)
- unknown (e.g. unseen mMTC storm)

Calculates confidence based on weighted evidence satisfaction and rule ambiguity penalties.
Abstains and recommends 'escalate_to_human' if confidence < threshold or cause is unknown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

from sliceguard.config import AppConfig, DiagnosisConfig, load_config
from sliceguard.simulator import KPIRow, Simulator


@dataclass
class EvidenceItem:
    """Individual telemetry evidence proposition."""
    description: str
    is_satisfied: bool
    weight: float
    observed_value: float
    threshold_value: float


@dataclass
class RuleScore:
    """Evaluation score for a specific candidate root cause."""
    cause: str
    score: float
    evidence: List[EvidenceItem]


@dataclass
class DiagnosisResult:
    """Structured output from the root-cause diagnosis engine."""
    cause: str
    confidence: float
    should_abstain: bool
    recommended_action: str
    top_scores: Dict[str, float]
    evidence_details: List[EvidenceItem]
    explanation_summary: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert diagnosis result to dictionary representation."""
        return {
            "cause": self.cause,
            "confidence": round(self.confidence, 3),
            "should_abstain": self.should_abstain,
            "recommended_action": self.recommended_action,
            "top_scores": {k: round(v, 3) for k, v in self.top_scores.items()},
            "explanation": self.explanation_summary,
        }


class DiagnosisEngine:
    """Rule-based causal diagnostic engine for 5G slice assurance."""

    CAUSES = [
        "normal_variation",
        "cross_slice_contention",
        "security_anomaly",
        "infrastructure_bottleneck",
        "traffic_overload",
        "unknown",
    ]

    def __init__(self, config: Optional[DiagnosisConfig] = None) -> None:
        """Initialize engine with diagnosis configuration."""
        self.config = config if config is not None else DiagnosisConfig()
        self.window_ticks = self.config.evidence_window_ticks
        self.abstain_threshold = self.config.abstain_confidence_threshold

    def diagnose_window(
        self,
        history: List[KPIRow | Dict[str, Any]],
        is_detector_incident: bool = False,
    ) -> DiagnosisResult:
        """Diagnose root cause from recent telemetry history window.

        Args:
            history: List of recent KPIRow or dictionary telemetry rows.
            is_detector_incident: Whether the anomaly detector flagged an incident.

        Returns:
            DiagnosisResult with diagnosed cause, confidence, and abstention status.
        """
        if not history:
            return DiagnosisResult(
                cause="normal_variation",
                confidence=1.0,
                should_abstain=False,
                recommended_action="no_action",
                top_scores={"normal_variation": 1.0},
                evidence_details=[],
                explanation_summary="No telemetry data available.",
            )

        # Take the most recent window of ticks
        recent = history[-self.window_ticks:]
        raw_dicts = []
        for r in recent:
            if hasattr(r, "to_observable_dict"):
                raw_dicts.append(r.to_observable_dict())
            elif hasattr(r, "items"):
                raw_dicts.append({k: v for k, v in r.items() if k not in Simulator.GROUND_TRUTH_COLUMNS})
            elif isinstance(r, dict):
                raw_dicts.append({k: v for k, v in r.items() if k not in Simulator.GROUND_TRUTH_COLUMNS})
            else:
                d = dict(r)
                raw_dicts.append({k: v for k, v in d.items() if k not in Simulator.GROUND_TRUTH_COLUMNS})

        df = pd.DataFrame(raw_dicts)

        # Compute window statistics
        mean_urllc_lat = float(df["urllc_latency_ms"].mean())
        mean_urllc_loss = float(df["urllc_loss_pct"].mean())
        mean_embb_served = float(df["embb_served_pct"].mean())
        mean_embb_demand = float(df["embb_demand_pct"].mean())
        mean_shared_util = float(df["shared_util_pct"].mean())
        mean_pattern_ratio = float(df["pattern_anomaly_ratio"].mean())
        mean_req_rate = float(df["req_rate_total"].mean())
        mean_cpu = float(df["cpu_pct"].mean())
        mean_reg_failures = float(df["mmtc_reg_failures"].mean())
        
        # Ramp rate estimation (difference over window)
        embb_ramp_rate = float(df["embb_demand_pct"].iloc[-1] - df["embb_demand_pct"].iloc[0]) / max(1, len(df))

        # Evaluate rules
        rule_evals: List[RuleScore] = []

        # 1. cross_slice_contention (Bandwidth surge causing buffer/queue congestion)
        ev_contention = [
            EvidenceItem("eMBB served load >= 45%", mean_embb_served >= 45.0, 1.0, mean_embb_served, 45.0),
            EvidenceItem("URLLC latency elevated (> 8ms)", mean_urllc_lat > 8.0, 1.0, mean_urllc_lat, 8.0),
            EvidenceItem("Shared utilization high (>= 60%)", mean_shared_util >= 60.0, 0.8, mean_shared_util, 60.0),
            EvidenceItem("Normal packet pattern ratio (< 0.20)", mean_pattern_ratio < 0.20, 1.0, mean_pattern_ratio, 0.20),
            EvidenceItem("Bandwidth-driven contention (req_rate < 2200 req/s)", mean_req_rate < 2200.0, 0.9, mean_req_rate, 2200.0),
        ]
        score_contention = sum(e.weight for e in ev_contention if e.is_satisfied) / sum(e.weight for e in ev_contention)
        rule_evals.append(RuleScore("cross_slice_contention", score_contention, ev_contention))

        # 2. security_anomaly (DDoS flood)
        ev_security = [
            EvidenceItem("Pattern anomaly ratio high (>= 0.60)", mean_pattern_ratio >= 0.60, 1.2, mean_pattern_ratio, 0.60),
            EvidenceItem("Request rate flood (>= 3500 req/s)", mean_req_rate >= 3500.0, 1.0, mean_req_rate, 3500.0),
            EvidenceItem("CPU utilization high (>= 70%)", mean_cpu >= 70.0, 0.8, mean_cpu, 70.0),
            EvidenceItem("eMBB demand elevated (>= 50%)", mean_embb_demand >= 50.0, 0.6, mean_embb_demand, 50.0),
        ]
        score_security = sum(e.weight for e in ev_security if e.is_satisfied) / sum(e.weight for e in ev_security)
        rule_evals.append(RuleScore("security_anomaly", score_security, ev_security))

        # 3. infrastructure_bottleneck (Capacity drop / fault)
        ev_infra = [
            EvidenceItem("URLLC latency/loss degraded (lat > 8ms or loss > 0.5%)", (mean_urllc_lat > 8.0 or mean_urllc_loss > 0.5), 1.0, mean_urllc_lat, 8.0),
            EvidenceItem("eMBB throughput throttled (< 45% served)", mean_embb_served < 45.0, 1.0, mean_embb_served, 45.0),
            EvidenceItem("Shared utilization high despite lower throughput (>= 65%)", mean_shared_util >= 65.0, 0.8, mean_shared_util, 65.0),
            EvidenceItem("Normal packet pattern (< 0.15)", mean_pattern_ratio < 0.15, 1.0, mean_pattern_ratio, 0.15),
            EvidenceItem("Request rate normal (< 2000 req/s)", mean_req_rate < 2000.0, 0.8, mean_req_rate, 2000.0),
        ]
        score_infra = sum(e.weight for e in ev_infra if e.is_satisfied) / sum(e.weight for e in ev_infra)
        rule_evals.append(RuleScore("infrastructure_bottleneck", score_infra, ev_infra))

        # 4. traffic_overload (Flash crowd / organic mass user traffic)
        ev_overload = [
            EvidenceItem("eMBB demand elevated (>= 50%)", mean_embb_demand >= 50.0, 1.0, mean_embb_demand, 50.0),
            EvidenceItem("Pattern anomaly ratio strictly normal (< 0.15)", mean_pattern_ratio < 0.15, 1.2, mean_pattern_ratio, 0.15),
            EvidenceItem("Organic user flood (req_rate >= 2200 req/s)", mean_req_rate >= 2200.0, 1.0, mean_req_rate, 2200.0),
            EvidenceItem("CPU load moderate to high (< 85%)", mean_cpu < 85.0, 0.6, mean_cpu, 85.0),
        ]
        score_overload = sum(e.weight for e in ev_overload if e.is_satisfied) / sum(e.weight for e in ev_overload)
        rule_evals.append(RuleScore("traffic_overload", score_overload, ev_overload))

        # 5. normal_variation
        ev_normal = [
            EvidenceItem("URLLC latency within SLA (<= 8.0ms)", mean_urllc_lat <= 8.0, 1.0, mean_urllc_lat, 8.0),
            EvidenceItem("Pattern anomaly ratio normal (< 0.10)", mean_pattern_ratio < 0.10, 1.0, mean_pattern_ratio, 0.10),
            EvidenceItem("Request rate normal (< 1500 req/s)", mean_req_rate < 1500.0, 0.8, mean_req_rate, 1500.0),
            EvidenceItem("mMTC registration failures low (< 10)", mean_reg_failures < 10.0, 0.8, mean_reg_failures, 10.0),
        ]
        score_normal = sum(e.weight for e in ev_normal if e.is_satisfied) / sum(e.weight for e in ev_normal)
        rule_evals.append(RuleScore("normal_variation", score_normal, ev_normal))

        # Check for unseen/unmodeled anomaly (e.g. mMTC registration storm)
        if mean_reg_failures > 50.0 or (is_detector_incident and all(r.score < 0.50 for r in rule_evals if r.cause != "normal_variation")):
            ev_unknown = [
                EvidenceItem(f"Unmodeled telemetry anomaly detected (reg_failures={mean_reg_failures:.1f})", True, 1.0, mean_reg_failures, 50.0)
            ]
            rule_evals.append(RuleScore("unknown", 0.95, ev_unknown))

        # Sort rules by score descending
        rule_evals.sort(key=lambda r: r.score, reverse=True)
        best_rule = rule_evals[0]
        second_best_score = rule_evals[1].score if len(rule_evals) > 1 else 0.0

        # Calculate confidence with ambiguity penalty
        raw_conf = best_rule.score
        margin = max(0.0, best_rule.score - second_best_score)
        
        # If the gap between top 2 rules is narrow (< 0.20), scale down confidence
        if margin < 0.20 and best_rule.cause != "normal_variation" and best_rule.cause != "unknown":
            confidence = raw_conf * (0.75 + 0.25 * (margin / 0.20))
        else:
            confidence = raw_conf

        # Default action mapping per diagnosed cause
        cause_action_map = {
            "normal_variation": "no_action",
            "cross_slice_contention": "protect_urllc",
            "security_anomaly": "isolate_suspicious_traffic",
            "infrastructure_bottleneck": "scale_up_resource",
            "traffic_overload": "rate_limit_embb",
            "unknown": "escalate_to_human",
        }

        # Abstention decision
        should_abstain = False
        final_cause = best_rule.cause

        if final_cause == "unknown" or confidence < self.abstain_threshold:
            should_abstain = True
            recommended_action = "escalate_to_human"
        else:
            recommended_action = cause_action_map.get(final_cause, "no_action")

        top_scores_dict = {r.cause: r.score for r in rule_evals}

        # Build readable explanation summary
        if should_abstain:
            if final_cause == "unknown":
                explanation = f"Abstained: Unrecognized anomaly signature detected (mMTC failure surge/unmodeled state). Escalating to human operator."
            else:
                explanation = f"Abstained: Diagnosis ambiguity ({final_cause} score {confidence:.2f} < threshold {self.abstain_threshold:.2f}). Escalating to human operator."
        else:
            explanation = f"Diagnosed {final_cause} with {confidence*100:.1f}% confidence. Recommended action: {recommended_action}."

        return DiagnosisResult(
            cause=final_cause,
            confidence=confidence,
            should_abstain=should_abstain,
            recommended_action=recommended_action,
            top_scores=top_scores_dict,
            evidence_details=best_rule.evidence,
            explanation_summary=explanation,
        )

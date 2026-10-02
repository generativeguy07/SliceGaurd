"""Template-based natural language explanations for assurance decisions.

Builds deterministic, auditable explanations from structured decision objects.
Explains:
- Diagnosed root cause and confidence
- Evaluated evidence propositions
- Policy validator outcome
- Digital twin prediction outcome (predicted URLLC latency & packet loss)
- Final decision execution (applied, rejected, or abstained)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sliceguard.actions import Action
from sliceguard.diagnosis import DiagnosisResult
from sliceguard.twin import TwinPrediction
from sliceguard.validator import ValidationResult


@dataclass
class ControllerDecision:
    """Full decision record produced by an assurance controller at a single tick."""
    tick: int
    scenario: str
    is_incident: bool
    diagnosis: Optional[DiagnosisResult]
    proposed_action: Action
    validation: Optional[ValidationResult]
    twin_prediction: Optional[TwinPrediction]
    action_applied: bool
    abstained: bool
    cooldown_remaining: int
    explanation: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert decision record to dictionary."""
        return {
            "tick": self.tick,
            "scenario": self.scenario,
            "is_incident": self.is_incident,
            "diagnosis": self.diagnosis.to_dict() if self.diagnosis else None,
            "action": self.proposed_action.to_dict(),
            "validation": self.validation.to_dict() if self.validation else None,
            "twin_prediction": self.twin_prediction.to_dict() if self.twin_prediction else None,
            "action_applied": self.action_applied,
            "abstained": self.abstained,
            "cooldown_remaining": self.cooldown_remaining,
            "explanation": self.explanation,
        }


class DecisionExplainer:
    """Generates clear, deterministic natural language explanations for assurance events."""

    @staticmethod
    def explain(
        decision: ControllerDecision,
    ) -> str:
        """Construct structured explanation text from a ControllerDecision."""
        if not decision.is_incident:
            return f"Tick {decision.tick}: Telemetry indicates normal network operation within SLA targets. No action required."

        lines = [f"[Tick {decision.tick}] Assurance Decision Summary:"]

        # Diagnosis details
        diag = decision.diagnosis
        if diag:
            conf_pct = diag.confidence * 100.0
            lines.append(f"  • Diagnosis: {diag.cause} (Confidence: {conf_pct:.1f}%)")
            satisfied_ev = [e.description for e in diag.evidence_details if e.is_satisfied]
            if satisfied_ev:
                lines.append(f"    Evidence: {', '.join(satisfied_ev[:3])}")

        # Abstention check
        if decision.abstained:
            lines.append(f"  • Decision: ABSTAINED & ESCALATED TO HUMAN OPERATOR.")
            lines.append(f"    Reason: Diagnosis confidence below safety threshold or unmodeled anomaly signature.")
            return "\n".join(lines)

        # Policy validation
        val = decision.validation
        if val:
            if val.is_valid:
                lines.append(f"  • Policy Validator: PASSED (Action '{decision.proposed_action.action}' complies with hard slice limits).")
            else:
                lines.append(f"  • Policy Validator: REJECTED with violations: {'; '.join(val.violations)}")

        # Digital Twin Pre-check
        twin = decision.twin_prediction
        if twin:
            lines.append(
                f"  • Digital Twin Pre-Check: Predicted URLLC Latency = {twin.predicted_urllc_latency_ms:.1f}ms, "
                f"Loss = {twin.predicted_urllc_loss_pct:.2f}% (SLA Safe: {twin.is_safe})"
            )

        # Final outcome
        if decision.action_applied:
            lines.append(f"  • Action Status: APPLIED '{decision.proposed_action.action}' (Parameters: {decision.proposed_action.params}).")
        else:
            lines.append(f"  • Action Status: WITHHELD (Cooldown active or pre-check failed).")

        return "\n".join(lines)


def rephrase_with_llm_stub(
    template_explanation: str,
    enable_llm: bool = False,
) -> str:
    """Optional utility to rephrase explanation text with an LLM.

    Strictly disabled by default. When disabled or in standard simulation runs,
    returns the exact deterministic template explanation without modification.
    """
    if not enable_llm:
        return template_explanation

    # Optional local rephrasing placeholder
    return f"[LLM Rephrased] {template_explanation}"

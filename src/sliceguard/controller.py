"""Autonomous assurance controllers B1 through B4 for 5G network slices.

Implements the four benchmark controllers from SPEC section 8:
- B1 (no_action): Passive baseline, applies no mitigations.
- B2 (static_threshold): Reactive rule; shifts fixed +10% to URLLC if latency > 10ms.
- B3 (detector_rules): Anomaly detector + rule-based diagnosis + validator. (No twin, no abstention).
- B4 (full): Complete safety loop (Detector + Diagnosis + Abstention + Validator + Digital Twin Pre-Check).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from sliceguard.actions import Action, get_candidate_actions_for_cause
from sliceguard.config import AppConfig, load_config
from sliceguard.detector import AnomalyDetector, train_default_detector
from sliceguard.diagnosis import DiagnosisEngine, DiagnosisResult
from sliceguard.explain import ControllerDecision, DecisionExplainer
from sliceguard.simulator import KPIRow, Simulator
from sliceguard.twin import DigitalTwin, TwinPrediction, train_default_digital_twin
from sliceguard.validator import PolicyValidator, ValidationResult


class BaseController(ABC):
    """Abstract base class for all assurance controllers."""

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        """Initialize controller with configuration."""
        self.config = config if config is not None else load_config()
        self.cooldown_ticks = self.config.controller.cooldown_ticks
        self.cooldown_counter = 0
        self.decision_log: List[ControllerDecision] = []
        self.latest_decision: Optional[ControllerDecision] = None

    def reset(self) -> None:
        """Reset internal controller state and decision history."""
        self.cooldown_counter = 0
        self.decision_log.clear()
        self.latest_decision = None

    @abstractmethod
    def decide(self, history: List[KPIRow]) -> Action:
        """Analyze telemetry history and return the chosen action for the current tick."""
        pass


class B1NoActionController(BaseController):
    """B1: Baseline that takes no corrective actions."""

    def decide(self, history: List[KPIRow]) -> Action:
        """Always return no_action."""
        tick = history[-1].t if history else 0
        scen = history[-1].scenario if history else "unknown"
        action = Action(action="no_action", reason="B1 baseline takes no action")

        decision = ControllerDecision(
            tick=tick,
            scenario=scen,
            is_incident=False,
            diagnosis=None,
            proposed_action=action,
            validation=None,
            twin_prediction=None,
            action_applied=False,
            abstained=False,
            cooldown_remaining=0,
            explanation="B1 baseline: no mitigation attempted.",
        )
        self.latest_decision = decision
        self.decision_log.append(decision)
        return action


class B2StaticThresholdController(BaseController):
    """B2: Reactive threshold controller without ML detector or digital twin."""

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        """Initialize B2 controller with policy validator."""
        super().__init__(config)
        self.validator = PolicyValidator(self.config)

    def decide(self, history: List[KPIRow]) -> Action:
        """Trigger static +10 shift to URLLC whenever current URLLC latency breaches 10ms SLA."""
        if not history:
            return Action(action="no_action")

        latest = history[-1]
        tick = latest.t
        scen = latest.scenario

        if self.cooldown_counter > 0:
            self.cooldown_counter -= 1

        curr_allocs = {
            "embb": latest.alloc_embb,
            "urllc": latest.alloc_urllc,
            "mmtc": latest.alloc_mmtc,
        }

        # Check raw SLA breach
        is_breaching = (latest.urllc_latency_ms > self.config.sla.urllc_max_latency_ms)

        if is_breaching and self.cooldown_counter == 0:
            candidate = Action(
                action="protect_urllc",
                params={"shift_pct": 10.0},
                reason="Static threshold breached (latency > 10ms); shifting +10% to URLLC",
                cause="sla_threshold_breach",
            )
            val_res = self.validator.validate(candidate, curr_allocs)

            if val_res.is_valid:
                self.cooldown_counter = self.cooldown_ticks
                decision = ControllerDecision(
                    tick=tick,
                    scenario=scen,
                    is_incident=True,
                    diagnosis=None,
                    proposed_action=candidate,
                    validation=val_res,
                    twin_prediction=None,
                    action_applied=True,
                    abstained=False,
                    cooldown_remaining=self.cooldown_counter,
                    explanation=f"B2 Static Threshold: SLA breach detected ({latest.urllc_latency_ms:.1f}ms). Applied protect_urllc (+10%).",
                )
                self.latest_decision = decision
                self.decision_log.append(decision)
                return candidate
            else:
                decision = ControllerDecision(
                    tick=tick,
                    scenario=scen,
                    is_incident=True,
                    diagnosis=None,
                    proposed_action=candidate,
                    validation=val_res,
                    twin_prediction=None,
                    action_applied=False,
                    abstained=False,
                    cooldown_remaining=0,
                    explanation=f"B2 Static Threshold: Proposed action rejected by policy: {val_res.violations}",
                )
                self.latest_decision = decision
                self.decision_log.append(decision)
                return Action(action="no_action")

        action = Action(action="no_action")
        decision = ControllerDecision(
            tick=tick,
            scenario=scen,
            is_incident=is_breaching,
            diagnosis=None,
            proposed_action=action,
            validation=None,
            twin_prediction=None,
            action_applied=False,
            abstained=False,
            cooldown_remaining=self.cooldown_counter,
            explanation="B2 Static Threshold: Normal or cooldown active.",
        )
        self.latest_decision = decision
        self.decision_log.append(decision)
        return action


class B3DetectorRulesController(BaseController):
    """B3: Detector + Diagnosis + Validator (without digital-twin pre-check and without abstention)."""

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        detector: Optional[AnomalyDetector] = None,
    ) -> None:
        """Initialize B3 controller."""
        super().__init__(config)
        self.detector = detector if detector is not None else train_default_detector(self.config)
        self.diagnosis_engine = DiagnosisEngine(self.config.diagnosis)
        self.validator = PolicyValidator(self.config)

    def reset(self) -> None:
        """Reset controller and internal detector filter."""
        super().reset()
        self.detector.reset_filter()

    def decide(self, history: List[KPIRow]) -> Action:
        """Decide action using detector and diagnosis without abstention or twin pre-check."""
        if not history:
            return Action(action="no_action")

        latest = history[-1]
        tick = latest.t
        scen = latest.scenario

        if self.cooldown_counter > 0:
            self.cooldown_counter -= 1

        curr_allocs = {
            "embb": latest.alloc_embb,
            "urllc": latest.alloc_urllc,
            "mmtc": latest.alloc_mmtc,
        }

        is_raw_anom, is_incident, score = self.detector.predict_step(history)

        if is_incident and self.cooldown_counter == 0:
            # Diagnose root cause
            diag_res = self.diagnosis_engine.diagnose_window(history, is_detector_incident=True)
            
            # B3 does NOT abstain; it always takes the default candidate action
            candidates = get_candidate_actions_for_cause(diag_res.cause)
            chosen_candidate = candidates[0] if candidates else Action("no_action")

            if chosen_candidate.action == "no_action" or chosen_candidate.action == "escalate_to_human":
                action = Action("no_action")
                decision = ControllerDecision(
                    tick=tick,
                    scenario=scen,
                    is_incident=True,
                    diagnosis=diag_res,
                    proposed_action=action,
                    validation=None,
                    twin_prediction=None,
                    action_applied=False,
                    abstained=False,
                    cooldown_remaining=0,
                    explanation=f"B3 Controller: Diagnosed {diag_res.cause}. No valid mitigation taken.",
                )
                self.latest_decision = decision
                self.decision_log.append(decision)
                return action

            val_res = self.validator.validate(chosen_candidate, curr_allocs)
            if val_res.is_valid:
                self.cooldown_counter = self.cooldown_ticks
                decision = ControllerDecision(
                    tick=tick,
                    scenario=scen,
                    is_incident=True,
                    diagnosis=diag_res,
                    proposed_action=chosen_candidate,
                    validation=val_res,
                    twin_prediction=None,
                    action_applied=True,
                    abstained=False,
                    cooldown_remaining=self.cooldown_counter,
                    explanation=f"B3 Controller: Applied '{chosen_candidate.action}' for {diag_res.cause} without twin pre-check.",
                )
                self.latest_decision = decision
                self.decision_log.append(decision)
                return chosen_candidate
            else:
                decision = ControllerDecision(
                    tick=tick,
                    scenario=scen,
                    is_incident=True,
                    diagnosis=diag_res,
                    proposed_action=chosen_candidate,
                    validation=val_res,
                    twin_prediction=None,
                    action_applied=False,
                    abstained=False,
                    cooldown_remaining=0,
                    explanation=f"B3 Controller: Action rejected by policy: {val_res.violations}",
                )
                self.latest_decision = decision
                self.decision_log.append(decision)
                return Action("no_action")

        action = Action(action="no_action")
        decision = ControllerDecision(
            tick=tick,
            scenario=scen,
            is_incident=is_incident,
            diagnosis=None,
            proposed_action=action,
            validation=None,
            twin_prediction=None,
            action_applied=False,
            abstained=False,
            cooldown_remaining=self.cooldown_counter,
            explanation="B3 Controller: Monitoring or cooldown active.",
        )
        self.latest_decision = decision
        self.decision_log.append(decision)
        return action


class B4FullAssuranceController(BaseController):
    """B4: Full Safety-First Assurance Controller.

    Integrates:
    - AnomalyDetector (Isolation Forest + persistence filter)
    - DiagnosisEngine (explainable rules + confidence scoring)
    - Confidence-based Abstention (safe fallback to human on low confidence / unknown)
    - PolicyValidator (strict hard bounds on slice allocations)
    - Digital-Twin Pre-Check (simulates candidate actions from smallest to largest step)
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        detector: Optional[AnomalyDetector] = None,
        twin: Optional[DigitalTwin] = None,
    ) -> None:
        """Initialize B4 controller with all safety loop components."""
        super().__init__(config)
        self.detector = detector if detector is not None else train_default_detector(self.config)
        self.twin = twin if twin is not None else train_default_digital_twin(self.config)
        self.diagnosis_engine = DiagnosisEngine(self.config.diagnosis)
        self.validator = PolicyValidator(self.config)

    def reset(self) -> None:
        """Reset controller state and detector filter."""
        super().reset()
        self.detector.reset_filter()

    def decide(self, history: List[KPIRow]) -> Action:
        """Execute full safety loop: detect -> diagnose -> abstain? -> validate -> precheck -> act."""
        if not history:
            return Action(action="no_action")

        latest = history[-1]
        tick = latest.t
        scen = latest.scenario

        if self.cooldown_counter > 0:
            self.cooldown_counter -= 1

        curr_allocs = {
            "embb": latest.alloc_embb,
            "urllc": latest.alloc_urllc,
            "mmtc": latest.alloc_mmtc,
        }
        current_state = {
            "urllc_latency_ms": latest.urllc_latency_ms,
            "urllc_loss_pct": latest.urllc_loss_pct,
            "embb_served_pct": latest.embb_served_pct,
            "embb_demand_pct": latest.embb_demand_pct,
            "shared_util_pct": latest.shared_util_pct,
            "alloc_urllc": latest.alloc_urllc,
            "alloc_embb": latest.alloc_embb,
        }

        # 1. Anomaly Detection
        is_raw_anom, is_incident, score = self.detector.predict_step(history)

        if not is_incident or self.cooldown_counter > 0:
            action = Action(action="no_action")
            decision = ControllerDecision(
                tick=tick,
                scenario=scen,
                is_incident=is_incident,
                diagnosis=None,
                proposed_action=action,
                validation=None,
                twin_prediction=None,
                action_applied=False,
                abstained=False,
                cooldown_remaining=self.cooldown_counter,
                explanation="Normal telemetry or cooldown in progress.",
            )
            self.latest_decision = decision
            self.decision_log.append(decision)
            return action

        # 2. Causal Diagnosis
        diag_res = self.diagnosis_engine.diagnose_window(history, is_detector_incident=True)

        # 3. Confidence-Based Abstention Check
        if diag_res.should_abstain or diag_res.cause == "unknown":
            escalate_action = Action(
                action="escalate_to_human",
                reason=diag_res.explanation_summary,
                cause=diag_res.cause,
                confidence=diag_res.confidence,
            )
            decision = ControllerDecision(
                tick=tick,
                scenario=scen,
                is_incident=True,
                diagnosis=diag_res,
                proposed_action=escalate_action,
                validation=None,
                twin_prediction=None,
                action_applied=False,
                abstained=True,
                cooldown_remaining=self.cooldown_ticks,
                explanation=DecisionExplainer.explain(
                    ControllerDecision(
                        tick=tick, scenario=scen, is_incident=True, diagnosis=diag_res,
                        proposed_action=escalate_action, validation=None, twin_prediction=None,
                        action_applied=False, abstained=True, cooldown_remaining=0, explanation=""
                    )
                ),
            )
            self.cooldown_counter = self.cooldown_ticks
            self.latest_decision = decision
            self.decision_log.append(decision)
            return escalate_action

        # 4. Candidate Action Pre-checking Loop (Smallest to Largest Step)
        candidate_actions = get_candidate_actions_for_cause(diag_res.cause)
        selected_action: Optional[Action] = None
        selected_val_res: Optional[ValidationResult] = None
        selected_twin_pred: Optional[TwinPrediction] = None

        for candidate in candidate_actions:
            candidate.confidence = diag_res.confidence
            candidate.cause = diag_res.cause

            # (a) Policy Validation
            val_res = self.validator.validate(candidate, curr_allocs)
            if not val_res.is_valid:
                continue

            # (b) Digital Twin Pre-Check
            twin_pred = self.twin.predict(
                current_state=current_state,
                target_allocations=val_res.target_allocations,
                action=candidate,
                sla_max_latency_ms=self.config.sla.urllc_max_latency_ms,
                sla_max_loss_pct=self.config.sla.urllc_max_loss_pct,
                embb_min_alloc_pct=self.config.slices.embb.min_pct,
            )

            if twin_pred.is_safe:
                selected_action = candidate
                selected_val_res = val_res
                selected_twin_pred = twin_pred
                break

        # 5. Apply or Escalate
        if selected_action is not None:
            self.cooldown_counter = self.cooldown_ticks
            decision = ControllerDecision(
                tick=tick,
                scenario=scen,
                is_incident=True,
                diagnosis=diag_res,
                proposed_action=selected_action,
                validation=selected_val_res,
                twin_prediction=selected_twin_pred,
                action_applied=True,
                abstained=False,
                cooldown_remaining=self.cooldown_counter,
                explanation="",
            )
            decision.explanation = DecisionExplainer.explain(decision)
            self.latest_decision = decision
            self.decision_log.append(decision)
            return selected_action

        # If no candidate action passed policy & twin pre-check: Escalate
        fallback_action = Action(
            action="escalate_to_human",
            reason="All candidate actions failed pre-check SLA criteria; safety escalation",
            cause=diag_res.cause,
            confidence=diag_res.confidence,
        )
        decision = ControllerDecision(
            tick=tick,
            scenario=scen,
            is_incident=True,
            diagnosis=diag_res,
            proposed_action=fallback_action,
            validation=None,
            twin_prediction=None,
            action_applied=False,
            abstained=True,
            cooldown_remaining=self.cooldown_ticks,
            explanation=f"Tick {tick}: All candidate actions rejected by digital twin pre-check. Escalating to human.",
        )
        self.cooldown_counter = self.cooldown_ticks
        self.latest_decision = decision
        self.decision_log.append(decision)
        return fallback_action

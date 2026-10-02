"""Action menu schema, dataclasses, and candidate action generators.

Defines the fixed, structured action menu for SliceGuard-Lite:
- protect_urllc: shift allocation percentage from eMBB to URLLC
- rate_limit_embb: apply bandwidth throttling percentage to eMBB
- isolate_suspicious_traffic: remove attack traffic fraction from affected slice
- scale_up_resource: boost capacity factor
- escalate_to_human: safety abstention fallback
- no_action: maintain current network state

Actions are JSON-serializable, strictly typed, and rejected if not in the menu.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import Any, Dict, List, Optional


VALID_ACTION_NAMES = [
    "protect_urllc",
    "rate_limit_embb",
    "isolate_suspicious_traffic",
    "scale_up_resource",
    "escalate_to_human",
    "no_action",
]


@dataclass
class Action:
    """Structured, JSON-serializable network assurance action."""
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    cause: str = "unknown"
    confidence: float = 0.0

    def __post_init__(self) -> None:
        """Ensure action name is from the approved menu."""
        if self.action not in VALID_ACTION_NAMES:
            raise ValueError(
                f"Action '{self.action}' is not in the approved action menu: {VALID_ACTION_NAMES}"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert action to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert action to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Action:
        """Create Action instance from dictionary."""
        return cls(
            action=data.get("action", "no_action"),
            params=data.get("params", {}) or {},
            reason=data.get("reason", ""),
            cause=data.get("cause", "unknown"),
            confidence=float(data.get("confidence", 0.0)),
        )

    @classmethod
    def from_json(cls, json_str: str) -> Action:
        """Create Action instance from JSON string."""
        return cls.from_dict(json.loads(json_str))


def get_candidate_actions_for_cause(cause: str) -> List[Action]:
    """Generate ordered candidate actions (smallest to largest step) for a diagnosed cause.

    Args:
        cause: Diagnosed root cause string.

    Returns:
        List of Action candidates to be evaluated by validator and digital twin.
    """
    if cause == "cross_slice_contention":
        return [
            Action(
                action="protect_urllc",
                params={"shift_pct": 5.0},
                reason="Candidate +5% capacity shift to URLLC",
                cause=cause,
            ),
            Action(
                action="protect_urllc",
                params={"shift_pct": 10.0},
                reason="Candidate +10% capacity shift to URLLC",
                cause=cause,
            ),
            Action(
                action="protect_urllc",
                params={"shift_pct": 15.0},
                reason="Candidate +15% capacity shift to URLLC",
                cause=cause,
            ),
        ]
    elif cause == "security_anomaly":
        return [
            Action(
                action="isolate_suspicious_traffic",
                params={"isolate_pct": 75.0},
                reason="Moderate suspicious traffic filtering (75%)",
                cause=cause,
            ),
            Action(
                action="isolate_suspicious_traffic",
                params={"isolate_pct": 90.0},
                reason="Aggressive suspicious traffic filtering (90%)",
                cause=cause,
            ),
        ]
    elif cause == "infrastructure_bottleneck":
        return [
            Action(
                action="scale_up_resource",
                params={"boost_pct": 15.0},
                reason="Elastic capacity boost +15%",
                cause=cause,
            ),
            Action(
                action="scale_up_resource",
                params={"boost_pct": 25.0},
                reason="Elastic capacity boost +25%",
                cause=cause,
            ),
        ]
    elif cause == "traffic_overload":
        return [
            Action(
                action="rate_limit_embb",
                params={"rate_limit_pct": 15.0},
                reason="Mild eMBB rate limit (15%) to relieve congestion",
                cause=cause,
            ),
            Action(
                action="rate_limit_embb",
                params={"rate_limit_pct": 30.0},
                reason="Moderate eMBB rate limit (30%) to relieve congestion",
                cause=cause,
            ),
        ]
    elif cause == "unknown":
        return [
            Action(
                action="escalate_to_human",
                params={},
                reason="Unrecognized incident pattern; safety abstention",
                cause=cause,
            )
        ]
    else:
        return [
            Action(
                action="no_action",
                params={},
                reason="Normal conditions; no mitigation required",
                cause=cause,
            )
        ]

"""Hard policy validator for network slice reallocations and control actions.

Enforces operator-defined safety constraints:
- Action must be in the approved menu
- Parameter values within bounded operating ranges
- Allocation sum must equal exactly 100.0%
- URLLC slice bounded within [25%, 50%]
- eMBB slice minimum >= 20%
- mMTC slice minimum >= 10%
- Maximum allocation change per single action <= 15%

Crucially, the validator evaluates all rules and returns ALL violated constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sliceguard.actions import Action, VALID_ACTION_NAMES
from sliceguard.config import AppConfig, ValidatorConfig, load_config


@dataclass
class ValidationResult:
    """Outcome of validating a candidate action against policy rules."""
    is_valid: bool
    violations: List[str]
    target_allocations: Dict[str, float]
    action: Action

    def to_dict(self) -> Dict[str, Any]:
        """Convert validation result to dictionary."""
        return {
            "is_valid": self.is_valid,
            "violations": self.violations,
            "target_allocations": self.target_allocations,
            "action": self.action.to_dict(),
        }


class PolicyValidator:
    """Evaluates proposed actions against strict deterministic policy invariants."""

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        """Initialize validator with application configuration."""
        self.config = config if config is not None else load_config()
        self.val_cfg = self.config.validator
        self.slice_cfg = self.config.slices

    def validate(
        self,
        action: Action | Dict[str, Any],
        current_allocations: Optional[Dict[str, float]] = None,
    ) -> ValidationResult:
        """Validate proposed action against all safety rules and compute target allocations.

        Args:
            action: Action object or dictionary to validate.
            current_allocations: Current slice allocations dict {'embb': float, 'urllc': float, 'mmtc': float}.

        Returns:
            ValidationResult with boolean validity and list of all violation messages.
        """
        violations: List[str] = []

        if isinstance(action, dict):
            try:
                act = Action.from_dict(action)
            except Exception as e:
                return ValidationResult(
                    is_valid=False,
                    violations=[f"Action schema invalid: {str(e)}"],
                    target_allocations=current_allocations or {},
                    action=Action(action="no_action"),
                )
        else:
            act = action

        # Current state fallback
        curr_alloc = {
            "embb": float(self.slice_cfg.embb.alloc_pct),
            "urllc": float(self.slice_cfg.urllc.alloc_pct),
            "mmtc": float(self.slice_cfg.mmtc.alloc_pct),
        }
        if current_allocations:
            curr_alloc.update(current_allocations)

        target_alloc = dict(curr_alloc)

        # 1. Action Name Verification
        if act.action not in VALID_ACTION_NAMES:
            violations.append(
                f"Action '{act.action}' is not in the approved action menu: {VALID_ACTION_NAMES}"
            )

        # 2. Action Parameters Range Verification
        params = act.params or {}

        if act.action == "protect_urllc":
            shift = float(params.get("shift_pct", 0.0))
            if shift <= 0.0 or shift > self.val_cfg.max_change_per_action_pct:
                violations.append(
                    f"protect_urllc shift_pct ({shift}) exceeds allowed bounds (0 < shift <= {self.val_cfg.max_change_per_action_pct})"
                )

            # Compute proposed target allocation
            target_alloc["urllc"] = round(curr_alloc["urllc"] + shift, 2)
            target_alloc["embb"] = round(curr_alloc["embb"] - shift, 2)

        elif act.action == "rate_limit_embb":
            rate_limit = float(params.get("rate_limit_pct", 0.0))
            if rate_limit < 5.0 or rate_limit > 80.0:
                violations.append(
                    f"rate_limit_embb rate_limit_pct ({rate_limit}) must be between 5.0% and 80.0%"
                )

        elif act.action == "isolate_suspicious_traffic":
            isolate_pct = float(params.get("isolate_pct", 0.0))
            if isolate_pct < 10.0 or isolate_pct > 95.0:
                violations.append(
                    f"isolate_suspicious_traffic isolate_pct ({isolate_pct}) must be between 10.0% and 95.0%"
                )

        elif act.action == "scale_up_resource":
            boost_pct = float(params.get("boost_pct", 0.0))
            if boost_pct < 5.0 or boost_pct > 30.0:
                violations.append(
                    f"scale_up_resource boost_pct ({boost_pct}) must be between 5.0% and 30.0%"
                )

        # 3. Allocation Limits & Total Sum Invariants
        total_alloc = round(sum(target_alloc.values()), 2)
        if total_alloc != 100.0:
            violations.append(
                f"Total allocation sum ({total_alloc}%) must equal exactly 100.0%"
            )

        # URLLC Bounds [25, 50]
        urllc_min = self.slice_cfg.urllc.min_pct
        urllc_max = self.slice_cfg.urllc.max_pct or 50.0
        if target_alloc["urllc"] < urllc_min or target_alloc["urllc"] > urllc_max:
            violations.append(
                f"URLLC allocation ({target_alloc['urllc']}%) outside allowed bounds [{urllc_min}%, {urllc_max}%]"
            )

        # eMBB Minimum Limit >= 20
        embb_min = self.slice_cfg.embb.min_pct
        if target_alloc["embb"] < embb_min:
            violations.append(
                f"eMBB allocation ({target_alloc['embb']}%) falls below minimum guaranteed floor ({embb_min}%)"
            )

        # mMTC Minimum Limit >= 10
        mmtc_min = self.slice_cfg.mmtc.min_pct
        if target_alloc["mmtc"] < mmtc_min:
            violations.append(
                f"mMTC allocation ({target_alloc['mmtc']}%) falls below minimum guaranteed floor ({mmtc_min}%)"
            )

        # Maximum Delta Change per Action
        for slice_name in ["embb", "urllc", "mmtc"]:
            delta = abs(target_alloc[slice_name] - curr_alloc[slice_name])
            if delta > self.val_cfg.max_change_per_action_pct:
                violations.append(
                    f"Allocation delta for {slice_name} ({delta}%) exceeds maximum step limit ({self.val_cfg.max_change_per_action_pct}%)"
                )

        is_valid = (len(violations) == 0)
        return ValidationResult(
            is_valid=is_valid,
            violations=violations,
            target_allocations=target_alloc,
            action=act,
        )

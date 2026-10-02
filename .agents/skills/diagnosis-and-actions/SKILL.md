---
name: diagnosis-and-actions
description: Use when implementing rule-based root-cause diagnosis with confidence, the fixed action menu, the policy validator or abstention for SliceGuard-Lite.
---

# Diagnosis, actions and validator

## Use this skill when
Working on `diagnosis.py`, `actions.py`, `validator.py` or `explain.py`.

## Steps
1. Implement diagnosis rules from SPEC section 6. Each rule returns the evidence items it checked and which were satisfied. Confidence is the weighted fraction of satisfied evidence, reduced if the second-best rule is close.
2. Implement abstention: if confidence is below the threshold or the cause is `unknown`, return an `escalate_to_human` decision with the evidence list.
3. Implement the action dataclass and fixed menu from SPEC section 7. Reject anything else.
4. Implement `validate(action, allocations) -> (ok, reasons)` with the hard limits. Return **all** violated rules, not just the first.
5. Implement `explain(decision) -> str` using templates. No LLM needed.

## Checks
- Unit tests for each validator rule (sum must be 100, URLLC within 25 to 50, eMBB at least 20, mMTC at least 10, change at most 15).
- A flash crowd must not be diagnosed as a security anomaly in the default scenario.
- `unseen_mmtc_storm` must produce abstention.
- A property test: random actions never produce an invalid allocation after validation.

## Pitfalls
- No free-text actions. Every action is a typed object from the menu.
- Do not let diagnosis read ground truth.


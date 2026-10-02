---
name: digital-twin-precheck
description: Use when building the digital-twin pre-check that predicts the outcome of a proposed action before it is applied in SliceGuard-Lite, including training data generation and error reporting.
---

# Digital-twin pre-check

## Use this skill when
Working on `twin.py` or the B4 controller.

## Steps
1. Generate twin training data by running the simulator with **different seeds, perturbed parameters (for example interference gamma +/- 20%, base latency +/- 10%) and extra noise**, applying random valid actions, and recording state, action and the resulting URLLC latency, URLLC loss and eMBB served load.
2. Train a scikit-learn regressor (RandomForest or GradientBoosting). Save to `models/`.
3. Implement `Twin.predict(state, action) -> Prediction(latency_ms, loss_pct, embb_served_pct)`.
4. In the controller: for candidate actions from smallest to largest step, validate then predict. Accept the first predicted to meet the URLLC SLA with eMBB above minimum. If none pass, escalate.
5. Log prediction and, after the action is applied, the actual outcome so twin error can be measured.

## Checks
- Report twin MAE on held-out data in `results/summary.csv`.
- Show at least one case where the pre-check rejected a too-small step (for example +5) and chose a larger one.
- Show at least one case where the twin was wrong, and what the system did.

## Pitfalls
- The twin must not simply call the simulator. That would be circular and prove nothing.
- Do not train the twin on the evaluation seeds.


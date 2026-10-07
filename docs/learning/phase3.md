# Phase 3: Safety Loop, Policy Validator & Digital Twin Pre-Check

Welcome to Phase 3! This is the most crucial architectural milestone of **SliceGuard-Lite**. Here, we implement the safety core: proving that a network automation system must verify an action is safe before touching live infrastructure.

---

## 1. What We Built (In Simple Words)

In this phase, we completed the **autonomous safety loop** by building five interconnected components:

1. **Fixed Action Menu ([src/sliceguard/actions.py](file:///home/maurya/Downloads/sliceguard-antigravity/src/sliceguard/actions.py))**:
   - A strongly-typed, JSON-serializable catalog of approved network operations (`protect_urllc`, `rate_limit_embb`, `isolate_suspicious_traffic`, `scale_up_resource`, `escalate_to_human`, `no_action`).
   - Completely blocks arbitrary, hallucinated, or free-text commands.

2. **Policy Validator ([src/sliceguard/validator.py](file:///home/maurya/Downloads/sliceguard-antigravity/src/sliceguard/validator.py))**:
   - A deterministic firewall checking hard mathematical invariants: slice allocations must sum to $100\%$, URLLC must stay between $25\%$ and $50\%$, eMBB $\ge 20\%$, mMTC $\ge 10\%$, and max change per step $\le 15\%$.
   - Returns **all violated rules** simultaneously.

3. **Digital Twin Pre-Check ([src/sliceguard/twin.py](file:///home/maurya/Downloads/sliceguard-antigravity/src/sliceguard/twin.py))**:
   - An independent predictive machine learning model (Random Forest) trained on perturbed simulation runs.
   - Before any candidate action is applied, the Digital Twin predicts what the resulting URLLC latency and loss will be.
   - It searches from **smallest to largest step** (e.g., $+5\% \rightarrow +10\% \rightarrow +15\%$). If $+5\%$ is predicted to leave latency above $10\text{ ms}$, it rejects $+5\%$ and tests $+10\%$.

4. **Safety Abstention & Explainability ([src/sliceguard/explain.py](file:///home/maurya/Downloads/sliceguard-antigravity/src/sliceguard/explain.py))**:
   - If confidence is $<60\%$, if the cause is `unknown`, or if all candidate actions fail the twin pre-check, the controller safely **abstains** and escalates to human engineers with an auditable decision log.

5. **Controllers B1 through B4 ([src/sliceguard/controller.py](file:///home/maurya/Downloads/sliceguard-antigravity/src/sliceguard/controller.py))**:
   - **B1**: No Action (passive baseline).
   - **B2**: Static Threshold (reactive latency threshold without AI).
   - **B3**: Detector + Rules (no pre-check, no abstention).
   - **B4**: Full Safety-First Assurance (Detector + Diagnosis + Abstention + Validator + Digital Twin).

### Everyday Analogy: The Flight Simulator Pre-Check & Copilot
Imagine flying a commercial airliner in severe turbulence:
- **B1 (No Action)**: The autopilot does nothing and lets the plane lose altitude.
- **B2 (Static Rule)**: If altitude drops, yank the control stick up hard (might overstress the wings or stall the engines!).
- **B3 (Unchecked AI)**: The AI spots turbulence and immediately executes an aggressive evasive dive without checking if it exceeds structural safety limits.
- **B4 (SliceGuard-Lite Safety Loop)**:
  1. The sensor flags turbulence.
  2. The copilot diagnoses wind shear ($95\%$ confidence).
  3. The flight computer runs a fast simulation on the digital twin: *"If we climb by 500 ft, is it enough? No, still in storm. If we climb by 1,000 ft? Yes, smooth air ahead and wing stress is within limits."*
  4. Only then is the maneuver applied to the plane!
  5. If the sensors report an unexplainable instrument failure, the system does not guess—it alerts the captain (**Abstain & Escalate**).

---

## 2. Key Terms Explained

- **Digital Twin**: A software predictive model that mimics the behavior of physical network infrastructure, allowing controllers to simulate "what-if" scenarios before acting.
- **Policy Invariant**: A hard, non-negotiable rule that the network state must never violate (e.g., total capacity = $100\%$, eMBB floor $\ge 20\%$).
- **Action Pre-Checking**: Evaluating candidate actions inside a predictive twin to verify SLA compliance prior to committing changes to the live network.
- **Cooldown**: A mandatory settling period after applying an action to allow physical queues and buffers to stabilize before another action is considered.
- **Abstention**: The deliberate refusal of an AI system to take automated action when uncertain, escalating safely to human operators.

---

## 3. How the Code Fits Together

```
src/sliceguard/
  ├── actions.py            Action dataclasses, parameter schemas, and candidate menu
  ├── validator.py          Hard invariant checks (sum=100%, slice bounds, max delta)
  ├── twin.py               DigitalTwin regressor, perturbed training data generator, and precheck
  ├── explain.py            ControllerDecision schema and deterministic template explainer
  ├── controller.py         B1 (no_action), B2 (static), B3 (detector_rules), B4 (full safety loop)
  └── demo_safety_cases.py  Script demonstrating the 3 core safety behaviors
tests/
  └── test_safety_loop.py   25 unit and property tests verifying all invariants and controllers
```

---

## 4. The Three Core Safety Demonstrations

We executed `python -m sliceguard.demo_safety_cases` to prove the three required safety behaviors:

### Case A: Pre-Check Rejects Too-Small Step (+5%) and Selects Larger Step (+10%)
```text
=== CASE A: PRE-CHECK REJECTS +5% AND SELECTS +10% ===
Current Degraded State: URLLC Latency = 31.4ms (SLA Limit: 10.0ms), eMBB Served = 60.0%
Evaluating Candidate Actions from Smallest to Largest Step:
  [1] Candidate Action: protect_urllc (+5%)
      • Validator: PASSED
      • Digital Twin Prediction: Latency = 12.16ms, Loss = 0.26%
      • Pre-Check Result: REJECTED (Predicted latency 12.16ms > 10.0ms SLA)
  [2] Candidate Action: protect_urllc (+10%)
      • Validator: PASSED
      • Digital Twin Prediction: Latency = 7.27ms, Loss = 0.10%
      • Pre-Check Result: ACCEPTED & APPLIED (Predicted latency 7.27ms <= 10.0ms SLA)
```

### Case B: Safety Abstention on Unseen mMTC Storm
```text
=== CASE B: SAFETY ABSTENTION ON UNSEEN MMTC STORM ===
Simulation Tick: 223
Observable Telemetry: Registration Failures = 352.3/s (Normal: ~2/s)
Diagnosis Result: Cause = 'unknown', Confidence = 95.0%
Abstention Status: should_abstain = True
Final Action: 'escalate_to_human'
Generated Explanation:
[Tick 223] Assurance Decision Summary:
  • Diagnosis: unknown (Confidence: 95.0%)
    Evidence: Unmodeled telemetry anomaly detected (reg_failures=190.0)
  • Decision: ABSTAINED & ESCALATED TO HUMAN OPERATOR.
    Reason: Diagnosis confidence below safety threshold or unmodeled anomaly signature.
```

### Case C: Digital Twin Imperfect Prediction Audit vs Physical Reality
```text
=== CASE C: DIGITAL TWIN PREDICTION VS PHYSICAL REALITY AUDIT ===
Applied Action: protect_urllc (+10% shift)
Digital Twin Prediction (Before Action):
  • Predicted URLLC Latency: 7.41 ms
  • Predicted URLLC Loss:    0.10 %
Actual Physical Simulator Telemetry (After Action):
  • Measured URLLC Latency:  6.76 ms
  • Measured URLLC Loss:     0.09 %
Prediction Error (MAE on this transition):
  • Latency Absolute Error:  0.65 ms
  • Loss Absolute Error:     0.01 %
Overall Test Set MAE:        0.70 ms
Conclusion: Twin correctly anticipated SLA restoration (error < 1.0ms) despite parameter perturbation.
```

---

## 5. What to Try (Hands-on Experiments)

1. **Run the Safety Cases Demo**:
   - In terminal, run: `.venv/bin/python -m sliceguard.demo_safety_cases`
   - Observe the step rejection, abstention log, and error audit.
2. **Test Validator Invariants**:
   - Run the property test: `.venv/bin/pytest tests/test_safety_loop.py -k test_validator_property_test_random_actions`
   - 1,000 randomized actions are validated, verifying that zero illegal slice allocations can ever bypass the validator.
3. **Change Cooldown Duration**:
   - In [config.yaml](file:///home/maurya/Downloads/sliceguard-antigravity/config.yaml), change `controller.cooldown_ticks: 20` to `50`.
   - Notice how controllers wait longer before making secondary adjustments.

---

## 6. Quiz (Test Your Understanding)

1. **Why does the digital twin evaluate candidate actions from smallest step to largest step?**
2. **Why is the digital twin trained on perturbed simulator data rather than exact simulator runs?**
3. **What happens if a proposed action tries to allocate $55\%$ to URLLC?**
4. **Why is a static threshold controller (B2) dangerous compared to B4?**
5. **How does the LLM fit into SliceGuard-Lite's control architecture?**

<details>
<summary><b>Click here to view Quiz Answers</b></summary>

1. *To find the minimal effective intervention. Shifting too much bandwidth away from eMBB unnecessarily degrades broadband user throughput. By checking candidate actions in ascending order (+5%, +10%, +15%), the system picks the smallest step that safely restores the URLLC SLA.*
2. *To avoid circular evaluation and mimic real life. In reality, a digital twin never perfectly mirrors physical radio dynamics; training on perturbed data (+-20% gamma, base latency shifts, extra noise) proves the safety loop is robust to modeling errors.*
3. *The Policy Validator rejects the action because URLLC is constrained to a maximum of 50%. The validator returns a specific violation message and prevents the change.*
4. *B2 is blind to root cause: it blindly shifts bandwidth even if the issue is a DDoS attack or an infrastructure fault where shifting bandwidth doesn't help. B4 diagnoses the root cause, checks validity, simulates the outcome on a twin, and abstains if uncertain.*
5. *The LLM NEVER controls network actions or makes decisions. Decisions come strictly from the deterministic safety loop. An LLM can only be used as an optional text rephraser to format the structured explanation for human operators.*
</details>

---

## 7. How a Telecom Judge Might Attack This Phase & How to Answer

> **Judge Attack:** *"If your Digital Twin is just an ML model, what happens when the Twin itself makes an incorrect prediction and claims an action is safe when it is actually unsafe?"*

**Your Confident & Honest Answer:**
> *"That is a fundamental challenge in predictive network automation, and SliceGuard-Lite is explicitly architected with **defense-in-depth**:*
> 
> *First, the Digital Twin is not the only safety check—the **deterministic Policy Validator** runs first and enforces hard boundaries (allocation floors, conservation of capacity, maximum delta caps) that no ML model can override.*
> 
> *Second, we continuously audit the Twin: after an action is applied, live physical telemetry is compared against the Twin's prior prediction to log the Mean Absolute Error (MAE). If the physical SLA is not restored, the closed-loop controller's cooldown expires, detects the ongoing breach, and falls back to escalating to human operators.*
> 
> *Third, our evaluation measures this exact risk: we report 'harmful actions' as an explicit benchmark metric across all controllers."*

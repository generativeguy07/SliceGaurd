# Phase 2: Detection and diagnosis

Start Phase 2 (or run `/phase2-detect-diagnose`).

Using the `anomaly-detector` and `diagnosis-and-actions` skills, build the feature extraction, Isolation Forest detector with calibration and persistence rule, and the rule-based diagnosis with confidence and abstention logic (SPEC sections 5 and 6).

Requirements:
- Train only on normal runs. Calibrate on separate held-out normal runs.
- The detector and diagnosis must not read ground-truth columns (add a test).
- Show a table of detection delay, false alarms, precision and recall per scenario.
- Show diagnosis accuracy per scenario. The flash crowd must not be labelled as an attack by default, and the unseen mMTC storm should cause abstention. If they do not, explain why and fix the rules rather than hiding it.

Then write `docs/learning/phase2.md`, run the tests and stop.

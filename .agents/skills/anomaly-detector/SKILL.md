---
name: anomaly-detector
description: Use when building the Isolation Forest anomaly detector, feature extraction, threshold calibration or persistence rule for SliceGuard-Lite.
---

# Anomaly detector

## Use this skill when
Working on `features.py` or `detector.py`.

## Steps
1. Build rolling-window features per SPEC section 5 (mean, std, rate of change per KPI over `detector.window`).
2. Train IsolationForest only on normal runs from several seeds. Save with joblib to `models/`.
3. Calibrate the score threshold on separate held-out normal runs so the false-alarm rate is about `detector.target_false_alarm_rate`.
4. Apply the persistence rule (`k` of last `n`) before declaring an incident.
5. Expose `Detector.fit(normal_runs)`, `Detector.score(row_or_window)`, `Detector.is_incident(history)`.

## Checks
- No use of ground-truth columns (test by dropping them and confirming identical output).
- Report precision, recall, false-alarm rate and detection delay across scenarios.
- Test on the noisy and overlapping scenarios. Report honestly if detection degrades.

## Pitfalls
- The detector only says "unusual". Do not let it output a cause.
- Do not tune thresholds on the same data used for the final evaluation.


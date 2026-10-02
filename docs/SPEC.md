# SPEC: SliceGuard-Lite

All numbers here are **assumed simulation parameters**, not measurements of a real network. They live in `config.yaml`.

## 1. Slices
| Slice | Meaning | Default allocation | Notes |
|---|---|---|---|
| eMBB | high-bandwidth (video, downloads) | 60% | min 20% |
| URLLC | critical, low latency (emergency telemetry) | 25% | min 25%, max 50% |
| mMTC | many small IoT devices | 15% | min 10% |

Allocations always sum to exactly 100%.

## 2. Time and KPIs
One tick = 1 second. A run is 600 ticks. Events start at tick 200 and last about 250 ticks unless the scenario says otherwise.

One row per tick (wide format). Columns:
```
t, scenario, event_label, is_attack,
alloc_embb, alloc_urllc, alloc_mmtc,
embb_demand_pct, embb_served_pct, embb_throughput_mbps, embb_latency_ms,
urllc_latency_ms, urllc_loss_pct, urllc_jitter_ms,
mmtc_devices, mmtc_reg_failures,
cpu_pct, shared_util_pct,
req_rate_total, pattern_anomaly_ratio
```
`event_label` and `is_attack` are **ground truth for evaluation only**. The detector, diagnosis and controllers must never read them.

`pattern_anomaly_ratio` (0..1) is a simulated proxy for how unusual the traffic pattern is (for example fraction of packets with abnormal size or source pattern). It is high for DDoS-like floods and low for a legitimate flash crowd. This is the key feature that separates attack from legitimate surge.

## 3. Network model (starting point, refine and document)
Let `D_s` be the demand of slice `s` in % of total capacity, `A_s` its allocation, and `cap` a capacity factor (1.0 normal, lower during an infrastructure fault).

```
served_embb = min(D_embb * (1 - rate_limit_embb), A_embb * cap)
I = clip((served_embb - threshold_pct) / width_pct, 0, 1)          # cross-slice interference 0..1
rho_urllc_eff = D_urllc / (A_urllc * cap) + gamma * I
latency(rho, base) = base * (1 + rho^2 / (1 - rho)),  with rho capped at 0.97
urllc_latency_ms = latency(rho_urllc_eff, base_urllc)
urllc_loss_pct  = 0.1 + k * max(0, rho_urllc_eff - 0.7)^2     (choose k so loss ~4-5% at the surge)
```
Intuition: the allocation caps how much shared capacity eMBB can consume, so moving allocation from eMBB to URLLC reduces interference.

Sanity targets with defaults (D_urllc = 9, D_embb = 27 normal, 70 in surge, base_urllc = 5):
| Situation | URLLC latency (approx) |
|---|---|
| Normal | 6 ms |
| eMBB surge, no action | 31 ms |
| Surge, protect_urllc +10 | 6.6 ms |
| Surge, protect_urllc +5 | 10.5 ms (just over SLA, so the pre-check should prefer a bigger step) |

Add multiplicative Gaussian noise (`noise.multiplicative_std`) and random missing readings (`missing_reading_prob`) to the KPI output. Document any change to these equations in `docs/ASSUMPTIONS.md`.

Other KPI behaviour (suggested): `cpu_pct` and `shared_util_pct` rise with total served load and with attack request rate; `eMBB throughput` proportional to served load; `mmtc_devices` roughly constant with small random walk; `mmtc_reg_failures` low normally.

## 4. Scenarios
| Name | Behaviour | Ground truth |
|---|---|---|
| normal | no event (used for training and false-alarm testing) | none |
| embb_surge | eMBB demand ramps from ~27 to ~70 quickly; pattern ratio low-moderate | resource_contention, not attack |
| ddos_like | request rate and pattern_anomaly_ratio jump; CPU rises fast; eMBB served load rises | security_anomaly, attack |
| infra_bottleneck | capacity factor drops (for example 0.6); throughput falls, latency and loss rise, CPU/memory high | infrastructure_fault |
| flash_crowd | legitimate surge: slower ramp, low pattern_anomaly_ratio, normal request pattern | traffic_overload, **not** attack |
| overlapping | embb_surge and infra_bottleneck start close together | multiple |
| noisy_kpis | embb_surge with higher noise and more missing readings | resource_contention |
| unseen_mmtc_storm | mMTC registration storm (registration failures spike). **Not covered by any diagnosis rule.** | unknown, the system should abstain |

## 5. Detector
- Isolation Forest from scikit-learn.
- Features: for each KPI, rolling mean, rolling std and rate of change over `detector.window` ticks.
- Train **only on normal runs** (several seeds). Calibrate the anomaly-score threshold on held-out normal runs to hit `target_false_alarm_rate`.
- Persistence rule: flag an incident only if the score exceeds the threshold in `persistence_k` of the last `persistence_n` ticks.
- The detector says only "unusual". It never names a cause.

## 6. Diagnosis and abstention
Rule-based, readable. Candidate causes: `normal_variation`, `traffic_overload`, `cross_slice_contention`, `infrastructure_bottleneck`, `security_anomaly`, `unknown`.

Each rule checks evidence over the last `evidence_window_ticks`. Example evidence:
- cross_slice_contention: eMBB served load up sharply AND URLLC latency up AND shared utilisation high AND pattern ratio low.
- security_anomaly: request rate up sharply AND pattern_anomaly_ratio high AND CPU rising fast.
- infrastructure_bottleneck: throughput down while latency, loss and CPU/memory up.
- traffic_overload (flash crowd): demand up with slow ramp and low pattern ratio.

Confidence = weighted fraction of satisfied evidence items for the best rule, reduced when two rules score similarly. If confidence < `abstain_confidence_threshold` or the best cause is `unknown`, the controller **abstains**: no action, raise an alert with the collected evidence.

## 7. Actions, validator and digital twin
### Action menu (structured, JSON-serialisable)
```json
{
  "action": "protect_urllc | rate_limit_embb | isolate_suspicious_traffic | scale_up_resource | escalate_to_human | no_action",
  "params": {"shift_pct": 10, "rate_limit_pct": 20},
  "reason": "text",
  "cause": "cross_slice_contention",
  "confidence": 0.87
}
```
- `protect_urllc`: move `shift_pct` from eMBB to URLLC.
- `rate_limit_embb`: reduce eMBB demand by `rate_limit_pct`.
- `isolate_suspicious_traffic`: simulated removal of the attack share of traffic from the affected slice (only used for diagnosed security anomalies).
- `scale_up_resource`: simulated, increases capacity factor by a small bounded amount.
- Anything not in the menu is rejected.

### Policy validator (hard limits)
- Slice names valid; allocations within 0..100; sum exactly 100.
- URLLC allocation within [25, 50]; eMBB >= 20; mMTC >= 10.
- Change per action <= 15 points.
- Action is in the menu, and its parameters are in range.

### Digital-twin pre-check
- A **separate predictive model** that estimates, for a candidate action, the resulting URLLC latency, URLLC loss and eMBB served load.
- Train it (for example RandomForest or GradientBoosting from scikit-learn) on data generated by the simulator with **different seeds, perturbed parameters and extra noise**, so it is an approximation and not a copy of the ground truth.
- Report the twin's prediction error (MAE) on held-out data in the results.
- Procedure: for each candidate action (smallest to largest step), validate, then predict. Accept the first action predicted to satisfy the URLLC SLA while keeping eMBB above its minimum. If none passes, reject all and escalate to a human.

## 8. Controllers to compare
| ID | Name | Behaviour |
|---|---|---|
| B1 | no_action | does nothing |
| B2 | static_threshold | if URLLC latency > SLA threshold, shift a fixed 10 points from eMBB to URLLC (still validator-checked), no detector, no twin |
| B3 | detector_rules | detector + diagnosis + validator, **no twin and no abstention** |
| B4 | full | detector + diagnosis + abstention + validator + twin pre-check |

All controllers apply actions to the same simulator instance type with the same seeds so comparisons are fair.

## 9. Metrics (computed per run, then averaged over seeds with spread)
- detection_delay_ticks (from event start to first correct flag)
- false_alarm_rate (flags outside events / normal ticks)
- sla_violation_ticks (URLLC latency or loss above SLA)
- mean_urllc_latency_ms and packet loss during the event
- embb_throughput_lost_pct (the cost of protection)
- harmful_or_unnecessary_actions (action taken in a non-incident, or made SLA worse, or taken against a legitimate flash crowd as if it were an attack)
- abstention_rate and recovery_delay when abstaining
- diagnosis_accuracy per scenario (including flash_crowd and unseen_mmtc_storm)
- twin_mae_latency_ms

Output: `results/summary.csv`, `results/per_run.csv`, plots in `results/figures/`.

## 10. Dashboard (Streamlit)
Buttons: inject eMBB surge, DDoS-like flood, infrastructure fault, flash crowd, unknown event. Live KPI charts, detector flag, diagnosis with confidence, proposed action, twin prediction, validator result, applied or rejected or abstained, recovery, explanation text, decision log and a results tab with the B1 to B4 comparison from `results/summary.csv`. Must run offline.

## 11. Explanations
Template-based text built from the structured decision (cause, confidence, action, twin prediction, validator result). Optional local-LLM rephrasing is allowed only as a separate, switch-off-able function that never changes the decision.

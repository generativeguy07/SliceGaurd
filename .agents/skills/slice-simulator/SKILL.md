---
name: slice-simulator
description: Use when building or changing the three-slice 5G network simulator, KPI generation, noise, scenarios or ground-truth labels for SliceGuard-Lite.
---

# Slice simulator

## Use this skill when
Creating or editing `simulator.py`, `scenarios.py` or anything that generates KPI data.

## Steps
1. Read SPEC sections 1 to 4 and `config.yaml`.
2. Implement `Simulator(config, rng)` with `step(action=None) -> KPIRow` so a controller can act in the loop. Keep the interference model from SPEC section 3 and record any change in `docs/ASSUMPTIONS.md`.
3. Allocation is a cap on how much shared capacity a slice consumes. Capacity factor `cap` models infrastructure faults. `rate_limit_embb` reduces eMBB demand.
4. Add multiplicative noise and random missing readings after the true KPIs are computed.
5. Implement each scenario as a function that returns a demand and event schedule (time-varying) plus ground-truth labels. Labels are stored in separate columns and never given to the detector.
6. `generate_run(scenario, seed) -> DataFrame` for offline data, and a stepwise API for closed-loop control.

## Checks
- Same seed gives identical output (test it).
- With defaults: normal URLLC latency about 6 ms; surge with no action about 30 ms (document actual values).
- Allocations always sum to 100 after any applied action.
- Plot normal and surge KPIs to `results/figures/` as a visual sanity check.

## Pitfalls
- Do not let the ground-truth label influence KPI values except through the scenario definition.
- Keep flash_crowd distinguishable from ddos_like only via pattern_anomaly_ratio, request rate shape and ramp speed, as in the SPEC.


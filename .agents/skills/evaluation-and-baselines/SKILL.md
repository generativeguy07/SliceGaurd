---
name: evaluation-and-baselines
description: Use when writing the experiment runner, baselines B1 to B4, metrics, multi-seed evaluation, tables and plots for SliceGuard-Lite.
---

# Evaluation and baselines

## Use this skill when
Working on `controller.py` baselines or `evaluate.py`.

## Steps
1. Implement controllers B1 (no action), B2 (static threshold), B3 (detector plus rules, no twin or abstention), B4 (full), per SPEC section 8.
2. For every scenario and every seed in `evaluation.n_seeds`, run all four controllers on identical scenario seeds.
3. Compute the metrics in SPEC section 9 per run. Save `results/per_run.csv`.
4. Aggregate to `results/summary.csv` with mean and standard deviation (and a simple 95% interval) per controller per scenario.
5. Produce plots: SLA-violation ticks per controller, false-alarm rate, harmful actions, eMBB throughput lost, and one time-series example per scenario.
6. Provide a single command: `python -m sliceguard.evaluate`.

## Checks
- Re-running with the same config gives identical tables.
- Include the flash-crowd and unseen-event scenarios in the headline table.
- Include at least one result where B4 is not the best, and explain why in `docs/LIMITATIONS.md`.

## Pitfalls
- Do not tune on evaluation seeds. Use separate seeds for training, calibration and evaluation.
- Do not report a metric you did not compute.


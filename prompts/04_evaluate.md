# Phase 4: Evaluation

Start Phase 4 (or run `/phase4-evaluate`).

Write `evaluate.py` per SPEC section 9 and the `evaluation-and-baselines` skill. Run all scenarios for B1 to B4 across the configured seeds, with separate seeds for training, calibration and evaluation.

Deliverables:
- `results/per_run.csv`, `results/summary.csv`, plots in `results/figures/`
- `docs/LIMITATIONS.md` first version, including at least one case where B4 is not best and why
- A plain-language reading guide for the results table in `docs/learning/phase4.md`

Verify reproducibility by running the command twice and diffing the summary. Do not tune on evaluation seeds. Then stop.

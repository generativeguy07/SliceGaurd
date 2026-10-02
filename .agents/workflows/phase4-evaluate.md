---
description: Run the multi-seed evaluation of B1 to B4 (Phase 4).
---

1. Read SPEC sections 8 and 9.
2. Use the `evaluation-and-baselines` skill.
3. Create `evaluate.py` and run `python -m sliceguard.evaluate`.
4. Verify tables and figures in `results/`. Check reproducibility by running twice.
5. Write `docs/LIMITATIONS.md` (first version) including at least one case where B4 is not best.
6. Run `pytest -q`, write `docs/learning/phase4.md`, summarise and stop.

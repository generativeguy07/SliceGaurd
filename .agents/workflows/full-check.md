---
description: Run all tests, lint, and a reproducibility check.
---

1. Run `pytest -q` and fix failures.
2. Check no module reads `event_label` or `is_attack` outside evaluation code.
3. Check every allocation change goes through `validator.py`.
4. Re-run `python -m sliceguard.evaluate` twice and confirm identical `results/summary.csv`.
5. Report problems found and fixes made.

# Project rules (always on)

1. Read `AGENTS.md` and `docs/SPEC.md` before changing code.
2. Work one phase at a time. At the end of a phase: run `pytest -q`, summarise what changed, write the learning note, then stop and wait.
3. Never hard-code numbers that belong in `config.yaml`.
4. Detector, diagnosis and controllers must never read ground-truth columns (`event_label`, `is_attack`). Add a test that enforces this.
5. Every action must pass through `validator.py`. No code path may change allocations without validation.
6. The LLM must never decide or execute network actions.
7. All randomness is seeded. Same seed gives the same result.
8. Keep modules small and readable, with docstrings and type hints. Prefer clarity over cleverness: the human must be able to explain every function.
9. Do not add dependencies beyond `requirements.txt` without asking.

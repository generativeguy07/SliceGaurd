# Python style (always on)

- Python 3.10+, type hints on public functions, short docstrings that explain the networking meaning in plain words.
- Use dataclasses or typed dicts for structured objects (Action, Decision, KPIRow).
- No global mutable state. Pass config and a numpy `Generator` explicitly.
- Use `pathlib`, not string paths. Keep functions under about 40 lines when practical.
- Tests with pytest in `tests/`. Name them after behaviour, for example `test_validator_rejects_total_not_100`.
- Plots with matplotlib, saved to `results/figures/`. Label axes with units.

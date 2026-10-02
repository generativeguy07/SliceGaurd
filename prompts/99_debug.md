# Debug / full check

Something is wrong or I want a health check.

1. Run `pytest -q` and show me the failures.
2. For each failure, explain the cause in simple words, then fix it with the smallest change.
3. Verify: no module outside evaluation reads `event_label` or `is_attack`; every allocation change goes through `validator.py`; same seed gives identical results.
4. Tell me what you changed and why. Do not change the SPEC or the config values without telling me.

# Phase 1: Simulator

Start Phase 1 (or run `/phase1-simulator`).

Build the three-slice simulator and the scenarios exactly as in SPEC sections 1 to 4, using the `slice-simulator` skill.

Deliverables:
- `src/sliceguard/config.py`, `simulator.py`, `scenarios.py`
- tests in `tests/test_simulator.py` (determinism with seed, allocations sum to 100, ground-truth columns exist, surge raises URLLC latency)
- sanity plots in `results/figures/` (normal run, eMBB surge run)
- `docs/ASSUMPTIONS.md` first version
- `docs/learning/phase1.md`

When done: run the tests, show me the plots, and tell me in simple words what URLLC, eMBB and mMTC are and why the surge hurts URLLC in this model. Then stop.

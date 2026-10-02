# Phase 3: Safety loop

Start Phase 3 (or run `/phase3-safety-loop`).

Build the action menu, policy validator, digital-twin pre-check, abstention, explanations and controllers B1 to B4 (SPEC sections 7 and 8), using the `diagnosis-and-actions`, `digital-twin-precheck` and `evaluation-and-baselines` skills.

Requirements:
- The twin must be an approximate model trained on perturbed simulator runs, not a call to the simulator.
- The validator returns all violated rules. Add unit tests for each rule and a property test with random actions.
- Demonstrate three cases with logs: (a) pre-check rejects a +5 step and chooses a larger step, (b) abstention on the unseen mMTC storm, (c) a case where the twin is wrong and what happens.

Then write `docs/learning/phase3.md`, run the tests and stop.

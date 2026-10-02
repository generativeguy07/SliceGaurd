# AGENTS.md: SliceGuard-Lite

## Project purpose
SliceGuard-Lite is a **simulation-based prototype** of autonomous assurance for 5G network slices. It detects abnormal behaviour in slice KPIs, estimates the likely cause with a confidence value, proposes a corrective action from a fixed menu, checks the action (policy validator plus a digital-twin pre-check), applies it in the simulator only if the critical slice is predicted to stay within its SLA, and abstains and escalates to a human when confidence is low. Every decision is logged with a plain-language explanation.

Tagline: *Autonomous networks need AI that proves an action is safe before it acts.*

This is a student prototype for the Nokia Shark Tank (AI in Telecom) preliminary selection at RV University. It runs locally with free tools, no paid cloud and no 5G hardware.

## Where to look first
1. `docs/SPEC.md` is the technical source of truth (data schema, model equations, parameters, interfaces).
2. `config.yaml` holds all tunable numbers. Do not hard-code them.
3. `.agents/rules/` holds always-on rules. `.agents/skills/` holds task knowledge. `.agents/workflows/` holds slash commands.
4. `docs/ROADMAP.md` is the phase plan.

## Hard constraints
- Python 3.10+, free libraries only: numpy, pandas, scikit-learn, matplotlib, streamlit, pyyaml, joblib, pytest.
- **The LLM never controls the simulator.** Actions come only from the fixed action menu and always pass the validator. A language model, if used at all, only rephrases an already-made decision. It must be optional and the project must run without it.
- All randomness uses explicit seeds. Every experiment is reproducible from `config.yaml` plus a seed.
- The digital twin must **not** be identical to the ground-truth simulator (see SPEC section 7). Avoid circular evaluation.
- Never fabricate, estimate or hand-type experimental results. Numbers in reports come only from files in `results/`.
- Describe the project as a simulation and proof of concept. Never claim integration with any vendor product or a real operator network.

## Repository layout (target)
```
src/sliceguard/
  config.py        load config.yaml
  simulator.py     three-slice network model, noise, event injection
  scenarios.py     scenario definitions and ground-truth labels
  features.py      rolling-window feature extraction
  detector.py      Isolation Forest, calibration
  diagnosis.py     correlation rules, cause and confidence
  actions.py       fixed action menu and schema
  validator.py     hard policy limits
  twin.py          approximate predictive model (digital twin)
  controller.py    B1..B4 controllers, abstention logic
  explain.py       template-based decision explanations
  evaluate.py      experiment runner, metrics, result tables and plots
  app.py           Streamlit dashboard
tests/             pytest tests
results/           generated CSVs and figures
docs/learning/     phase notes written for the human teammate
```

## Working agreement
- Work **one phase at a time** (see ROADMAP). Stop after each phase and summarise.
- After every phase: run `pytest -q`, then write `docs/learning/phaseN.md` (see rule `03-teach-the-human.md`).
- Prefer small, readable functions with docstrings and type hints. The human teammate is a beginner in networking and must be able to read and explain the code.
- When you make a modelling assumption, record it in `docs/ASSUMPTIONS.md` with the reason.
- If a requirement is ambiguous, state your assumption and continue. Ask the human only when the choice changes the project direction.

## Definition of done (whole project)
- `python -m sliceguard.evaluate` produces results for B1 to B4 across all scenarios and at least 30 seeds, with tables in `results/` and plots.
- `streamlit run src/sliceguard/app.py` runs the 2-minute demo flow offline.
- `pytest -q` passes.
- `docs/ASSUMPTIONS.md` and `docs/LIMITATIONS.md` exist and are honest.

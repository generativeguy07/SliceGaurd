# GEMINI.md

This file is the Antigravity entry point. All project guidelines live in `AGENTS.md`.

Before doing anything:
1. Read `AGENTS.md`.
2. Read `docs/SPEC.md`.
3. Follow the rules in `.agents/rules/` and use the skills in `.agents/skills/` when relevant.

Core reminders:
- Build one phase at a time, test, then explain to the human in `docs/learning/`.
- The LLM never controls the network simulation. Fixed action menu, validator, digital-twin pre-check, abstain when unsure.
- Never invent results. Only report numbers produced by the evaluation runner.

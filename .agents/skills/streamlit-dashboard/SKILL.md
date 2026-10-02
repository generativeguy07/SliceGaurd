---
name: streamlit-dashboard
description: Use when building the Streamlit demo dashboard for SliceGuard-Lite with event injection buttons, live KPIs, decision log and results tab.
---

# Streamlit dashboard

## Use this skill when
Working on `src/sliceguard/app.py`.

## Layout
- Sidebar: seed, controller (B1 to B4), speed, buttons to inject: eMBB surge, DDoS-like flood, infrastructure fault, flash crowd, unknown event, reset.
- Main: live line charts (URLLC latency with SLA line, packet loss, eMBB load, allocations), status banner (normal, incident, abstained, recovered), decision panel (cause, confidence, action, twin prediction, validator result, applied or rejected), explanation text, decision log table.
- Results tab: reads `results/summary.csv` and shows the B1 to B4 comparison and figures.

## Rules
- Must run fully offline with `streamlit run src/sliceguard/app.py`.
- Keep simulator state in `st.session_state`. Step the simulation with a button or a timed loop, not blocking calls.
- Show a visible "SIMULATION" label. Never show numbers as if from a real network.
- If `results/summary.csv` is missing, show a message telling the user to run the evaluation first.

## Demo flow (2 minutes)
Normal, inject surge, detect, diagnose, pre-check, apply, recover, inject flash crowd (handled without treating as attack), inject unknown event (abstain), open results tab.


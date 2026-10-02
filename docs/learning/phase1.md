# Phase 1: 5G Network Slice Simulator & Scenarios

Welcome to the Phase 1 learning notes! This document gives you the foundational telecom and system knowledge you need to explain this phase to any telecom expert or hackathon judge with complete confidence.

---

## 1. What We Built (In Simple Words)

In this phase, we built a mathematical **three-slice 5G network simulator** and **eight distinct traffic scenarios**. 

The simulator generates per-second telemetry data (latency, packet loss, throughput, CPU utilization, jitter) for three 5G slices sharing a common pool of radio and compute capacity. Crucially, when video downloads (eMBB) surge, the shared buffers and scheduler get clogged, which causes high-priority emergency packets (URLLC) to experience dangerous delays and packet loss (cross-slice interference). We also built the ability to apply corrective actions (like reallocating bandwidth or rate-limiting) mid-simulation to see how the network recovers.

### 🚗 Everyday Analogy: The 3-Lane Highway
Imagine a 3-lane highway:
1. **Lane 1 (eMBB)**: A freight lane for heavy cargo trucks (video streams).
2. **Lane 2 (URLLC)**: An emergency lane reserved for ambulances and fire trucks (critical low-latency data).
3. **Lane 3 (mMTC)**: A lane for thousands of tiny electric scooters (smart meters/IoT).

Normally, traffic flows freely: the ambulance drives at top speed ($6\text{ ms}$ delay). But during an "eMBB surge", an avalanche of trucks floods Lane 1, overflows into the highway merge zone, and blocks the ambulance ($31\text{ ms}$ delay!). 

By shifting capacity (`protect_urllc`), we dynamically widen the emergency lane, clearing a path so the ambulance gets back down to safety ($6.6\text{ ms}$).

---

## 2. Key Terms Explained

- **5G Network Slice**: A dedicated virtual network carved out of shared physical infrastructure, customized for a specific type of service.
- **eMBB (enhanced Mobile Broadband)**: The slice designed for heavy data throughput, such as 4K video streaming, downloads, and VR.
- **URLLC (Ultra-Reliable Low-Latency Communication)**: The critical slice designed for missions where failure is not an option (e.g. robotic surgery, smart grid protection, autonomous braking), requiring latency under $10\text{ ms}$ and near-zero packet loss.
- **mMTC (massive Machine-Type Communication)**: The slice designed to connect tens of thousands of low-power IoT devices (e.g., smart utility meters, environmental sensors) sending small, intermittent packets.
- **SLA (Service Level Agreement)**: The contractual performance guarantee that an operator promises to customers (e.g., "URLLC latency will not exceed $10\text{ ms}$").
- **Cross-Slice Interference**: When heavy traffic in one slice consumes shared queues, buffers, or radio resource blocks, indirectly slowing down other isolated slices.
- **Jitter**: The variation or instability in packet arrival times, which can disrupt real-time control loops.
- **Closed-Loop Assurance**: An automated system that continuously monitors telemetry, detects degradation, decides on a fix, and executes it without waiting for manual human intervention.

---

## 3. How the Code Fits Together

Here is the architectural layout of what we built in Phase 1:

```
src/sliceguard/
  ├── config.py         Loads all parameters from config.yaml into typed dataclasses
  ├── scenarios.py      Defines the 8 scenario schedules, event profiles, and ground-truth
  ├── simulator.py      Mathematical 3-slice engine, cross-slice interference, and step API
  └── plot_sanity.py    Generates verification plots to results/figures/
tests/
  └── test_simulator.py Pytest suite verifying SLAs, seed reproducibility, and shielding
```

### Key Functions and Classes:
1. **`AppConfig` & `load_config()`** ([src/sliceguard/config.py](file:///home/maurya/Downloads/sliceguard-antigravity/src/sliceguard/config.py)):
   - Loads [config.yaml](file:///home/maurya/Downloads/sliceguard-antigravity/config.yaml). Ensures no numbers are hardcoded anywhere in the logic.
2. **`ScenarioRegistry.get_tick_profile()`** ([src/sliceguard/scenarios.py](file:///home/maurya/Downloads/sliceguard-antigravity/src/sliceguard/scenarios.py)):
   - Computes time-varying demand schedules, capacity factors, and ground truth for any of the 8 scenarios at tick $t$.
3. **`Simulator.step(action)`** ([src/sliceguard/simulator.py](file:///home/maurya/Downloads/sliceguard-antigravity/src/sliceguard/simulator.py)):
   - Executes 1 tick of physical simulation: updates slice allocations if an action was provided, calculates nonlinear interference $I$, effective load $\rho$, latency, loss, and adds sensor noise.
4. **`Simulator.run()` / `generate_run()`** ([src/sliceguard/simulator.py](file:///home/maurya/Downloads/sliceguard-antigravity/src/sliceguard/simulator.py)):
   - Runs a full 600-second simulation and returns a pandas DataFrame with all metrics.
5. **`generate_sanity_plots()`** ([src/sliceguard/plot_sanity.py](file:///home/maurya/Downloads/sliceguard-antigravity/src/sliceguard/plot_sanity.py)):
   - Generates and saves visual verification charts to `results/figures/`.

---

## 4. What to Try (Hands-on Experiments)

Try modifying values in [config.yaml](file:///home/maurya/Downloads/sliceguard-antigravity/config.yaml) to see how the network behavior responds:

1. **Change Interference Coupling (`interference.gamma`)**:
   - In [config.yaml](file:///home/maurya/Downloads/sliceguard-antigravity/config.yaml), change `gamma: 0.5` to `gamma: 0.8`.
   - Run `.venv/bin/python -m sliceguard.plot_sanity` and inspect `results/figures/phase1_normal_vs_surge.png`.
   - *Observation*: Notice how URLLC latency shoots up even higher during the surge because cross-slice contention is modeled as stronger. (Remember to restore it to 0.5 afterward).
2. **Make Telemetry Noisier (`noise.multiplicative_std`)**:
   - In [config.yaml](file:///home/maurya/Downloads/sliceguard-antigravity/config.yaml), change `multiplicative_std: 0.04` to `0.10` (10% noise).
   - Re-run `.venv/bin/python -m sliceguard.plot_sanity`.
   - *Observation*: Observe the jagged spikes in the telemetry curves. This mimics noisy real-world radio channel metrics.
3. **Run the Automated Test Suite**:
   - Run `.venv/bin/pytest -q` in the terminal.
   - All 10 tests pass, confirming mathematical consistency and reproducibility.

---

## 5. Quiz (Test Your Understanding)

1. **Why does an eMBB surge cause URLLC latency to spike if slices are supposed to be isolated?**
2. **What is the difference between `flash_crowd` and `ddos_like` in our simulation?**
3. **Why do we strictly shield `event_label` and `is_attack` from the detector and controller?**
4. **What happens to the slice allocations when we apply the action `protect_urllc` with `shift_pct: 10`?**
5. **What is the role of `seed` in our simulation?**

<details>
<summary><b>Click here to view Quiz Answers</b></summary>

1. *In real 5G networks, physical isolation is never 100% complete; slices share physical radio channels, baseband processing cores, and internal buffer queues. When eMBB demand exceeds the interference threshold (45%), queue buildup and scheduler delays spill over, causing cross-slice interference on URLLC.*
2. *Both cause a surge in traffic, but `flash_crowd` represents legitimate user activity (slower ramp, normal packet patterns with low `pattern_anomaly_ratio`), whereas `ddos_like` is a malicious flood (abrupt step increase, high `pattern_anomaly_ratio` > 0.8).*
3. *In real-world networks, operators do not have an omniscient "label" telling them whether an ongoing anomaly is an attack or a fault. The AI assurance engine must infer the situation purely from observable telemetry metrics. The ground-truth labels are used solely by the evaluation harness to grade accuracy.*
4. *URLLC allocation increases from 25% to 35% (+10%), eMBB allocation decreases from 60% to 50% (-10%), and mMTC remains at 15%. Total allocation remains exactly 100%.*
5. *The seed initializes the pseudo-random number generator, ensuring that noise, dropouts, and experiments are 100% bit-for-bit reproducible.*
</details>

---

## 6. How a Telecom Judge Might Attack This Phase & How to Answer

> **Judge Attack:** *"Your simulator uses simplified queuing formulas ($M/M/1$) instead of an open-source 3GPP protocol stack like OpenAirInterface, ns-3, or Free5GC. How can you claim your results are meaningful?"*

**Your Confident & Honest Answer:**
> *"That is a very fair point. Our goal in SliceGuard-Lite is not to simulate per-packet radio waveform propagation, but to prototype and rigorously benchmark the **closed-loop decision and safety architecture** (the combination of anomaly detection, causal diagnosis, policy validation, and predictive digital-twin pre-checks).*
> 
> *Our mathematical model captures the core physical reality: shared resource contention, queue-induced latency degradation, and capacity conservation. Because our controller interfaces exclusively via standardized telemetry metrics (KPIs) and standard slice management actions (3GPP-compatible resource reallocation), this entire safety-first control loop can be plugged directly on top of an ns-3 simulation or an O-RAN Near-RT RIC in future work without changing the decision architecture."*

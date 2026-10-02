# Phase 5: Streamlit Interactive Demo Dashboard

Welcome to the Phase 5 learning notes! In this phase, we built the **interactive demonstration dashboard** that lets judges, telecom engineers, and stakeholders see SliceGuard-Lite in action in real time.

---

## 1. What We Built (In Simple Words)

In this phase, we built an offline-capable, interactive **Streamlit dashboard** ([src/sliceguard/app.py](file:///home/maurya/Downloads/sliceguard-antigravity/src/sliceguard/app.py)) that brings our simulation and safety loop to life.

With this dashboard, you can:
1. **Inject Anomaly Events with 1 Click**: eMBB Bandwidth Surge, DDoS Attack, Hardware Bottleneck, Flash Crowd, or Unseen IoT Storm.
2. **Watch Real-Time Telemetry**: Live updating charts for URLLC latency (with the $10\text{ ms}$ SLA line), packet loss, capacity utilization, and dynamic slice allocations.
3. **Inspect the Safety Pre-Check in Action**: See the Isolation Forest trigger, view the diagnosed root cause and confidence score, watch the Digital Twin simulate candidate actions, and verify that the Policy Validator checks all constraints before anything touches the simulator.
4. **Demonstrate Safety Abstention**: Inject an unseen mMTC storm and watch the system automatically abstain and escalate to human operators rather than taking destructive actions.
5. **Explore Benchmark Results**: Browse multi-seed evaluation tables and charts comparing B1 through B4 across all 8 scenarios.

### 🎮 Everyday Analogy: The Flight Simulator Cockpit
Imagine training a commercial airline pilot:
- Instead of testing maneuvers on a real aircraft carrying passengers, you put the pilot in a **full-motion flight simulator cockpit**.
- The flight instructor has an "event injection panel": they press a button to trigger wind shear or engine failure.
- The cockpit dials (latency, loss, throttle) react immediately. The copilot AI assesses the emergency, pre-tests a recovery climb in the simulation computer, and displays the exact plan on the multi-function display before executing.

---

## 2. Key Terms Explained

- **Streamlit**: A Python framework for building interactive web applications for data science and machine learning prototypes.
- **Session State (`st.session_state`)**: A persistent memory mechanism in Streamlit that preserves variables (e.g. simulator tick, active controller, telemetry history) across user interactions and button clicks.
- **Offline Capable**: The application runs completely on local hardware without requiring internet access, cloud APIs, or external server infrastructure.
- **Closed-Loop Demo Flow**: A rapid 2-minute live walkthrough demonstrating normal state $\rightarrow$ event injection $\rightarrow$ autonomous detection $\rightarrow$ causal diagnosis $\rightarrow$ twin pre-check $\rightarrow$ action execution $\rightarrow$ SLA recovery.

---

## 3. How to Run the 2-Minute Demo for Telecom Judges

To launch the dashboard, run:
```bash
streamlit run src/sliceguard/app.py
```

### The 2-Minute Scripted Demonstration Flow:
1. **Step 1: Normal Operation (0:00 - 0:20)**:
   - Click **🟢 Normal Baseline**. Click **+50s** twice to advance to tick 100.
   - Point to the live gauges: URLLC latency is resting safely at $\approx 6\text{ ms}$, packet loss is $0.1\%$, and slice allocations are at default ($60\%$ eMBB, $25\%$ URLLC, $15\%$ mMTC).
2. **Step 2: Inject eMBB Surge & Show Failure in B1 (0:20 - 0:50)**:
   - Switch controller in sidebar to **B1 (No Action)**. Click **⚠️ Inject eMBB Surge**. Advance with **+50s** to tick 250.
   - Point to the red SLA violation: URLLC latency spikes to $\approx 31\text{ ms}$, breaching the $10\text{ ms}$ SLA!
3. **Step 3: Enable B4 and Show Autonomous Recovery (0:50 - 1:20)**:
   - Switch controller to **B4 (Full Safety Loop)** and click **⚠️ Inject eMBB Surge**. Advance with **+50s** to tick 250.
   - Show the **Safety Pre-Check Panel**:
     - Diagnosis: `cross_slice_contention` ($100\%$ confidence).
     - Digital Twin Pre-Check: Candidate $+5\%$ rejected ($12.16\text{ ms} > 10\text{ ms}$); candidate $+10\%$ accepted ($7.27\text{ ms} \le 10\text{ ms}$).
     - Action Applied: URLLC allocation shifted to $35\%$.
     - Result: URLLC latency safely restored to $\approx 6.6\text{ ms}$!
4. **Step 4: Demonstrate Flash Crowd Handling (1:20 - 1:40)**:
   - Click **🔵 Inject Flash Crowd**. Advance to tick 300.
   - Point out that the system accurately diagnoses `traffic_overload` ($98.9\%$ confidence) and does NOT punish real users as if they were DDoS attackers.
5. **Step 5: Demonstrate Safety Abstention (1:40 - 2:00)**:
   - Click **🟣 Inject Unknown IoT Storm**. Advance to tick 250.
   - Show the red **SAFETY ABSTENTION** banner: The system detects the registration failure spike, identifies the condition as `unknown`, and safely abstains and escalates to human engineers rather than making unverified changes.

---

## 4. How the Code Fits Together

```
src/sliceguard/
  ├── app.py                Streamlit dashboard with live charts, event buttons, and results tab
  ├── simulator.py          Provides closed-loop step execution and state tracking
  ├── controller.py         Executes B1..B4 controller logic per tick
  ├── twin.py               Provides real-time predictive pre-checking
  └── diagnosis.py          Provides evidence evaluation and confidence badges
results/
  ├── summary.csv           Empirical benchmark data loaded into the Results Tab
  └── figures/              Embedded benchmark visualization plots
```

---

## 5. Quiz (Test Your Understanding)

1. **Why is the "SIMULATION PROTOTYPE" label prominently displayed on the dashboard?**
2. **What happens under the hood when a user clicks "+10s" in the dashboard?**
3. **How does the dashboard demonstrate the difference between B1 (No Action) and B4 (Full Safety)?**
4. **Why is it essential that the dashboard runs fully offline?**
5. **Where does the data in the "Results Benchmark" tab come from?**

<details>
<summary><b>Click here to view Quiz Answers</b></summary>

1. *In accordance with honest engineering rules: we must never present simulation data as if it were measured on a live commercial carrier network or claim integration with vendor hardware.*
2. *The dashboard calls `step_sim(10)`, advancing the mathematical 3-slice simulator by 10 ticks while allowing the active controller (B1-B4) to monitor telemetry, evaluate pre-checks, and apply actions closed-loop.*
3. *Under B1, an eMBB surge causes persistent SLA degradation (latency stays at ~31ms). Under B4, the dashboard shows the anomaly detection, causal diagnosis, twin pre-check step rejection/selection, and dynamic capacity reallocation restoring latency to ~6.6ms.*
4. *To ensure 100% reliable demo execution during live hackathon presentations and judge interviews where conference Wi-Fi or cloud services may be unavailable or slow.*
5. *Directly from `results/summary.csv`, which was generated by running the 30-seed evaluation runner (`python -m sliceguard.evaluate`).*
</details>

---

## 6. How a Telecom Judge Might Attack This Phase & How to Answer

> **Judge Attack:** *"Your dashboard looks like a nice UI demo, but is this just an animation or is real mathematical simulation and AI running behind the scenes?"*

**Your Confident & Honest Answer:**
> *"Every single data point displayed on this dashboard is computed live in real-time by our mathematical simulation and machine learning models:*
> *1. When you advance the clock, our `Simulator` executes the full $M/M/1$ cross-slice coupling equations, adds Gaussian noise, and simulates packet loss.*
> *2. The `AnomalyDetector` runs real rolling feature extraction through a trained Isolation Forest model.*
> *3. The `DiagnosisEngine` evaluates actual telemetry evidence propositions.*
> *4. The `DigitalTwin` executes live Random Forest inference to predict post-action latency before committing changes.*
> *You can change the random seed or adjust `config.yaml` parameters right now, and the entire physical dynamics and AI decisions will adapt live."*

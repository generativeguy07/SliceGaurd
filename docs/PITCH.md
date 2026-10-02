# SliceGuard-Lite: Presentation Pitch & Demo Guide

**Shark Tank Theme**: AI in Telecom / Autonomous Networks  
**Tagline**: *Autonomous networks need AI that proves an action is safe before it acts.*

---

## 🎯 Part 1: Slide Presentation Outline (6 Slides)

### Slide 1: The Problem — When Critical Slices Collide
- **Visual**: A split screen showing an ambulance emergency telemetry feed alongside a user streaming 4K video.
- **Key Points**:
  - 5G network slicing promises isolation between broadband (eMBB) and mission-critical (URLLC) services.
  - In practice, slices share physical baseband processors, radio resource blocks, and buffer queues.
  - When video traffic surges, buffer bloat and cross-slice contention cause URLLC latency to spike from $6\text{ ms}$ to $>30\text{ ms}$, breaching strict contractual SLAs.
- **Speaker Note**: *"5G promises dedicated virtual lanes, but they share the same physical highway. When video downloads surge, emergency ambulances get stuck in traffic."*

---

### Slide 2: The Gap — The Danger of Unchecked AI Automation
- **Visual**: A comparison box: Dumb Thresholds vs. Hallucinating Black-Box AI.
- **Key Points**:
  - **Static Thresholds (B2)**: Blindly shift capacity without diagnosing root cause (cannot isolate DDoS attacks or handle novel faults).
  - **Unchecked AI / LLMs**: Black-box neural nets and LLMs can hallucinate unsafe commands, violate capacity limits, or act on noisy sensor glitches.
  - **The Missing Link**: Network operators cannot trust AI closed-loop control unless the AI can **prove an action will restore the SLA before it executes**.
- **Speaker Note**: *"Operators today don't trust closed-loop AI because it acts like a black box. If an AI hallucinates a bad configuration, it can take down an entire cell tower."*

---

### Slide 3: The Solution — The SliceGuard-Lite Safety Loop
- **Visual**: The 5-stage pipeline diagram:
  1. *Unsupervised Detector* (Isolation Forest + $3$-of-$5$ Persistence)
  2. *Causal Diagnosis Engine* (Evidence propositions + Confidence scoring)
  3. *Policy Validator* (Hard deterministic invariant firewall)
  4. *Digital Twin Pre-Check* (Predictive "what-if" regression before acting)
  5. *Confidence-Based Abstention* (Safe fallback to human operators when uncertain)
- **Speaker Note**: *"SliceGuard-Lite introduces a deterministic safety loop: we detect deviations, diagnose root cause, validate policy limits, and simulate the outcome on an approximate Digital Twin before touching the live network."*

---

### Slide 4: Empirical Tournament — 960 Multi-Seed Benchmark Runs
- **Visual**: Bar chart of SLA Violations & Efficiency Tradeoff across 30 seeds.
- **Key Points**:
  - **eMBB Surge**: B4 autonomously restores URLLC latency to $7.6\text{ ms}$ ($\le 10\text{ ms}$ SLA).
  - **DDoS Attack**: Accurately diagnoses `security_anomaly` and isolates attack traffic ($50.5\%$ throughput filtering).
  - **Flash Crowd**: Accurately diagnoses `traffic_overload` ($98.9\%$ confidence) and protects legitimate users without treating them as attackers.
  - **Unseen IoT Storm**: Triggers $100\%$ safety abstention and alerts humans.
- **Speaker Note**: *"We benchmarked four controllers across 30 random seeds. B4 safely recovers SLAs across surges and attacks, while achieving 100% safety abstention on unseen zero-day storms."*

---

### Slide 5: Live Demonstration
- *(Switch to live Streamlit dashboard for the 2-minute demonstration flow detailed below)*.

---

### Slide 6: Honest Limitations & Future Roadmap
- **Visual**: Transparent Roadmap table (Current Prototype vs. Future Evolution).
- **Key Points**:
  - **Current Prototype**: M/M/1 mathematical queuing model, synthetic telemetry, offline execution.
  - **Honest Tradeoff**: B4 accepts a $2\text{--}3$ second persistence delay to eliminate false alarms and flapping.
  - **Next Steps**: Porting the safety loop to an O-RAN Near-RT RIC (xApp architecture) interfacing with an ns-3 or OpenAirInterface 5G simulator.
- **Speaker Note**: *"We are completely transparent: this is an algorithmic proof-of-concept. Our next milestone is deploying this safety loop as an O-RAN xApp on top of an open-source 5G core."*

---

## ⏱️ Part 2: Word-for-Word 2-Minute Live Demo Script

**Setup**: Open terminal and run `streamlit run src/sliceguard/app.py`. Open browser to `http://localhost:8501`.

```text
[0:00 - 0:25] INTRODUCTION & NORMAL BASELINE
"Good morning judges. Here is SliceGuard-Lite running live in our offline dashboard.
Notice our three slices: eMBB (video downloads) at 60%, URLLC (emergency medical telemetry) at 25%, and mMTC (IoT smart meters) at 15%.
Under normal traffic, our URLLC latency rests safely at 6.0 ms, well below our 10 ms SLA limit."
[Action: Click "+50s" twice to advance to tick 100.]

[0:25 - 0:50] INJECT SURGE ON PASSIVE BASELINE (B1)
"Now, let's switch to a passive network baseline (B1) and inject an eMBB bandwidth surge at tick 200.
Watch what happens: video downloads jump to 70%, buffers get clogged, and cross-slice interference causes URLLC latency to skyrocket to 30 ms!
Because B1 has no automation, the emergency slice stays in severe SLA violation for the entire 250-second incident."
[Action: Select 'B1_no_action', click '⚠️ Inject eMBB Surge', advance with '+50s' to tick 250.]

[0:50 - 1:20] AUTONOMOUS RECOVERY WITH B4 & TWIN PRE-CHECK
"Now let's switch to SliceGuard-Lite's B4 Safety Loop and inject the exact same surge.
Notice what happens:
1. At tick 203, our Isolation Forest detector flags an incident with a 3-of-5 persistence filter.
2. Our explainable diagnosis engine identifies 'cross_slice_contention' with 100% confidence.
3. Crucially, look at the Digital Twin Pre-Check panel: it tests a candidate +5% shift, predicts that latency would remain at 12.16 ms (violating the SLA), and REJECTS it. It then tests a +10% shift, predicts 7.27 ms latency, and ACCEPTS it!
4. It shifts URLLC allocation to 35%, and latency instantly recovers to 6.6 ms. The SLA is saved!"
[Action: Select 'B4_full', click '⚠️ Inject eMBB Surge', advance to tick 250.]

[1:20 - 1:40] FLASH CROWD DISTINCTION (NO HARMFUL ACTIONS)
"Next, what happens during a legitimate Flash Crowd?
A dumb system might mistake high traffic for a DDoS attack and block legitimate users.
SliceGuard-Lite inspects the packet pattern anomaly ratio, diagnoses 'traffic_overload' with 98.9% confidence, and applies mild rate limiting rather than destructive isolation."
[Action: Click '🔵 Inject Flash Crowd', advance to tick 300.]

[1:40 - 2:00] ZERO-DAY ANOMALY & SAFETY ABSTENTION
"Finally, what happens when an unseen zero-day event hits, like an unmodeled IoT registration storm?
Watch the red banner: the detector spots the spike, but because no known rule matches, our system refuses to guess.
It ABSTAINS and immediately escalates to human operators with an auditable telemetry log.
That is the essence of SliceGuard-Lite: AI that proves an action is safe before it acts. Thank you!"
[Action: Click '🟣 Inject Unknown IoT Storm', advance to tick 250.]
```

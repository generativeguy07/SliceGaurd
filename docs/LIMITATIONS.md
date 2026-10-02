# Honest Engineering Limitations: SliceGuard-Lite

In accordance with telecom engineering rigor and project guidelines, this document explicitly details the architectural simplifications, known failure modes, and benchmark tradeoffs where SliceGuard-Lite's full safety controller (B4) is outperformed by simpler heuristics.

---

## 1. Benchmark Tradeoffs: Where B4 is Not the Best

Our 30-seed empirical evaluation ([results/summary.csv](file:///home/maurya/Downloads/sliceguard-antigravity/results/summary.csv)) reveals specific operational tradeoffs:

### 1.1 Detection Latency Tradeoff vs. Blind Reactive Thresholds (B2 vs. B4)
- **Measured Result**: During an abrupt eMBB surge or DDoS flood, **B2 (Static Threshold)** records fewer initial SLA violation ticks ($\approx 1\text{ tick}$) than **B4** ($\approx 22\text{ ticks}$).
- **Root Cause**: B2 has zero intelligence—the instant a single telemetry reading exceeds $10\text{ ms}$, it immediately fires a $+10\%$ reallocation. B4, by contrast, enforces an **unsupervised Isolation Forest** with rolling-window features ($\text{window}=10$) and a **$3$-of-$5$ persistence filter** to filter out transient noise spikes before triggering.
- **Why This Tradeoff Exists**: In real networks, blind reactive triggers cause catastrophic "flapping" (rapid oscillations and false triggers on noisy radio channels). B4 trades $\approx 2\text{--}3$ seconds of initial detection delay in exchange for robust noise immunity and causal certainty.

### 1.2 Protection Cost (eMBB Throughput Degradation)
- **Measured Result**: On eMBB surges, B4 incurs higher eMBB throughput loss ($\approx 33.8\%$) compared to B3 ($\approx 21.1\%$) because the Digital Twin pre-check rejects undersized $+5\%$ steps and enforces $+10\%$ to $+15\%$ shifts to strictly guarantee the sub-$10\text{ ms}$ SLA.
- **Tradeoff**: B4 prioritizes strict URLLC survival over broadband throughput.

---

## 2. Modeling & Simulation Simplifications

1. **Queuing-Theoretic Network Model**:
   - The simulation uses an M/M/1-derived nonlinear queuing delay equation with cross-slice coupling ($\gamma = 0.5$) and capacity conservation ($\sum A_s = 100\%$).
   - It does not simulate 3GPP Layer-1 physical radio waveforms, OFDM subcarrier fading, or beamforming channels.
2. **Synthetic Telemetry Stream**:
   - Telemetry is generated at 1-second ticks with multiplicative Gaussian noise ($\sigma = 0.04$) and Bernoulli packet dropouts ($p = 0.01$).
   - Real OAM telemetry systems may exhibit asynchronous timestamps, multi-second collection delays, and varying counter granularities.
3. **Digital Twin as an Approximation**:
   - The Digital Twin is an ML regressor trained on synthetic runs with perturbed parameters ($\pm 15\%$ base latency, $\pm 15\%$ coupling, extra noise).
   - While it achieves an MAE of $\approx 0.70\text{ ms}$ on test data, extreme domain shifts outside its training distribution can introduce prediction errors.

---

## 3. Scope & Deployment Limitations

1. **No Vendor Product Claims**:
   - SliceGuard-Lite is a standalone research prototype and proof-of-concept. It does not integrate directly with Nokia AVA, Nokia NetAct, or proprietary vendor controllers.
2. **Fixed Action Catalog**:
   - The controller selects only from the approved 6-action menu. It cannot invent new routing protocols or deploy dynamic virtual network functions (VNFs) on the fly.
3. **Deterministic Rule Ruleset**:
   - While highly explainable and auditable, the rule-based diagnosis engine relies on predefined thresholds and depends on abstention when encountering unmodeled traffic profiles (such as the unseen mMTC storm).

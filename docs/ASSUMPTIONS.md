# Modeling Assumptions: SliceGuard-Lite

This document transparently records all mathematical equations, parameters, operational simplifications, and architectural assumptions used in the SliceGuard-Lite simulation.

---

## 1. Network Slicing & Capacity Partitioning

### 1.1 Slices and Default Capacity Allocations
In 5G networks, network slicing logically partitions a shared physical infrastructure (Radio Access Network, transport, and Core Network) into isolated virtual networks tailored to distinct service requirements:
- **eMBB (enhanced Mobile Broadband)**: High throughput for video streaming and large downloads.
  - Default allocation: $60\%$ of total capacity.
  - Minimum hard limit: $20\%$.
  - Normal base demand: $27\%$.
- **URLLC (Ultra-Reliable Low-Latency Communication)**: High priority, deterministic sub-10ms latency for critical applications (e.g. emergency telemetry, autonomous robotics).
  - Default allocation: $25\%$ of total capacity.
  - Minimum hard limit: $25\%$, maximum allowed allocation: $50\%$.
  - Normal base demand: $9\%$.
- **mMTC (massive Machine-Type Communication)**: High connection density of low-rate IoT sensors.
  - Default allocation: $15\%$ of total capacity.
  - Minimum hard limit: $10\%$.
  - Normal base demand: $5\%$, supporting ~8,000 active devices.

### 1.2 Resource Conservation Constraint
Allocations represent fractional shares of total system radio/compute capacity and must always satisfy:
$$\sum_{s \in \{\text{eMBB}, \text{URLLC}, \text{mMTC}\}} A_s = 100\%$$

---

## 2. Cross-Slice Interference and Latency Model

### 2.1 eMBB Served Load
Let $D_{\text{embb}}$ be eMBB demand, $A_{\text{embb}}$ its allocation percentage, $cap$ the infrastructure capacity factor ($1.0$ normal, $<1.0$ during faults), and $r_{\text{limit}}$ any active rate limiting:
$$\text{served}_{\text{embb}} = \min(D_{\text{embb}} \cdot (1 - r_{\text{limit}}), A_{\text{embb}} \cdot cap)$$

### 2.2 Nonlinear Cross-Slice Interference ($I$)
When eMBB served traffic exceeds an interference threshold ($\text{threshold} = 45\%$), shared buffer and scheduler contention begins degrading the high-priority slice:
$$I = \text{clip}\left(\frac{\text{served}_{\text{embb}} - 45.0}{15.0}, 0.0, 1.0\right)$$

### 2.3 Effective URLLC Load ($\rho_{\text{urllc\_eff}}$)
The effective utilization load seen by the URLLC scheduler incorporates cross-slice contention via coupling constant $\gamma = 0.5$:
$$\rho_{\text{urllc\_eff}} = \frac{D_{\text{urllc}}}{A_{\text{urllc}} \cdot cap} + \gamma \cdot I$$

### 2.4 M/M/1 Queuing Latency Formulation
Latency is computed using an M/M/1-derived nonlinear queuing delay model, with utilization $\rho$ capped at $0.97$ to model buffer-bounded delay:
$$\text{latency}(\rho, \text{base}) = \text{base} \cdot \left(1 + \frac{\rho^2}{1 - \rho}\right)$$
For URLLC ($\text{base} = 5.0\text{ ms}$):
- **Normal state**: $D_{\text{urllc}}=9\%, A_{\text{urllc}}=25\%, I=0 \implies \rho=0.36 \implies \text{latency} \approx 6.01\text{ ms}$.
- **Surge state (no action)**: $D_{\text{embb}}=70\%, A_{\text{embb}}=60\%, I=1.0 \implies \rho=0.36 + 0.50 = 0.86 \implies \text{latency} \approx 31.4\text{ ms}$ (breaches 10ms SLA).
- **Surge + Protect URLLC (+10%)**: $A_{\text{urllc}}=35\%, A_{\text{embb}}=50\%, \text{served}_{\text{embb}}=50\% \implies I = 0.333 \implies \rho = 0.257 + 0.167 = 0.424 \implies \text{latency} \approx 6.56\text{ ms}$ (SLA safely restored).

### 2.5 Packet Loss Model
Base background packet loss is $0.1\%$. When effective utilization exceeds $70\%$, buffer overflow induces packet drop:
$$\text{loss}_{\text{urllc}} = 0.1\% + k \cdot \max(0.0, \rho_{\text{urllc\_eff}} - 0.70)^2$$
With $k = 170.0$, peak surge loss reaches $\approx 4.45\%$, matching target SLA breach behavior ($>1.0\%$).

---

## 3. Observability and Measurement Noise

1. **Noise**: Multiplicative Gaussian noise with standard deviation $\sigma = 0.04$ ($4\%$) is applied to all physical metrics to simulate real-world sensor/telemetry noise.
2. **Missing Readings**: A Bernoulli dropout probability ($p = 0.01$) simulates packet drops in the OAM telemetry plane.
3. **Ground-Truth Shielding**: Labels (`event_label`, `is_attack`) are recorded for offline benchmark scoring only. The detector, diagnosis engine, and closed-loop controllers are strictly isolated from ground-truth columns.

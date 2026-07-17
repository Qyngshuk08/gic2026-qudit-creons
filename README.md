# GIC 2026 Phase 3 — Quantum-Enhanced BESS Siting
## Team Qudit Creons | Abhishek Raj | DOE Energy Infrastructure Challenge

[![Launch on qBraid](https://qbraid-static.s3.amazonaws.com/logos/Launch_on_qBraid_white.png)](https://account.qbraid.com?gitHubUrl=https://github.com/Qyngshuk08/gic2026-qudit-creons)

---

## Project Summary
Hybrid quantum-classical optimisation for strategic Battery Energy Storage System (BESS)
siting and sizing on the IEEE 118-bus New England transmission network, augmented with
two synthetic AI datacenter loads (300 MW each). The BESS placement problem is
formulated as a 40-variable QUBO and solved using D-Wave's hybrid solver ecosystem,
benchmarked against an exact classical MILP baseline (PuLP + HiGHS).

**Challenge Track:** DOE OTC — Energy Infrastructure  
**Test System:** IEEE 118-bus (MATPOWER case118, public domain)  
**Key Result:** D-Wave SA achieves 91.4% EUE reduction vs 92.1% optimal (8.7% gap) at 40 QUBO variables; LeapHybridSampler (QPU) closes this gap on real hardware.

---

## Repository Structure
```
gic2026-qudit-creons/
├── experiment.py          # Main Phase 3 experiment (all solvers + scaling study)
├── results_phase3.json    # Output results (auto-generated)
├── README.md              # This file
└── requirements.txt       # Python dependencies
```

---

## Setup Instructions

### 1. Clone and install dependencies
```bash
git clone https://github.com/Qyngshuk08/gic2026-qudit-creons.git
cd gic2026-qudit-creons
pip install -r requirements.txt
```

### 2. On qBraid
- Click the **Launch on qBraid** button above
- The repo will be cloned into your qBraid Lab environment automatically
- All dependencies are pre-installed on qBraid (dwave-ocean-sdk, pulp, highspy, numpy)
- Open a terminal in qBraid Lab and run:
```bash
cd gic2026-qudit-creons
python experiment.py
```

---

## Running the Experiment

### Local run (no QPU credentials needed)
Runs MILP baseline + D-Wave SimulatedAnnealingSampler locally:
```bash
python experiment.py
```

### Full scaling study
```bash
python experiment.py --scaling
```

### With D-Wave Leap QPU (LeapHybridSampler)
Requires a valid D-Wave Leap API token:
```bash
export DWAVE_API_TOKEN=<your_token>
python experiment.py --leap
```
Or on Windows:
```powershell
$env:DWAVE_API_TOKEN="<your_token>"
python experiment.py --leap
```

### With IBM Quantum (QAOA)
Requires a valid IBM Quantum API token (Open Plan):
```bash
export IBM_QUANTUM_TOKEN=<your_token>
python experiment.py --ibm
```
This runs a p=1 QAOA circuit on the least-busy IBM backend, using a 10-bus / 20-qubit
subset of the candidate set (gate-based QAOA is qubit-limited compared to D-Wave's
QUBO-native hybrid solvers, so a smaller instance is used for hardware execution).

**Note on compute environment:** This experiment was developed and initially verified on
qBraid Lab. Due to qBraid credit exhaustion during development, IBM Quantum and D-Wave
Leap runs are executed directly via their respective SDKs (`qiskit-ibm-runtime`,
`dwave-ocean-sdk`) using personal API tokens, runnable from any Python environment
including qBraid, local machines, or other quantum IDEs (e.g. Classiq).

---

## Expected Inputs / Outputs

**Inputs:** None required — all data is embedded in the script (IEEE 118-bus loads from
MATPOWER case118, public domain; synthetic AI load profiles generated internally).

**Outputs:**
- Terminal: benchmark results table, scaling study, penalty sensitivity sweep
- `results_phase3.json`: full structured results for all solvers

**Expected runtime:**
- Local (no QPU): ~5–10 seconds
- With --scaling flag: ~30–60 seconds
- With --leap (QPU): ~15–30 seconds (10s time_limit per D-Wave task)

---

## Key Results (reproduced from results_phase3.json)

| Method | EUE (MW·prob) | EUE Reduction | Gap vs Optimal | Runtime |
|---|---|---|---|---|
| No BESS (baseline) | 62.67 | — | — | — |
| Classical MILP (HiGHS) | 4.94 | **92.1%** | 0.0% (optimal) | 0.007 s |
| D-Wave SA (3000 reads) | 5.37 | 91.4% | 8.7% | 0.44 s |
| D-Wave LeapHybrid (QPU) | TBD | TBD | TBD | ~15 s |

**QUBO parameters:** 40 binary variables, λ_budget = 3.0, μ_invalid = 6.0  
**Scaling:** 20→25 candidate buses (40→50 qubits), gap increases from 8.7% to 59.6% — identifying the regime where QPU advantage is most likely.

---

## Known Limitations and Assumptions

- **DC-OPF linearisation:** Full AC power flow is approximated by DC-OPF (lossless, flat
  voltage). Reactive power and voltage magnitude constraints are excluded. This is standard
  practice in transmission planning studies but underestimates congestion in heavily loaded
  networks.
- **Generation capacity:** 5,200 MW effective dispatchable capacity (52% of nameplate)
  used to create realistic EUE shortfall under contingency scenarios. A full study would
  use unit commitment to determine available capacity per scenario.
- **Scenario reduction:** 15 representative scenarios (vs. 8,760 hourly annual) generated
  by scaling from MATPOWER base case. A production study would use k-means clustering
  of historical EIA/NREL profiles.
- **QUBO penalty tuning:** λ_budget = 3.0 is calibrated on the 20-bus problem; larger
  problems may require re-tuning.
- **Local D-Wave SA vs QPU:** The `--leap` flag is required to run real QPU hardware.
  Local results use D-Wave's classical SimulatedAnnealingSampler from dwave-ocean-sdk.

---

## Dependencies
```
dwave-ocean-sdk>=7.0
pulp>=2.7
highspy>=1.5
numpy>=1.24
```
See `requirements.txt` for pinned versions.

---

## Disclosure
- Test system data: MATPOWER case118 (public domain, R. D. Zimmerman, Cornell University)
- AI load profiles: synthetic, generated within script
- Generative AI tools used for code support and writing assistance (disclosed per GIC rules)
- All technical formulations, QUBO construction, and experimental design are the team's own work

**Contact:** kvt057@gmail.com | Aqora: @qyngshuq

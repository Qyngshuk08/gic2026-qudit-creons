# GIC 2026 Phase 3 — Quantum-Enhanced BESS Siting
## Team Qudit Creons | Abhishek Raj | DOE Energy Infrastructure Challenge

[![Launch on qBraid](https://qbraid-static.s3.amazonaws.com/logos/Launch_on_qBraid_white.png)](https://account.qbraid.com?gitHubUrl=https://github.com/Qyngshuk08/gic2026-qudit-creons)

---

## Project Summary
Hybrid quantum-classical optimisation for strategic Battery Energy Storage System (BESS)
siting and sizing on the IEEE 118-bus New England transmission network, augmented with
two synthetic AI datacenter loads (300 MW each). The BESS placement problem is
formulated as a 40-variable QUBO and solved through **three architecturally distinct
quantum/hybrid execution paths** — D-Wave LeapHybridSampler, raw D-Wave QPU (direct
annealing), and IBM Quantum QAOA+COBYLA — all benchmarked against an exact classical
MILP baseline (PuLP + HiGHS) and a 10-seed classical SA statistical baseline.

**Challenge Track:** DOE OTC — Energy Infrastructure
**Test System:** IEEE 118-bus (MATPOWER case118, public domain)
**Key Result:** D-Wave LeapHybridSampler achieves a **1.73% optimality gap** on real QPU
hardware — the best result of any method except exact MILP, and better than the best
classical heuristic result obtained (2.66%, best-of-10 simulated annealing seeds).

---

## Repository Structure
```
gic2026-qudit-creons/
├── experiment.py           # Main Phase 3 experiment (all solvers, QPU, scaling study)
├── results_phase3_v4.json  # Output results (auto-generated)
├── README.md               # This file
├── requirements.txt        # Python dependencies
├── visualizations/         # Standalone chart-generation scripts (see below)
└── images/                 # Generated chart outputs (300 DPI, print-ready)
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
- Open a terminal in qBraid Lab and run:
```bash
cd gic2026-qudit-creons
pip install -r requirements.txt
python experiment.py
```

---

## Running the Experiment

### Local run (no credentials needed)
Runs MILP baseline + D-Wave SimulatedAnnealingSampler across 10 seeds + economic analysis:
```bash
python experiment.py
```

### Full scaling study
```bash
python experiment.py --scaling
```

### D-Wave LeapHybridSampler (hybrid: classical decomposition + QPU)
Requires a valid D-Wave Leap API token:
```bash
export DWAVE_API_TOKEN=<your_token>
python experiment.py --leap
```

### D-Wave raw QPU (direct annealing, no decomposition)
Submits the full 40-variable QUBO directly to physical qubits via minor-embedding:
```bash
export DWAVE_API_TOKEN=<your_token>
python experiment.py --qpu --qpu-reads 200
```
If the run reports low feasibility or high chain-break fraction, increase chain strength:
```bash
python experiment.py --qpu --qpu-reads 300 --qpu-chain-mult 2.0
```
Chain strength is computed automatically via Ocean SDK's `uniform_torque_compensation`
(see Known Limitations below for why this matters for this specific QUBO).

### IBM Quantum (QAOA + COBYLA)
Requires a valid IBM Quantum API token (Open Plan):
```bash
export IBM_QUANTUM_TOKEN=<your_token>
python experiment.py --ibm --ibm-iters 25
```
Runs a p=1 QAOA circuit with a genuine COBYLA parameter-optimisation loop (one real QPU
job per iteration) on a 10-bus / 20-qubit subset of the candidate set. Each iteration
submits a real hardware job — budget QPU time accordingly (25 iterations ≈ 7 minutes).

### Run everything together
```bash
export DWAVE_API_TOKEN=<your_dwave_token>
export IBM_QUANTUM_TOKEN=<your_ibm_token>
python experiment.py --leap --qpu --ibm --ibm-iters 25 --scaling
```

**Note on compute environment:** This experiment was developed and initially verified on
qBraid Lab. Due to qBraid credit exhaustion during development, D-Wave and IBM Quantum
runs are executed directly via their respective SDKs (`dwave-ocean-sdk`,
`qiskit-ibm-runtime`) using personal API tokens — fully portable to qBraid, a local
machine, or any Python environment with network access to both platforms.

---

## Expected Inputs / Outputs

**Inputs:** None required — all data is embedded in the script (IEEE 118-bus loads from
MATPOWER case118, public domain; synthetic AI load profiles generated internally).

**Outputs:**
- Terminal: benchmark results table, chain-strength diagnostics, scaling study
- `results_phase3_v4.json`: full structured results for all solvers, including embedding
  diagnostics (physical qubits used, chain lengths, chain-break fraction, feasibility rate)

**Expected runtime:**
- Local only (MILP + SA, no tokens): ~5–10 seconds
- `--scaling`: +30–60 seconds
- `--leap`: +2–15 seconds (10s D-Wave time_limit)
- `--qpu`: +10–20 seconds (200 reads)
- `--ibm --ibm-iters 25`: +5–8 minutes (26 sequential real QPU jobs)

---

## Key Results (reproduced from results_phase3_v4.json)

| Method | EUE (MW·prob) | EUE Reduction | Gap vs Optimal | Notes |
|---|---|---|---|---|
| No BESS (baseline) | 62.67 | — | — | — |
| Classical MILP (HiGHS) | 4.94 | **92.12%** | 0.0% (proven optimal) | 0.01–0.04 s |
| **D-Wave LeapHybridSampler (QPU)** | **5.03** | **91.98%** | **1.73%** | Best quantum result; real QPU |
| D-Wave SA — best of 10 seeds | 5.07 | 91.91% | 2.66% | Best classical heuristic |
| D-Wave raw QPU (direct anneal) | 5.24 | 91.64% | 6.05% | No decomposition; 178 physical qubits, 85/200 reads feasible |
| D-Wave SA — mean of 10 seeds | 6.17 | 90.16% | 24.80% | Single-seed runs are unreliable — see std |
| IBM QAOA + COBYLA (ibm_fez) | 9.45 | 84.92% | 50.06% | 25 iterations; see extraction-sensitivity finding below |

**QUBO parameters:** 40 binary variables (20 candidate buses × 2 capacity bits).
λ_budget derived analytically (λ_min = 0.1595, applied λ = 0.2392 with 1.5x safety
margin) rather than tuned empirically — see `derive_lambda_bound()` in experiment.py.

**Chain-strength finding:** the first raw-QPU run used default chain strength and
returned **zero** budget-feasible solutions across 200 reads (chain-break fraction 0.20).
Switching to explicit `uniform_torque_compensation` chain strength (computed: 26,284.05)
fixed this completely — chain-break fraction dropped to 0.0 and feasibility rose to
85/200 (42.5%). This before/after is retained in the results JSON.

**IBM QAOA finding:** the COBYLA loop ran its full 25-iteration budget (26 real QPU
jobs, job IDs logged), but the per-iteration objective trace shows no convergence and
the final answer is unchanged from an earlier unoptimised single-shot run. Diagnosis:
at p=1, best-of-2048-shots extraction is not sensitive enough to surface small COBYLA
parameter improvements. See "Known Limitations" below.

**Scaling study:** across 10 → 25 candidate buses (20 → 50 qubits), classical SA's mean
gap is non-monotonic (92.4% → 21.5% → 34.2% → 59.6%), identifying the 40-qubit region as
where the QUBO landscape is best-conditioned for this problem's penalty structure.

---

## Visualizations

Seven standalone, enterprise-styled chart scripts (`visualisation/scripts/`) generate
the figures used in the Phase 3 write-up, each producing a 300 DPI print-ready PNG
(`visualisation/images/`) from the real experimental results above. Each script is
fully self-contained and runnable independently:

```bash
cd visualisation/scripts
python benchmark_comparison.py   # -> ../images/benchmark_comparison.png
```

| Script | Image | Shows |
|---|---|---|
| [`visualisation/scripts/benchmark_comparison.py`](visualisation/scripts/benchmark_comparison.py) | [`visualisation/images/benchmark_comparison.png`](visualisation/images/benchmark_comparison.png) | All 6 methods — EUE reduction and optimality gap side-by-side |
| [`visualisation/scripts/scaling_study.py`](visualisation/scripts/scaling_study.py) | [`visualisation/images/scaling_study.png`](visualisation/images/scaling_study.png) | Qubits vs. gap; non-monotonic scaling finding |
| [`visualisation/scripts/qaoa_convergence.py`](visualisation/scripts/qaoa_convergence.py) | [`visualisation/images/qaoa_convergence.png`](visualisation/images/qaoa_convergence.png) | Real 25-iteration IBM COBYLA trace with extraction-sensitivity diagnosis |
| [`visualisation/scripts/chain_strength_fix.py`](visualisation/scripts/chain_strength_fix.py) | [`visualisation/images/chain_strength_fix.png`](visualisation/images/chain_strength_fix.png) | Before/after: chain-break fraction 0.20→0.0, feasibility 0%→42.5% |
| [`visualisation/scripts/economic_analysis.py`](visualisation/scripts/economic_analysis.py) | [`visualisation/images/economic_analysis.png`](visualisation/images/economic_analysis.png) | CAPEX vs. annual outage-cost savings, with methodology caveat |
| [`visualisation/scripts/penalty_sensitivity.py`](visualisation/scripts/penalty_sensitivity.py) | [`visualisation/images/penalty_sensitivity.png`](visualisation/images/penalty_sensitivity.png) | λ_budget sweep vs. EUE, with analytical derivation annotated |
| [`visualisation/scripts/architecture_diagram.py`](visualisation/scripts/architecture_diagram.py) | [`visualisation/images/architecture_diagram.png`](visualisation/images/architecture_diagram.png) | Three-path hybrid quantum-classical architecture flowchart |

All figures are generated directly from the values in `results_phase3_v4.json` —
no fabricated or illustrative data. Regenerate all seven with:

```bash
cd visualisation/scripts
for f in *.py; do python "$f"; done
```

---

## Known Limitations and Assumptions

- **DC-OPF linearisation:** Full AC power flow is approximated by DC-OPF (lossless, flat
  voltage). Reactive power and voltage magnitude constraints are excluded. Standard
  practice for contingency screening, but not a substitute for full AC-OPF in production.
- **Contingency modelling:** N-1 and weather scenarios use documented generation-fraction
  scaling, not branch-level PTDF/LODF analysis. This would require verified IEEE 118-bus
  line impedance data not safely reproduced from memory within this project's timeline.
- **Generation capacity:** 5,200 MW effective dispatchable capacity is deliberately capped
  below peak load (4,842 MW) to create a demonstrable, benchmarkable shortfall. The
  resulting baseline EUE (~2.6% of annual energy unserved) is roughly 100–1000x larger
  than real NERC reliability targets (<0.01%). **This is a stylized construct for
  algorithm benchmarking, not a calibrated reliability study** — the economic/VOLL
  figures in `results_phase3_v4.json` illustrate methodology only and should not be read
  as investment guidance.
- **Coefficient dynamic range:** the QUBO mixes small objective-benefit coefficients
  (~0.001–5) with large penalty coefficients (~1000s from λ·cap² budget terms). This is
  harmless for exact/simulated solvers but requires explicit chain-strength tuning on
  real D-Wave QPU hardware (see Chain-strength finding above) and likely contributes to
  the raw-QPU path's 6.05% gap versus LeapHybrid's 1.73%.
- **IBM QAOA extraction sensitivity:** best-of-shots post-selection does not reliably
  track COBYLA's parameter search at p=1 (see IBM QAOA finding above). Recommended fix
  for future work: expectation-value scoring via EstimatorV2, or p≥2 circuits.
- **Raw-QPU feasibility rate:** only 42.5% of reads (85/200) satisfied the budget
  constraint even after chain-strength tuning. Production use would need more reads, a
  higher chain-strength multiplier, or QUBO reformulation to improve this.
- **Scenario reduction:** 15 representative scenarios (vs. 8,760 hourly annual) generated
  by scaling from MATPOWER base case. A production study would use k-means clustering
  of historical EIA/NREL profiles.
- **Capacity discretisation:** 3 tiers per bus (0/50/100 MW) limits siting resolution.

---

## Dependencies
```
dwave-ocean-sdk>=7.0
qiskit>=1.0
qiskit-ibm-runtime>=0.20
pulp>=2.7
highspy>=1.5
numpy>=1.24
scipy>=1.10
```
See `requirements.txt` for pinned versions.

---

## Disclosure
- Test system data: MATPOWER case118 (public domain, R. D. Zimmerman, Cornell University)
- Economic assumptions: NREL 2024 Annual Technology Baseline (BESS capex); DOE/LBNL
  Interruption Cost Estimate Calculator (Value of Lost Load)
- AI load profiles: synthetic, generated within script
- Generative AI tools used for documentation and writing assistance (disclosed per GIC rules)
- All technical formulations, QUBO construction, chain-strength diagnosis, and
  experimental design are the team's own work

**Contact:** kvt057@gmail.com | Aqora: @qyngshuq

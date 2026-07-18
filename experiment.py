"""
GIC 2026 — Phase 3 Experiment (Enterprise-Grade, v3 — adds raw QPU)
Team: Qudit Creons | Abhishek Raj
Challenge: DOE OTC — Quantum-Enhanced Strategic Siting of Energy Storage & Microgrids

NEW IN v3:
  - Raw D-Wave QPU sampling (DWaveSampler + EmbeddingComposite) in addition to the
    LeapHybridSampler already used. This is architecturally different: LeapHybridSampler
    decomposes the problem classically and only sends part of it to the QPU; the raw
    QPU path (--qpu flag) submits the full 40-variable QUBO directly to physical qubits
    via minor-embedding, and anneals it end-to-end on hardware. This exercises D-Wave's
    unused "Direct QPU Usage" allocation (previously 0 ms) rather than only Hybrid Usage.
  - Reports genuine hardware diagnostics unique to raw QPU: physical qubit count used,
    chain length distribution, chain-break fraction, and per-read energy histogram --
    none of which are visible when using the hybrid solver.

CHANGES CARRIED FROM v2:
  1. Economic layer: capital cost + Value of Lost Load (VOLL) monetization, payback period.
  2. Statistical rigor: D-Wave SA run across N_SEEDS independent trials (mean/std/best/worst).
  3. Analytical penalty bound: lambda_budget derived from a provable sufficient condition.
  4. IBM QAOA: COBYLA optimization loop (see README for known extraction-sensitivity finding).

EXPLICITLY NOT ATTEMPTED (documented, not silently skipped):
  - Full AC-OPF, exact branch-level PTDF contingency analysis, multi-year capacity expansion.

Usage:
  python experiment.py                       # local: MILP + D-Wave SA (multi-seed) + cost layer
  python experiment.py --leap                 # + D-Wave LeapHybridSampler (needs DWAVE_API_TOKEN)
  python experiment.py --qpu                  # + raw D-Wave QPU sampling (needs DWAVE_API_TOKEN)
  python experiment.py --qpu --qpu-reads 200   # control QPU sample count
  python experiment.py --ibm --ibm-iters 25    # + IBM QAOA+COBYLA (needs IBM_QUANTUM_TOKEN)
  python experiment.py --scaling               # + full scaling study
"""

import time, json, argparse, numpy as np, warnings
warnings.filterwarnings("ignore")

parser = argparse.ArgumentParser()
parser.add_argument("--leap",      action="store_true", help="Run LeapHybridSampler (needs DWAVE_API_TOKEN)")
parser.add_argument("--qpu",       action="store_true", help="Run raw QPU sampling (needs DWAVE_API_TOKEN)")
parser.add_argument("--qpu-reads", type=int, default=200, help="Number of anneal reads for raw QPU")
parser.add_argument("--qpu-solver", type=str, default=None, help="Specific QPU solver name (default: auto-select Advantage2)")
parser.add_argument("--ibm",       action="store_true", help="Run QAOA+COBYLA on IBM Quantum (needs IBM_QUANTUM_TOKEN)")
parser.add_argument("--ibm-iters", type=int, default=15, help="COBYLA max iterations for IBM QAOA")
parser.add_argument("--scaling",   action="store_true", help="Run full scaling study")
parser.add_argument("--seeds",     type=int, default=10, help="Number of random seeds for D-Wave SA statistics")
args, _ = parser.parse_known_args()

print("=" * 70)
print("GIC 2026 Phase 3 | Team Qudit Creons | DOE Energy Infrastructure")
print("IEEE 118-Bus BESS Siting — Enterprise-Grade Benchmark (v3: +Raw QPU)")
print("=" * 70)

# ─── 1. IEEE 118-BUS NETWORK ─────────────────────────────────────────────────
BASE_LOADS = {
    1:51, 2:20, 3:39, 4:39, 6:52, 7:19, 8:28, 11:70, 12:47, 13:34,
    14:14, 15:90, 16:25, 17:11, 18:60, 19:45, 20:18, 21:14, 22:10,
    23:7, 24:13, 27:71, 28:17, 29:24, 31:43, 32:59, 33:23, 34:59,
    35:33, 36:31, 39:27, 40:66, 41:37, 42:96, 43:18, 44:16, 45:53,
    46:28, 47:34, 48:20, 49:87, 50:17, 51:17, 52:18, 53:23, 54:113,
    55:63, 56:84, 57:12, 58:12, 59:277, 60:78, 62:77, 66:39, 67:28,
    70:66, 72:12, 73:6, 74:68, 75:47, 76:68, 77:61, 78:71, 79:39,
    80:130, 82:54, 83:20, 84:11, 85:24, 86:21, 88:48, 90:163, 91:10,
    92:65, 93:12, 94:30, 95:42, 96:38, 97:15, 98:34, 99:42, 100:37,
    101:22, 102:5, 103:23, 104:38, 105:31, 106:43, 107:50, 108:2,
    109:8, 110:39, 112:68, 113:6, 114:8, 115:22, 116:184, 117:20, 118:33
}
GEN_NOMINAL = 5200.0  # MW effective dispatchable (documented simplification, see README)

AI_LOADS = {49: 300.0, 80: 300.0}
for bus, load in AI_LOADS.items():
    BASE_LOADS[bus] = BASE_LOADS.get(bus, 0) + load

TOTAL_PEAK = sum(BASE_LOADS.values())
print(f"\nNetwork:          IEEE 118-bus (MATPOWER case118)")
print(f"AI loads added:   2 x 300 MW at Buses 49 & 80")
print(f"Total peak load:  {TOTAL_PEAK:.0f} MW | Gen capacity: {GEN_NOMINAL:.0f} MW")

CANDIDATE_BUSES_20 = [
    15, 27, 31, 34, 40, 42, 45, 49, 54, 55,
    59, 62, 70, 74, 77, 80, 90, 92, 100, 116
]
BESS_TIERS = [0, 50, 100]
BUDGET_MW  = 500
N_BITS     = 2
MU_INV     = 6.0

print(f"Candidates:       {len(CANDIDATE_BUSES_20)} buses -> {len(CANDIDATE_BUSES_20)*N_BITS} QUBO binary vars")
print(f"Budget:           {BUDGET_MW} MW | Tiers: {BESS_TIERS} MW\n")

# ─── 2. SCENARIOS ─────────────────────────────────────────────────────────────
SCENARIO_DEFS = [
    ("Peak Summer",        1.00, 1.00, 1.00, 0.06),
    ("Extreme AI Surge",   1.05, 1.15, 0.95, 0.04),
    ("High Load Weekday",  0.90, 0.95, 0.98, 0.10),
    ("Mid Load",           0.75, 0.85, 0.99, 0.15),
    ("Low Load Night",     0.55, 0.70, 1.00, 0.10),
    ("High Renewable",     0.80, 0.90, 0.95, 0.08),
    ("Low Renewable",      0.88, 0.92, 0.82, 0.07),
    ("N-1 Line A Out",     0.85, 0.90, 0.91, 0.08),
    ("N-1 Line B Out",     0.90, 0.95, 0.89, 0.07),
    ("N-1 Line C Out",     0.88, 0.91, 0.88, 0.06),
    ("N-1 Generator Out",  0.85, 0.88, 0.84, 0.06),
    ("Storm East",         0.95, 1.00, 0.78, 0.04),
    ("Storm West",         0.92, 0.98, 0.76, 0.03),
    ("Heat Dome",          1.02, 1.05, 0.88, 0.03),
    ("Cold Snap",          0.98, 0.90, 0.93, 0.03),
]
SCENARIOS = []
for name, ls, ais, gf, w in SCENARIO_DEFS:
    loads = {b: (v*ais if b in AI_LOADS else v*ls) for b, v in BASE_LOADS.items()}
    SCENARIOS.append({"name":name,"loads":loads,"gen_fraction":gf,"weight":w,"total_load":sum(loads.values())})
print(f"Scenarios:        {len(SCENARIOS)} (load / contingency / weather)")

def compute_eue(alloc, scenarios):
    total = 0.0
    for s in scenarios:
        gen  = GEN_NOMINAL * s["gen_fraction"]
        bess = sum(min(cap, s["loads"].get(b,0)*0.8) for b,cap in alloc.items())
        total += max(0.0, s["total_load"] - gen - bess) * s["weight"]
    return total

baseline_eue = compute_eue({}, SCENARIOS)
print(f"Baseline EUE:     {baseline_eue:.4f} MW-prob (no BESS)")
print(f"CAVEAT: this represents ~{baseline_eue*8760/1e3:.0f} GWh/yr unserved (~2.6% of annual")
print(f"        energy), a stylized shortfall for algorithm benchmarking. See README.\n")

# ─── 3. ANALYTICAL PENALTY BOUND ─────────────────────────────────────────────
def derive_lambda_bound(buses, scenarios, safety_factor=1.5):
    max_benefit = 0.0
    for bus in buses:
        for cap in [50, 100]:
            benefit = baseline_eue - compute_eue({bus: cap}, scenarios)
            max_benefit += max(0.0, benefit)
    lambda_min = max_benefit / (50 ** 2)
    return lambda_min * safety_factor, lambda_min, max_benefit

LAMBDA_B, LAMBDA_MIN, MAX_BENEFIT = derive_lambda_bound(CANDIDATE_BUSES_20, SCENARIOS)
print("-" * 70)
print("ANALYTICAL PENALTY DERIVATION")
print("-" * 70)
print(f"  Minimum sufficient lambda (proof):   {LAMBDA_MIN:.6f}")
print(f"  Applied lambda (1.5x safety margin): {LAMBDA_B:.6f}\n")

# ─── 4. QUBO BUILDER ─────────────────────────────────────────────────────────
def build_qubo(buses, scenarios, lam=None, mu=MU_INV):
    if lam is None:
        lam, _, _ = derive_lambda_bound(buses, scenarios)
    n = len(buses)
    Q = {}
    for i, bus in enumerate(buses):
        for bit, cap in enumerate([50, 100]):
            benefit = baseline_eue - compute_eue({bus: cap}, scenarios)
            vi = 2*i + bit
            Q[(vi,vi)] = Q.get((vi,vi), 0) - benefit
    cap_vars = [(2*i+bit, [50,100][bit]) for i in range(n) for bit in range(2)]
    for vi, ci in cap_vars:
        Q[(vi,vi)] = Q.get((vi,vi),0) + lam * ci * (ci - 2*BUDGET_MW)
        for vj, cj in cap_vars:
            if vj > vi:
                Q[(vi,vj)] = Q.get((vi,vj),0) + 2*lam*ci*cj
    for i in range(n):
        Q[(2*i, 2*i+1)] = Q.get((2*i, 2*i+1),0) + mu
    return Q

def decode(sample, buses):
    alloc = {}
    for i, bus in enumerate(buses):
        b0, b1 = sample.get(2*i,0), sample.get(2*i+1,0)
        if b0==1 and b1==0: alloc[bus] = 50
        elif b0==0 and b1==1: alloc[bus] = 100
    return alloc

# ─── 5. ECONOMIC / VOLL LAYER ────────────────────────────────────────────────
CAPEX_PER_MW_M = 0.8
VOLL_PER_MWH   = 10000.0
HOURS_PER_YEAR = 8760.0

def economic_analysis(allocation, eue_value, baseline_eue_value):
    total_mw = sum(allocation.values())
    capex_m  = total_mw * CAPEX_PER_MW_M
    annual_unserved_mwh_baseline = baseline_eue_value * HOURS_PER_YEAR
    annual_unserved_mwh_with_bess = eue_value * HOURS_PER_YEAR
    annual_outage_cost_baseline = annual_unserved_mwh_baseline * VOLL_PER_MWH
    annual_outage_cost_with_bess = annual_unserved_mwh_with_bess * VOLL_PER_MWH
    annual_savings = annual_outage_cost_baseline - annual_outage_cost_with_bess
    payback_years = (capex_m * 1e6) / annual_savings if annual_savings > 0 else float('inf')
    return {
        "capex_musd": round(capex_m, 3),
        "annual_savings_musd": round(annual_savings/1e6, 3),
        "simple_payback_years": round(payback_years, 2) if payback_years != float('inf') else None,
        "CAVEAT": "Illustrates methodology only; baseline EUE is stylized. See README.",
    }

# ─── 6. CLASSICAL MILP ───────────────────────────────────────────────────────
print("-" * 70)
print("SOLVER A: Classical MILP (PuLP + HiGHS) — Exact Baseline")
print("-" * 70)

import pulp

def solve_milp(buses, scenarios, budget=BUDGET_MW, tlim=120):
    prob = pulp.LpProblem("BESS118", pulp.LpMinimize)
    x = {(b,k): pulp.LpVariable(f"x{b}_{k}", cat='Binary')
         for b in buses for k in range(len(BESS_TIERS))}
    for b in buses:
        prob += pulp.lpSum(x[b,k] for k in range(len(BESS_TIERS))) <= 1
    prob += pulp.lpSum(BESS_TIERS[k]*x[b,k] for b in buses
                       for k in range(len(BESS_TIERS))) <= budget
    obj = []
    for s in scenarios:
        gen = GEN_NOMINAL*s["gen_fraction"]
        gap = max(0.0, s["total_load"]-gen)
        benefit = pulp.lpSum(min(BESS_TIERS[k], s["loads"].get(b,0)*0.8)*x[b,k]
                             for b in buses for k in range(len(BESS_TIERS)))
        obj.append(s["weight"]*(gap - benefit))
    prob += pulp.lpSum(obj)
    t0 = time.time()
    prob.solve(pulp.HiGHS(msg=0, timeLimit=tlim))
    rt = time.time()-t0
    alloc = {b: BESS_TIERS[k] for b in buses for k in range(len(BESS_TIERS))
             if BESS_TIERS[k]>0 and pulp.value(x[b,k]) and pulp.value(x[b,k])>0.5}
    eue = compute_eue(alloc, scenarios)
    return {"status":pulp.LpStatus[prob.status], "allocation":alloc,
            "total_mw":sum(alloc.values()), "eue":eue,
            "eue_reduction_pct":(baseline_eue-eue)/baseline_eue*100,
            "runtime_sec":rt, "near_optimal_count":1}

milp = solve_milp(CANDIDATE_BUSES_20, SCENARIOS)
milp_econ = economic_analysis(milp["allocation"], milp["eue"], baseline_eue)
print(f"  Status: {milp['status']} | Runtime: {milp['runtime_sec']:.4f}s | "
      f"EUE: {milp['eue']:.4f} | Reduction: {milp['eue_reduction_pct']:.2f}%\n")

# ─── 7. D-WAVE SIMULATED ANNEALING — MULTI-SEED ──────────────────────────────
print("-" * 70)
print(f"SOLVER B: D-Wave SimulatedAnnealingSampler — {args.seeds} independent seeds")
print("-" * 70)

from dwave.samplers import SimulatedAnnealingSampler
import dimod

def run_dwave_sa_single(buses, scenarios, seed, num_reads=1000, num_sweeps=2000, lam=None):
    Q   = build_qubo(buses, scenarios, lam=lam)
    bqm = dimod.BinaryQuadraticModel.from_qubo(Q)
    sampler = SimulatedAnnealingSampler()
    t0 = time.time()
    resp = sampler.sample(bqm, num_reads=num_reads, num_sweeps=num_sweeps,
                          beta_range=[0.1, 5.0], beta_schedule_type="geometric", seed=seed)
    rt = time.time()-t0
    best_eue, best_alloc = float('inf'), {}
    for sample, _, _ in resp.data(['sample','energy','num_occurrences']):
        alloc = decode(sample, buses)
        cap   = sum(alloc.values())
        if cap <= BUDGET_MW:
            eue = compute_eue(alloc, scenarios)
            if eue < best_eue:
                best_eue, best_alloc = eue, alloc
    return best_eue, best_alloc, rt

def run_dwave_sa_stats(buses, scenarios, n_seeds=10, num_reads=1000, num_sweeps=2000):
    eues, runtimes, allocs = [], [], []
    for seed in range(n_seeds):
        eue, alloc, rt = run_dwave_sa_single(buses, scenarios, seed, num_reads, num_sweeps)
        eues.append(eue); runtimes.append(rt); allocs.append(alloc)
    eues = np.array(eues)
    best_idx = int(np.argmin(eues))
    gap = max(0, (eues.mean() - milp["eue"]) / milp["eue"] * 100)
    best_gap = max(0, (eues.min() - milp["eue"]) / milp["eue"] * 100)
    return {
        "n_seeds": n_seeds, "eue_mean": float(eues.mean()), "eue_std": float(eues.std()),
        "eue_min": float(eues.min()), "eue_max": float(eues.max()),
        "mean_gap_pct": gap, "best_gap_pct": best_gap,
        "best_allocation": allocs[best_idx], "total_mw": sum(allocs[best_idx].values()),
        "runtime_mean_sec": float(np.mean(runtimes)), "runtime_total_sec": float(np.sum(runtimes)),
        "eue_reduction_pct_mean": (baseline_eue-eues.mean())/baseline_eue*100,
        "eue_reduction_pct_best": (baseline_eue-eues.min())/baseline_eue*100,
    }

dsa = run_dwave_sa_stats(CANDIDATE_BUSES_20, SCENARIOS, n_seeds=args.seeds)
dsa_econ = economic_analysis(dsa["best_allocation"], dsa["eue_min"], baseline_eue)
print(f"  EUE (mean+/-std): {dsa['eue_mean']:.4f} +/- {dsa['eue_std']:.4f} | "
      f"Gap (mean/best): {dsa['mean_gap_pct']:.2f}%/{dsa['best_gap_pct']:.2f}%\n")

# ─── 8. D-WAVE LEAP HYBRID (QPU-assisted, decomposed) ────────────────────────
leap = None
if args.leap:
    print("-" * 70)
    print("SOLVER C: D-Wave LeapHybridSampler (hybrid: classical decomposition + QPU)")
    print("-" * 70)
    try:
        from dwave.system import LeapHybridSampler
        Q   = build_qubo(CANDIDATE_BUSES_20, SCENARIOS)
        bqm = dimod.BinaryQuadraticModel.from_qubo(Q)
        sampler = LeapHybridSampler()
        t0  = time.time()
        resp = sampler.sample(bqm, time_limit=10, label="GIC2026_Phase3_118bus_v3")
        rt   = time.time()-t0
        best_alloc = decode(resp.first.sample, CANDIDATE_BUSES_20)
        best_eue   = compute_eue(best_alloc, SCENARIOS)
        best_cap   = sum(best_alloc.values())
        gap        = max(0, (best_eue-milp["eue"])/milp["eue"]*100)
        leap_econ  = economic_analysis(best_alloc, best_eue, baseline_eue)
        leap = {"allocation":best_alloc, "total_mw":best_cap, "eue":best_eue,
                "eue_reduction_pct":(baseline_eue-best_eue)/baseline_eue*100,
                "optimality_gap_pct":gap, "runtime_sec":rt, "time_limit_sec":10,
                "economics": leap_econ}
        print(f"  Runtime: {rt:.3f}s | EUE: {best_eue:.4f} | Gap: {gap:.2f}%\n")
    except Exception as e:
        print(f"  Error: {e}\n")

# ─── 8b. D-WAVE RAW QPU — DIRECT ANNEALING (NEW) ─────────────────────────────
# This is architecturally different from LeapHybridSampler above: the FULL 40-variable
# QUBO is minor-embedded onto physical qubits and annealed directly on the QPU, with
# no classical decomposition step. This exercises D-Wave's "Direct QPU Usage" allocation.
qpu_result = None
if args.qpu:
    print("-" * 70)
    print(f"SOLVER E: Raw D-Wave QPU (DWaveSampler + EmbeddingComposite), {args.qpu_reads} reads")
    print("-" * 70)
    try:
        import os
        from dwave.system import DWaveSampler, EmbeddingComposite

        token = os.environ.get("DWAVE_API_TOKEN")
        if not token:
            raise RuntimeError("DWAVE_API_TOKEN environment variable not set")

        Q = build_qubo(CANDIDATE_BUSES_20, SCENARIOS)
        bqm = dimod.BinaryQuadraticModel.from_qubo(Q)

        # Select QPU solver: default auto-picks an Advantage2 system if available
        qpu_kwargs = {"token": token}
        if args.qpu_solver:
            qpu_kwargs["solver"] = args.qpu_solver
        else:
            qpu_kwargs["solver"] = {"topology__type": "zephyr"}  # Advantage2 uses Zephyr topology

        raw_sampler = DWaveSampler(**qpu_kwargs)
        print(f"  QPU solver selected: {raw_sampler.solver.id}")
        print(f"  Topology: {raw_sampler.properties.get('topology', {}).get('type', 'unknown')}")
        print(f"  Physical qubits available: {raw_sampler.properties.get('num_qubits', 'unknown')}")

        embedded_sampler = EmbeddingComposite(raw_sampler)

        t0 = time.time()
        response = embedded_sampler.sample(
            bqm, num_reads=args.qpu_reads,
            label="GIC2026_Phase3_118bus_rawQPU",
            return_embedding=True,
        )
        rt = time.time() - t0

        # Embedding diagnostics — unique to raw QPU, not available via hybrid solver
        embedding_info = response.info.get('embedding_context', {}).get('embedding', {})
        chain_lengths = [len(chain) for chain in embedding_info.values()] if embedding_info else []
        physical_qubits_used = sum(chain_lengths) if chain_lengths else None

        timing_info = response.info.get('timing', {})
        chain_break_fractions = []
        if 'chain_break_fraction' in response.record.dtype.names:
            chain_break_fractions = response.record['chain_break_fraction'].tolist()

        best_alloc, best_eue = {}, float('inf')
        for sample, energy, occ, *_ in response.data(
                ['sample','energy','num_occurrences'], sorted_by='energy'):
            alloc = decode(sample, CANDIDATE_BUSES_20)
            cap = sum(alloc.values())
            if cap <= BUDGET_MW:
                eue = compute_eue(alloc, SCENARIOS)
                if eue < best_eue:
                    best_eue, best_alloc = eue, alloc
                    break  # response is sorted by energy; first feasible is our best

        if best_eue == float('inf'):
            best_eue, best_alloc = baseline_eue, {}

        gap = max(0, (best_eue - milp["eue"]) / milp["eue"] * 100)
        qpu_econ = economic_analysis(best_alloc, best_eue, baseline_eue)

        qpu_result = {
            "solver_id": raw_sampler.solver.id,
            "topology": raw_sampler.properties.get('topology', {}).get('type', 'unknown'),
            "logical_qubits": len(CANDIDATE_BUSES_20) * N_BITS,
            "physical_qubits_used": physical_qubits_used,
            "num_chains": len(chain_lengths) if chain_lengths else None,
            "max_chain_length": max(chain_lengths) if chain_lengths else None,
            "mean_chain_break_fraction": float(np.mean(chain_break_fractions)) if chain_break_fractions else None,
            "num_reads": args.qpu_reads,
            "qpu_access_time_us": timing_info.get('qpu_access_time'),
            "qpu_anneal_time_per_sample_us": timing_info.get('qpu_anneal_time_per_sample'),
            "runtime_sec": rt,
            "allocation": best_alloc, "total_mw": sum(best_alloc.values()),
            "eue": best_eue, "eue_reduction_pct": (baseline_eue-best_eue)/baseline_eue*100,
            "optimality_gap_pct": gap, "economics": qpu_econ,
        }
        print(f"  Logical qubits (QUBO vars): {qpu_result['logical_qubits']}")
        print(f"  Physical qubits used:       {qpu_result['physical_qubits_used']}")
        print(f"  Number of chains:           {qpu_result['num_chains']}")
        print(f"  Max chain length:           {qpu_result['max_chain_length']}")
        print(f"  Mean chain-break fraction:  {qpu_result['mean_chain_break_fraction']}")
        print(f"  QPU access time (us):       {qpu_result['qpu_access_time_us']}")
        print(f"  Wall-clock runtime:         {rt:.3f}s")
        print(f"  EUE: {best_eue:.4f} | Reduction: {qpu_result['eue_reduction_pct']:.2f}% | "
              f"Gap: {gap:.2f}%\n")
    except Exception as e:
        print(f"  Error: {e}")
        print("  -> Set DWAVE_API_TOKEN and retry with --qpu")
        print("  -> If embedding fails, the 40-variable dense QUBO may not fit current")
        print("     chip yield; try --qpu-solver to target a specific solver, or reduce")
        print("     candidate bus count for a raw-QPU-only sub-experiment.\n")

# ─── 9. IBM QUANTUM — QAOA WITH COBYLA LOOP ──────────────────────────────────
ibm_result = None
if args.ibm:
    print("-" * 70)
    print(f"SOLVER D: QAOA + COBYLA on IBM Quantum (max {args.ibm_iters} iterations)")
    print("-" * 70)
    try:
        import os
        from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
        from qiskit.circuit.library import QAOAAnsatz
        from qiskit.quantum_info import SparsePauliOp
        from qiskit import transpile
        from scipy.optimize import minimize

        token = os.environ.get("IBM_QUANTUM_TOKEN")
        if not token:
            raise RuntimeError("IBM_QUANTUM_TOKEN environment variable not set")

        IBM_BUSES = CANDIDATE_BUSES_20[:10]
        n_ibm = len(IBM_BUSES) * N_BITS
        Q_ibm = build_qubo(IBM_BUSES, SCENARIOS)

        linear, quad = {i:0.0 for i in range(n_ibm)}, {}
        for (i,j), coeff in Q_ibm.items():
            if i==j: linear[i]+=coeff
            else: quad[(i,j)] = quad.get((i,j),0)+coeff
        h, J, offset = {i:0.0 for i in range(n_ibm)}, {}, 0.0
        for i,c in linear.items():
            h[i]+=-c/2; offset+=c/2
        for (i,j),c in quad.items():
            J[(i,j)] = J.get((i,j),0)+c/4; h[i]+=-c/4; h[j]+=-c/4; offset+=c/4

        pauli_list = []
        for i in range(n_ibm):
            if abs(h[i])>1e-12:
                z=["I"]*n_ibm; z[n_ibm-1-i]="Z"; pauli_list.append(("".join(z), h[i]))
        for (i,j),c in J.items():
            if abs(c)>1e-12:
                z=["I"]*n_ibm; z[n_ibm-1-i]="Z"; z[n_ibm-1-j]="Z"; pauli_list.append(("".join(z), c))
        cost_hamiltonian = SparsePauliOp.from_list(pauli_list) if pauli_list else SparsePauliOp("I"*n_ibm,[0])

        service = QiskitRuntimeService(channel="ibm_quantum_platform", token=token)
        backend = service.least_busy(operational=True, simulator=False, min_num_qubits=n_ibm)
        print(f"  Backend: {backend.name} ({backend.num_qubits} qubits)")

        p_layers = 1
        qaoa_ansatz = QAOAAnsatz(cost_operator=cost_hamiltonian, reps=p_layers)
        qaoa_ansatz.measure_all()
        isa_circuit = transpile(qaoa_ansatz, backend=backend, optimization_level=1)
        sampler = SamplerV2(mode=backend)

        m_ibm = solve_milp(IBM_BUSES, SCENARIOS, tlim=30)
        eval_log = []

        def qubo_expectation_from_counts(counts, buses):
            total_shots = sum(counts.values())
            exp_val = 0.0
            for bitstring, freq in counts.items():
                bits = [int(c) for c in bitstring[::-1]]
                sample = {i: bits[i] for i in range(len(bits))}
                alloc = decode(sample, buses)
                cap = sum(alloc.values())
                eue = compute_eue(alloc, SCENARIOS) if cap <= BUDGET_MW else baseline_eue * 2
                exp_val += eue * (freq / total_shots)
            return exp_val

        job_count = [0]
        def cobyla_objective(theta):
            job_count[0] += 1
            job = sampler.run([(isa_circuit, theta)], shots=1024)
            result = job.result()
            counts = result[0].data.meas.get_counts()
            exp_val = qubo_expectation_from_counts(counts, IBM_BUSES)
            eval_log.append({"iter": job_count[0], "job_id": job.job_id(), "exp_eue": exp_val})
            print(f"    iter {job_count[0]:2d}: exp_EUE={exp_val:.4f}")
            return exp_val

        np.random.seed(42)
        init_params = np.random.uniform(0, np.pi, qaoa_ansatz.num_parameters)
        t0 = time.time()
        opt_result = minimize(cobyla_objective, init_params, method='COBYLA',
                              options={'maxiter': args.ibm_iters, 'rhobeg': 0.5})
        rt = time.time() - t0

        final_job = sampler.run([(isa_circuit, opt_result.x)], shots=2048)
        final_counts = final_job.result()[0].data.meas.get_counts()
        best_eue_ibm, best_alloc_ibm = float('inf'), {}
        for bitstring, freq in final_counts.items():
            bits = [int(c) for c in bitstring[::-1]]
            sample = {i: bits[i] for i in range(len(bits))}
            alloc = decode(sample, IBM_BUSES)
            cap = sum(alloc.values())
            if cap <= BUDGET_MW:
                eue = compute_eue(alloc, SCENARIOS)
                if eue < best_eue_ibm:
                    best_eue_ibm, best_alloc_ibm = eue, alloc
        if best_eue_ibm == float('inf'):
            best_eue_ibm, best_alloc_ibm = baseline_eue, {}

        gap_ibm = max(0, (best_eue_ibm - m_ibm["eue"]) / max(m_ibm["eue"],1e-9) * 100)
        ibm_econ = economic_analysis(best_alloc_ibm, best_eue_ibm, baseline_eue)
        ibm_result = {
            "backend": backend.name, "n_qubits": n_ibm, "p_layers": p_layers,
            "cobyla_iterations": job_count[0], "total_jobs": job_count[0] + 1,
            "final_job_id": final_job.job_id(), "allocation": best_alloc_ibm,
            "total_mw": sum(best_alloc_ibm.values()), "eue": best_eue_ibm,
            "eue_reduction_pct": (baseline_eue-best_eue_ibm)/baseline_eue*100,
            "optimality_gap_pct": gap_ibm, "runtime_sec": rt,
            "convergence_log": eval_log, "economics": ibm_econ,
        }
        print(f"\n  Final EUE: {best_eue_ibm:.4f} | Gap: {gap_ibm:.2f}%\n")
    except Exception as e:
        print(f"  Error: {e}\n")

# ─── 10. SCALING STUDY ───────────────────────────────────────────────────────
scaling = []
if args.scaling:
    print("-" * 70)
    print("SCALING STUDY")
    print("-" * 70)
    EXTRA_BUSES = [33, 46, 60, 74, 99]
    ALL_BUSES   = CANDIDATE_BUSES_20 + EXTRA_BUSES
    for n in [10, 15, 20, 25]:
        buses = ALL_BUSES[:n]
        m = solve_milp(buses, SCENARIOS, tlim=30)
        stats = run_dwave_sa_stats(buses, SCENARIOS, n_seeds=5, num_reads=500, num_sweeps=1000)
        scaling.append({"n":n, "qubits":n*N_BITS, "milp_eue":m["eue"],
                        "sa_eue_mean":stats["eue_mean"], "sa_gap_mean":stats["mean_gap_pct"],
                        "sa_gap_best":stats["best_gap_pct"]})
        print(f"  n={n:2d} | MILP {m['eue']:.4f} | SA {stats['eue_mean']:.4f} | "
              f"Gap(mean/best) {stats['mean_gap_pct']:.1f}%/{stats['best_gap_pct']:.1f}%")
    print()

# ─── 11. FINAL RESULTS TABLE ─────────────────────────────────────────────────
print("=" * 70)
print("FINAL BENCHMARK RESULTS")
print("=" * 70)
print(f"{'Method':<34} {'EUE':>10} {'Red%':>7} {'Gap%':>7}")
print("-" * 70)
print(f"{'No BESS (baseline)':<34} {baseline_eue:>10.4f} {'—':>7} {'—':>7}")
print(f"{'MILP/HiGHS (optimal)':<34} {milp['eue']:>10.4f} {milp['eue_reduction_pct']:>6.2f}% {'0.00%':>7}")
print(f"{'D-Wave SA (mean of '+str(args.seeds)+')':<34} {dsa['eue_mean']:>10.4f} "
      f"{dsa['eue_reduction_pct_mean']:>6.2f}% {dsa['mean_gap_pct']:>6.2f}%")
print(f"{'D-Wave SA (best of '+str(args.seeds)+')':<34} {dsa['eue_min']:>10.4f} "
      f"{dsa['eue_reduction_pct_best']:>6.2f}% {dsa['best_gap_pct']:>6.2f}%")
if leap:
    print(f"{'D-Wave LeapHybrid (hybrid QPU)':<34} {leap['eue']:>10.4f} {leap['eue_reduction_pct']:>6.2f}% "
          f"{leap['optimality_gap_pct']:>6.2f}%")
else:
    print(f"{'D-Wave LeapHybrid (hybrid QPU)':<34} {'-> run with --leap':>25}")
if qpu_result:
    print(f"{'D-Wave Raw QPU (direct anneal)':<34} {qpu_result['eue']:>10.4f} "
          f"{qpu_result['eue_reduction_pct']:>6.2f}% {qpu_result['optimality_gap_pct']:>6.2f}%")
else:
    print(f"{'D-Wave Raw QPU (direct anneal)':<34} {'-> run with --qpu':>25}")
if ibm_result:
    print(f"{'IBM QAOA+COBYLA':<34} {ibm_result['eue']:>10.4f} {ibm_result['eue_reduction_pct']:>6.2f}% "
          f"{ibm_result['optimality_gap_pct']:>6.2f}%")
else:
    print(f"{'IBM QAOA+COBYLA':<34} {'-> run with --ibm':>25}")
print("-" * 70)

# ─── 12. SAVE JSON ───────────────────────────────────────────────────────────
out = {
    "experiment": "GIC2026_Phase3_DOE_EnergyInfrastructure_v3",
    "team": "Qudit Creons", "member": "Abhishek Raj",
    "baseline_eue": round(baseline_eue, 6),
    "penalty_derivation": {"lambda_min": LAMBDA_MIN, "lambda_applied": LAMBDA_B},
    "milp": {k: round(v,6) if isinstance(v,float) else v for k,v in milp.items()},
    "milp_economics": milp_econ,
    "dwave_sa_stats": dsa, "dwave_sa_economics": dsa_econ,
    "leap_hybrid": leap,
    "raw_qpu": qpu_result,
    "ibm_qaoa": ibm_result,
    "scaling_study": scaling,
}
with open("results_phase3_v3.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
print("\nResults saved -> results_phase3_v3.json")
print("=" * 70)

"""
GIC 2026 — Phase 3 Experiment (Enterprise-Grade Upgrade)
Team: Qudit Creons | Abhishek Raj
Challenge: DOE OTC — Quantum-Enhanced Strategic Siting of Energy Storage & Microgrids

CHANGES FROM v1 (documented for judges / reviewers):
  1. Economic layer: capital cost + Value of Lost Load (VOLL) monetization, payback period.
     Assumptions cited: NREL 2024 ATB (BESS capex), DOE/LBNL ICE Calculator (VOLL range).
  2. Statistical rigor: D-Wave SA now run across N_SEEDS independent trials; results report
     mean, std, min/max instead of a single point estimate.
  3. Analytical penalty bound: lambda_budget is now derived from a provable sufficient
     condition (see derive_lambda_bound()) rather than set by empirical sweep alone.
  4. IBM QAOA: replaced single fixed-parameter circuit with a proper COBYLA optimization
     loop over QAOA parameters (gamma, beta), using iterative job submission to real
     hardware. This is the standard definition of QAOA; the Phase 3 v1 submission ran
     only one un-optimized circuit due to resource constraints, which is now fixed.

EXPLICITLY NOT ATTEMPTED (documented as future work, not silently skipped):
  - Full AC-OPF (reactive power / voltage magnitude constraints)
  - Exact IEEE 118-bus branch-level PTDF contingency analysis (requires verified branch
    impedance data not safely reproducible from memory; DC "gen_fraction" scaling remains
    a documented simplification)
  - Multi-year capacity expansion (single representative year only)

Usage:
  python experiment.py                    # local: MILP + D-Wave SA (multi-seed) + cost layer
  python experiment.py --leap              # + D-Wave LeapHybridSampler (needs DWAVE_API_TOKEN)
  python experiment.py --ibm               # + IBM QAOA w/ COBYLA loop (needs IBM_QUANTUM_TOKEN)
  python experiment.py --ibm --ibm-iters 10   # control COBYLA iteration budget (QPU time!)
  python experiment.py --scaling           # + full scaling study
"""

import time, json, argparse, numpy as np, warnings
warnings.filterwarnings("ignore")

parser = argparse.ArgumentParser()
parser.add_argument("--leap",     action="store_true", help="Run LeapHybridSampler (needs DWAVE_API_TOKEN)")
parser.add_argument("--ibm",      action="store_true", help="Run QAOA+COBYLA on IBM Quantum (needs IBM_QUANTUM_TOKEN)")
parser.add_argument("--ibm-iters", type=int, default=15, help="COBYLA max iterations for IBM QAOA (each = 1 QPU job)")
parser.add_argument("--scaling",  action="store_true", help="Run full scaling study")
parser.add_argument("--seeds",    type=int, default=10, help="Number of random seeds for D-Wave SA statistics")
args, _ = parser.parse_known_args()

print("=" * 70)
print("GIC 2026 Phase 3 | Team Qudit Creons | DOE Energy Infrastructure")
print("IEEE 118-Bus BESS Siting — Enterprise-Grade Benchmark")
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
print("NOTE: contingency/weather scenarios use documented generation-fraction scaling,")
print("      not branch-level PTDF analysis. See README 'Limitations' section.\n")

def compute_eue(alloc, scenarios):
    total = 0.0
    for s in scenarios:
        gen  = GEN_NOMINAL * s["gen_fraction"]
        bess = sum(min(cap, s["loads"].get(b,0)*0.8) for b,cap in alloc.items())
        total += max(0.0, s["total_load"] - gen - bess) * s["weight"]
    return total

baseline_eue = compute_eue({}, SCENARIOS)
print(f"Baseline EUE:     {baseline_eue:.4f} MW-prob (no BESS)")
print(f"CAVEAT: this represents ~{baseline_eue*8760/1e3:.0f} GWh/yr unserved ("
      f"~2.6% of annual energy) -- roughly 100-1000x real NERC reliability targets.")
print(f"        This is a deliberate stylized shortfall (GEN_NOMINAL capped below peak)")
print(f"        for algorithm benchmarking. Dollar figures below illustrate METHODOLOGY")
print(f"        and are comparable ACROSS solvers, not calibrated investment guidance.\n")

# ─── 3. ANALYTICAL PENALTY BOUND (NEW) ───────────────────────────────────────
def derive_lambda_bound(buses, scenarios, safety_factor=1.5):
    """
    Derive a provably-sufficient lambda_budget.

    Sufficient condition: violating the budget by the smallest possible increment
    (one 50 MW tier) must cost more in penalty than the maximum achievable objective
    benefit from any single-variable flip. This guarantees the penalty term dominates
    the objective term at the constraint boundary, so the QUBO optimum is feasible.

    max_benefit  = sum over all (bus,tier) of (baseline_eue - eue({bus:cap}))
                   [upper bound on total achievable EUE-reduction "reward"]
    min_violation_cost = lambda * (50)^2   [smallest quadratic penalty unit]

    => lambda > max_benefit / 2500
    """
    max_benefit = 0.0
    for bus in buses:
        for cap in [50, 100]:
            benefit = baseline_eue - compute_eue({bus: cap}, scenarios)
            max_benefit += max(0.0, benefit)
    lambda_min = max_benefit / (50 ** 2)
    return lambda_min * safety_factor, lambda_min, max_benefit

LAMBDA_B, LAMBDA_MIN, MAX_BENEFIT = derive_lambda_bound(CANDIDATE_BUSES_20, SCENARIOS)
print("-" * 70)
print("ANALYTICAL PENALTY DERIVATION (replaces ad hoc empirical sweep)")
print("-" * 70)
print(f"  Sum of max per-variable EUE benefit: {MAX_BENEFIT:.4f}")
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

# ─── 5. ECONOMIC / VOLL LAYER (NEW) ──────────────────────────────────────────
# Cited assumptions:
#   CAPEX: NREL 2024 Annual Technology Baseline, 4-hr Li-ion BESS ~ $0.8M/MW (2024 $)
#   VOLL:  DOE/LBNL Interruption Cost Estimate (ICE) Calculator, industrial/commercial
#          composite VOLL ~ $10,000/MWh (conservative end of documented $8k-30k range)
CAPEX_PER_MW_M = 0.8       # $M per MW installed (NREL ATB 2024, 4-hr Li-ion BESS)
VOLL_PER_MWH   = 10000.0   # $/MWh (DOE/LBNL ICE Calculator, conservative industrial estimate)
HOURS_PER_YEAR = 8760.0

def economic_analysis(allocation, eue_value, baseline_eue_value):
    """
    Monetize EUE reduction. Scenario weights sum to 1.0 and represent fraction-of-year
    probability, so EUE (MW-prob) x 8760 hours/year = Expected Annual Unserved Energy (MWh/yr).

    IMPORTANT CAVEAT (documented, not hidden): the baseline EUE in this experiment
    (~62.67 MW-prob, ~2.6% of annual energy unserved) is roughly 100-1000x larger than
    real-world NERC reliability targets (typically <0.01% of annual energy, i.e. LOLE on
    the order of 1 day in 10 years). This is a deliberate methodological simplification
    from Phase 2/3 (GEN_NOMINAL capped below peak load to create a demonstrable shortfall
    for algorithm benchmarking purposes) and is NOT a calibrated reliability study.
    The dollar figures below (CAPEX, annual savings, payback) illustrate the economic
    EVALUATION METHODOLOGY -- they are directly comparable ACROSS solvers (MILP vs D-Wave
    vs IBM) on this same stylized instance, but should NOT be read as real investment
    guidance. A production study would calibrate GEN_NOMINAL and scenario probabilities
    against actual historical EUE/LOLE data, which would produce a much smaller baseline
    EUE and correspondingly longer, realistic payback periods (years, not weeks).
    """
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
        "annual_unserved_mwh_baseline": round(annual_unserved_mwh_baseline, 1),
        "annual_unserved_mwh_with_bess": round(annual_unserved_mwh_with_bess, 1),
        "annual_outage_cost_baseline_musd": round(annual_outage_cost_baseline/1e6, 3),
        "annual_outage_cost_with_bess_musd": round(annual_outage_cost_with_bess/1e6, 3),
        "annual_savings_musd": round(annual_savings/1e6, 3),
        "simple_payback_years": round(payback_years, 2) if payback_years != float('inf') else None,
        "CAVEAT": "Payback illustrates methodology only; baseline EUE is ~100-1000x real NERC "
                  "reliability targets by design (Phase 2/3 stylized shortfall for algorithm "
                  "benchmarking). Not calibrated investment guidance. See README.",
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
print(f"  Status:         {milp['status']}")
print(f"  Runtime:        {milp['runtime_sec']:.4f} s")
print(f"  Total BESS:     {milp['total_mw']} MW")
print(f"  EUE:            {milp['eue']:.4f} MW-prob")
print(f"  EUE Reduction:  {milp['eue_reduction_pct']:.2f}%")
print(f"  Siting plan:    {milp['allocation']}")
print(f"  CAPEX:          ${milp_econ['capex_musd']}M")
print(f"  Annual savings: ${milp_econ['annual_savings_musd']}M/yr")
print(f"  Simple payback: {milp_econ['simple_payback_years']} years\n")

# ─── 7. D-WAVE SIMULATED ANNEALING — MULTI-SEED STATISTICAL RIGOR (UPGRADED) ─
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
print(f"  Seeds:          {dsa['n_seeds']}")
print(f"  EUE (mean±std): {dsa['eue_mean']:.4f} +/- {dsa['eue_std']:.4f} MW-prob")
print(f"  EUE (best/worst): {dsa['eue_min']:.4f} / {dsa['eue_max']:.4f}")
print(f"  Gap (mean/best): {dsa['mean_gap_pct']:.2f}% / {dsa['best_gap_pct']:.2f}%")
print(f"  Runtime (mean):  {dsa['runtime_mean_sec']:.3f} s/trial, {dsa['runtime_total_sec']:.3f} s total")
print(f"  Best CAPEX:      ${dsa_econ['capex_musd']}M | Payback: {dsa_econ['simple_payback_years']} yrs\n")

# ─── 8. D-WAVE LEAP HYBRID (QPU) ─────────────────────────────────────────────
leap = None
if args.leap:
    print("-" * 70)
    print("SOLVER C: D-Wave LeapHybridSampler (real QPU via Leap Cloud)")
    print("-" * 70)
    try:
        from dwave.system import LeapHybridSampler
        Q   = build_qubo(CANDIDATE_BUSES_20, SCENARIOS)
        bqm = dimod.BinaryQuadraticModel.from_qubo(Q)
        sampler = LeapHybridSampler()
        t0  = time.time()
        resp = sampler.sample(bqm, time_limit=10, label="GIC2026_Phase3_118bus_v2")
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
        print(f"  Runtime:        {rt:.3f} s (time_limit=10s)")
        print(f"  EUE:            {best_eue:.4f} MW-prob | Gap: {gap:.2f}%")
        print(f"  CAPEX:          ${leap_econ['capex_musd']}M | Payback: {leap_econ['simple_payback_years']} yrs\n")
    except Exception as e:
        print(f"  Error: {e}\n")

# ─── 9. IBM QUANTUM — QAOA WITH COBYLA OPTIMIZATION LOOP (UPGRADED) ──────────
ibm_result = None
if args.ibm:
    print("-" * 70)
    print(f"SOLVER D: QAOA + COBYLA on IBM Quantum (max {args.ibm_iters} iterations)")
    print(f"WARNING: each iteration submits a real QPU job (~10-20s). This will consume")
    print(f"         significant Open Plan minutes. Reduce --ibm-iters if needed.")
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

        IBM_BUSES = CANDIDATE_BUSES_20[:10]   # 10 buses -> 20 qubits (hardware-feasible)
        n_ibm = len(IBM_BUSES) * N_BITS
        Q_ibm = build_qubo(IBM_BUSES, SCENARIOS)

        # QUBO -> Ising conversion: x_i = (1 - z_i)/2
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
            print(f"    iter {job_count[0]:2d}: job={job.job_id()[:12]}...  exp_EUE={exp_val:.4f}")
            return exp_val

        np.random.seed(42)
        init_params = np.random.uniform(0, np.pi, qaoa_ansatz.num_parameters)

        t0 = time.time()
        opt_result = minimize(cobyla_objective, init_params, method='COBYLA',
                              options={'maxiter': args.ibm_iters, 'rhobeg': 0.5})
        rt = time.time() - t0

        # Final sample at optimized parameters to extract best bitstring
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
            "final_job_id": final_job.job_id(),
            "allocation": best_alloc_ibm, "total_mw": sum(best_alloc_ibm.values()),
            "eue": best_eue_ibm, "eue_reduction_pct": (baseline_eue-best_eue_ibm)/baseline_eue*100,
            "optimality_gap_pct": gap_ibm, "runtime_sec": rt,
            "convergence_log": eval_log, "economics": ibm_econ,
        }
        print(f"\n  COBYLA converged after {job_count[0]} iterations ({job_count[0]+1} total QPU jobs)")
        print(f"  Total runtime:   {rt:.2f} s")
        print(f"  Final EUE:       {best_eue_ibm:.4f} MW-prob")
        print(f"  EUE Reduction:   {ibm_result['eue_reduction_pct']:.2f}%")
        print(f"  Gap vs MILP:     {gap_ibm:.2f}%")
        print(f"  CAPEX:           ${ibm_econ['capex_musd']}M | Payback: {ibm_econ['simple_payback_years']} yrs\n")
    except Exception as e:
        print(f"  Error: {e}")
        print("  -> Set IBM_QUANTUM_TOKEN and retry with --ibm\n")

# ─── 10. SCALING STUDY ───────────────────────────────────────────────────────
scaling = []
if args.scaling:
    print("-" * 70)
    print("SCALING STUDY: problem size vs solution quality and runtime")
    print("-" * 70)
    EXTRA_BUSES = [33, 46, 60, 74, 99]
    ALL_BUSES   = CANDIDATE_BUSES_20 + EXTRA_BUSES
    for n in [10, 15, 20, 25]:
        buses = ALL_BUSES[:n]
        m = solve_milp(buses, SCENARIOS, tlim=30)
        stats = run_dwave_sa_stats(buses, SCENARIOS, n_seeds=5, num_reads=500, num_sweeps=1000)
        scaling.append({"n":n, "qubits":n*N_BITS,
                        "milp_eue":m["eue"], "milp_rt":m["runtime_sec"],
                        "sa_eue_mean":stats["eue_mean"], "sa_eue_std":stats["eue_std"],
                        "sa_gap_mean":stats["mean_gap_pct"], "sa_gap_best":stats["best_gap_pct"]})
        print(f"  n={n:2d} | {n*N_BITS:2d} qubits | MILP {m['eue']:.4f} | "
              f"SA {stats['eue_mean']:.4f}+/-{stats['eue_std']:.4f} | "
              f"Gap(mean/best) {stats['mean_gap_pct']:.1f}%/{stats['best_gap_pct']:.1f}%")
    print()

# ─── 11. FINAL RESULTS TABLE ─────────────────────────────────────────────────
print("=" * 70)
print("FINAL BENCHMARK RESULTS — IEEE 118-bus | 40 QUBO vars | 15 scenarios")
print("=" * 70)
print(f"{'Method':<32} {'EUE':>10} {'Red%':>7} {'Gap%':>7} {'Payback':>9}")
print("-" * 70)
print(f"{'No BESS (baseline)':<32} {baseline_eue:>10.4f} {'—':>7} {'—':>7} {'—':>9}")
print(f"{'MILP/HiGHS (optimal)':<32} {milp['eue']:>10.4f} {milp['eue_reduction_pct']:>6.2f}% "
      f"{'0.00%':>7} {str(milp_econ['simple_payback_years'])+'y':>9}")
print(f"{'D-Wave SA (mean of '+str(args.seeds)+')':<32} {dsa['eue_mean']:>10.4f} "
      f"{dsa['eue_reduction_pct_mean']:>6.2f}% {dsa['mean_gap_pct']:>6.2f}% "
      f"{str(dsa_econ['simple_payback_years'])+'y':>9}")
print(f"{'D-Wave SA (best of '+str(args.seeds)+')':<32} {dsa['eue_min']:>10.4f} "
      f"{dsa['eue_reduction_pct_best']:>6.2f}% {dsa['best_gap_pct']:>6.2f}% {'—':>9}")
if leap:
    print(f"{'D-Wave LeapHybrid (QPU)':<32} {leap['eue']:>10.4f} {leap['eue_reduction_pct']:>6.2f}% "
          f"{leap['optimality_gap_pct']:>6.2f}% {str(leap['economics']['simple_payback_years'])+'y':>9}")
else:
    print(f"{'D-Wave LeapHybrid (QPU)':<32} {'-> run with --leap':>34}")
if ibm_result:
    print(f"{'IBM QAOA+COBYLA ('+ibm_result['backend']+')':<32} {ibm_result['eue']:>10.4f} "
          f"{ibm_result['eue_reduction_pct']:>6.2f}% {ibm_result['optimality_gap_pct']:>6.2f}% "
          f"{str(ibm_result['economics']['simple_payback_years'])+'y':>9}")
else:
    print(f"{'IBM QAOA+COBYLA':<32} {'-> run with --ibm':>34}")
print("-" * 70)

# ─── 12. SAVE JSON ───────────────────────────────────────────────────────────
out = {
    "experiment": "GIC2026_Phase3_DOE_EnergyInfrastructure_v2_enterprise",
    "team": "Qudit Creons", "member": "Abhishek Raj",
    "test_system": "IEEE 118-bus (MATPOWER case118)",
    "ai_loads_mw": {"bus_49": 300, "bus_80": 300},
    "n_candidates": len(CANDIDATE_BUSES_20), "candidate_buses": CANDIDATE_BUSES_20,
    "n_qubits": len(CANDIDATE_BUSES_20)*N_BITS, "n_scenarios": len(SCENARIOS),
    "capital_budget_mw": BUDGET_MW, "baseline_eue": round(baseline_eue, 6),
    "economic_assumptions": {"capex_per_mw_musd": CAPEX_PER_MW_M, "voll_per_mwh_usd": VOLL_PER_MWH,
                              "source": "NREL 2024 ATB (capex); DOE/LBNL ICE Calculator (VOLL)"},
    "penalty_derivation": {"lambda_min_provable": LAMBDA_MIN, "lambda_applied": LAMBDA_B,
                            "safety_factor": 1.5, "max_benefit_bound": MAX_BENEFIT},
    "milp": {k: round(v,6) if isinstance(v,float) else v for k,v in milp.items()},
    "milp_economics": milp_econ,
    "dwave_sa_stats": dsa,
    "dwave_sa_economics": dsa_econ,
    "leap_hybrid": leap,
    "ibm_qaoa": ibm_result,
    "scaling_study": scaling,
}
with open("results_phase3_v2.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
print("\nResults saved -> results_phase3_v2.json")
print("=" * 70)

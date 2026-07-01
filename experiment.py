"""
GIC 2026 — Phase 3 Full Experiment
Team: Qudit Creons | Abhishek Raj
Challenge: DOE OTC — Quantum-Enhanced Strategic Siting of Energy Storage & Microgrids

Experiment structure:
  1. IEEE 118-bus network + 2 synthetic AI datacenter loads (300 MW each)
  2. 20 candidate BESS buses, 3 capacity tiers → 40 binary variables (QUBO)
  3. 15 operating + contingency + weather scenarios
  4. SOLVER A: Classical MILP (PuLP + HiGHS)              — exact optimal baseline
  5. SOLVER B: D-Wave SimulatedAnnealingSampler (local)   — classical heuristic via D-Wave SDK
  6. SOLVER C: D-Wave LeapHybridSampler (QPU)             — real quantum (--leap flag)
  7. Scaling study: 10, 15, 20, 25 candidate buses
  8. Penalty sensitivity: lambda_budget sweep
  9. Full results table + JSON output

Usage:
  python experiment.py                    # local run, no QPU credentials needed
  python experiment.py --leap             # run LeapHybridSampler (requires DWAVE_API_TOKEN)
  python experiment.py --scaling          # also run full scaling study

Requirements:
  pip install dwave-ocean-sdk pulp highspy numpy
"""

import time, json, argparse, numpy as np, warnings
warnings.filterwarnings("ignore")

parser = argparse.ArgumentParser()
parser.add_argument("--leap",    action="store_true", help="Run LeapHybridSampler (needs DWAVE_API_TOKEN)")
parser.add_argument("--scaling", action="store_true", help="Run full scaling study")
args, _ = parser.parse_known_args()

print("=" * 70)
print("GIC 2026 Phase 3 | Team Qudit Creons | DOE Energy Infrastructure")
print("IEEE 118-Bus BESS Siting — D-Wave Hybrid vs Classical Benchmark")
print("=" * 70)

# ─── 1. IEEE 118-BUS NETWORK ─────────────────────────────────────────────────
# Source: MATPOWER case118 (public domain). Selective load buses in MW.
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
GEN_NOMINAL = 5200.0  # MW effective dispatchable (creates realistic shortfall under peak+contingency)

# Add 2 synthetic AI datacenter loads
AI_LOADS = {49: 300.0, 80: 300.0}
for bus, load in AI_LOADS.items():
    BASE_LOADS[bus] = BASE_LOADS.get(bus, 0) + load

TOTAL_PEAK = sum(BASE_LOADS.values())
print(f"\nNetwork:          IEEE 118-bus (MATPOWER case118)")
print(f"AI loads added:   2 × 300 MW at Buses 49 & 80")
print(f"Total peak load:  {TOTAL_PEAK:.0f} MW | Gen capacity: {GEN_NOMINAL:.0f} MW")

# ─── 2. CANDIDATE BESS LOCATIONS ─────────────────────────────────────────────
# 20 buses: high-load nodes + buses adjacent to AI loads (Buses 49, 80)
CANDIDATE_BUSES_20 = [
    15, 27, 31, 34, 40, 42, 45, 49, 54, 55,
    59, 62, 70, 74, 77, 80, 90, 92, 100, 116
]
BESS_TIERS  = [0, 50, 100]   # MW per bus
BUDGET_MW   = 500             # capital budget
N_BITS      = 2               # bits per bus: (1,0)=50MW (0,1)=100MW
LAMBDA_B    = 3.0             # budget penalty strength
MU_INV      = 6.0            # invalid-state penalty

print(f"Candidates:       {len(CANDIDATE_BUSES_20)} buses → {len(CANDIDATE_BUSES_20)*N_BITS} QUBO binary vars")
print(f"Budget:           {BUDGET_MW} MW | Tiers: {BESS_TIERS} MW\n")

# ─── 3. SCENARIOS ─────────────────────────────────────────────────────────────
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

# ─── 4. EUE OBJECTIVE ────────────────────────────────────────────────────────
def compute_eue(alloc, scenarios):
    total = 0.0
    for s in scenarios:
        gen  = GEN_NOMINAL * s["gen_fraction"]
        bess = sum(min(cap, s["loads"].get(b,0)*0.8) for b,cap in alloc.items())
        total += max(0.0, s["total_load"] - gen - bess) * s["weight"]
    return total

baseline_eue = compute_eue({}, SCENARIOS)
print(f"Baseline EUE:     {baseline_eue:.4f} MW·prob (no BESS)\n")

# ─── 5. QUBO BUILDER ─────────────────────────────────────────────────────────
def build_qubo(buses, scenarios, lam=LAMBDA_B, mu=MU_INV):
    """Build QUBO dict for D-Wave. Variable 2i = 50MW bit, 2i+1 = 100MW bit."""
    n = len(buses)
    Q = {}

    # Objective: negative EUE-reduction on diagonal
    for i, bus in enumerate(buses):
        for bit, cap in enumerate([50, 100]):
            benefit = baseline_eue - compute_eue({bus: cap}, scenarios)
            vi = 2*i + bit
            Q[(vi,vi)] = Q.get((vi,vi), 0) - benefit

    # Budget penalty: lambda*(sum cap_i*x_i - B)^2, only over-budget penalised
    cap_vars = [(2*i+bit, [50,100][bit]) for i in range(n) for bit in range(2)]
    for vi, ci in cap_vars:
        Q[(vi,vi)] = Q.get((vi,vi),0) + lam * ci * (ci - 2*BUDGET_MW)
        for vj, cj in cap_vars:
            if vj > vi:
                Q[(vi,vj)] = Q.get((vi,vj),0) + 2*lam*ci*cj

    # Invalid-state penalty: penalise x_{i,0}=1 AND x_{i,1}=1 simultaneously
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
            "eue_reduction_pct":(baseline_eue-eue)/max(baseline_eue,1e-9)*100,
            "runtime_sec":rt, "near_optimal_count":1}

milp = solve_milp(CANDIDATE_BUSES_20, SCENARIOS)
print(f"  Status:         {milp['status']}")
print(f"  Runtime:        {milp['runtime_sec']:.4f} s")
print(f"  Total BESS:     {milp['total_mw']} MW")
print(f"  EUE:            {milp['eue']:.4f} MW·prob")
print(f"  EUE Reduction:  {milp['eue_reduction_pct']:.2f}%")
print(f"  Siting plan:    {milp['allocation']}\n")

# ─── 7. D-WAVE SIMULATED ANNEALING (local) ───────────────────────────────────
print("-" * 70)
print("SOLVER B: D-Wave SimulatedAnnealingSampler (local, no credentials)")
print("-" * 70)

from dwave.samplers import SimulatedAnnealingSampler
import dimod

def run_dwave_sa(buses, scenarios, num_reads=3000, num_sweeps=5000):
    Q   = build_qubo(buses, scenarios)
    bqm = dimod.BinaryQuadraticModel.from_qubo(Q)
    sampler = SimulatedAnnealingSampler()
    t0 = time.time()
    resp = sampler.sample(bqm, num_reads=num_reads, num_sweeps=num_sweeps,
                          beta_range=[0.1, 5.0], beta_schedule_type="geometric", seed=42)
    rt = time.time()-t0

    threshold = milp["eue"] * 1.02
    near_opt, seen, best_eue, best_alloc = [], set(), float('inf'), {}
    for sample, _, _ in resp.data(['sample','energy','num_occurrences']):
        alloc = decode(sample, buses)
        cap   = sum(alloc.values())
        eue   = compute_eue(alloc, scenarios)
        key   = tuple(sorted(alloc.items()))
        if cap <= BUDGET_MW:
            if eue < best_eue:
                best_eue, best_alloc = eue, alloc
            if eue <= threshold and key not in seen:
                near_opt.append(alloc); seen.add(key)

    gap = max(0, (best_eue - milp["eue"]) / milp["eue"] * 100) if milp["eue"]>0 else 0
    return {"allocation":best_alloc, "total_mw":sum(best_alloc.values()),
            "eue":best_eue, "eue_reduction_pct":(baseline_eue-best_eue)/baseline_eue*100,
            "optimality_gap_pct":gap, "near_optimal_count":max(len(near_opt),1),
            "runtime_sec":rt, "num_reads":num_reads, "num_sweeps":num_sweeps}

dsa = run_dwave_sa(CANDIDATE_BUSES_20, SCENARIOS, num_reads=3000, num_sweeps=5000)
print(f"  Reads/Sweeps:   {dsa['num_reads']} / {dsa['num_sweeps']}")
print(f"  Runtime:        {dsa['runtime_sec']:.3f} s")
print(f"  Total BESS:     {dsa['total_mw']} MW")
print(f"  EUE:            {dsa['eue']:.4f} MW·prob")
print(f"  EUE Reduction:  {dsa['eue_reduction_pct']:.2f}%")
print(f"  Gap vs MILP:    {dsa['optimality_gap_pct']:.2f}%")
print(f"  Near-Optimal:   {dsa['near_optimal_count']} distinct portfolios\n")

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
        resp = sampler.sample(bqm, time_limit=10, label="GIC2026_Phase3_118bus")
        rt   = time.time()-t0

        threshold = milp["eue"] * 1.02
        near_opt, seen = [], set()
        for sample, _, _ in resp.data(['sample','energy','num_occurrences']):
            alloc = decode(sample, CANDIDATE_BUSES_20)
            cap   = sum(alloc.values())
            eue   = compute_eue(alloc, SCENARIOS)
            key   = tuple(sorted(alloc.items()))
            if eue <= threshold and cap <= BUDGET_MW and key not in seen:
                near_opt.append(alloc); seen.add(key)

        best_alloc = decode(resp.first.sample, CANDIDATE_BUSES_20)
        best_eue   = compute_eue(best_alloc, SCENARIOS)
        best_cap   = sum(best_alloc.values())
        gap        = max(0, (best_eue-milp["eue"])/milp["eue"]*100)

        leap = {"allocation":best_alloc, "total_mw":best_cap, "eue":best_eue,
                "eue_reduction_pct":(baseline_eue-best_eue)/baseline_eue*100,
                "optimality_gap_pct":gap, "near_optimal_count":max(len(near_opt),1),
                "runtime_sec":rt, "time_limit_sec":10,
                "problem_id": str(getattr(resp, 'problem_id', 'N/A'))}
        print(f"  Runtime:        {leap['runtime_sec']:.3f} s (time_limit=10s)")
        print(f"  Total BESS:     {leap['total_mw']} MW")
        print(f"  EUE:            {leap['eue']:.4f} MW·prob")
        print(f"  EUE Reduction:  {leap['eue_reduction_pct']:.2f}%")
        print(f"  Gap vs MILP:    {leap['optimality_gap_pct']:.2f}%")
        print(f"  Near-Optimal:   {leap['near_optimal_count']} distinct portfolios")
        print(f"  Problem ID:     {leap['problem_id']}\n")
    except Exception as e:
        print(f"  Error: {e}")
        print("  → Set DWAVE_API_TOKEN and retry with --leap\n")

# ─── 9. SCALING STUDY ────────────────────────────────────────────────────────
print("-" * 70)
print("SCALING STUDY: problem size vs solution quality and runtime")
print("-" * 70)
EXTRA_BUSES = [33, 46, 60, 74, 99]
ALL_BUSES   = CANDIDATE_BUSES_20 + EXTRA_BUSES
scaling     = []
for n in [10, 15, 20, 25]:
    buses = ALL_BUSES[:n]
    m = solve_milp(buses, SCENARIOS, tlim=30)
    d = run_dwave_sa(buses, SCENARIOS, num_reads=1000, num_sweeps=2000)
    scaling.append({"n":n, "qubits":n*N_BITS,
                    "milp_eue":m["eue"], "milp_rt":m["runtime_sec"],
                    "sa_eue":d["eue"],   "sa_rt":d["runtime_sec"],
                    "sa_gap":d["optimality_gap_pct"],
                    "sa_near_opt":d["near_optimal_count"]})
    print(f"  n={n:2d} | {n*N_BITS:2d} qubits | "
          f"MILP {m['eue']:.4f} ({m['runtime_sec']:.4f}s) | "
          f"SA {d['eue']:.4f} ({d['runtime_sec']:.3f}s) | "
          f"Gap {d['optimality_gap_pct']:.2f}% | Near-opt {d['near_optimal_count']}")
print()

# ─── 10. PENALTY SENSITIVITY ─────────────────────────────────────────────────
print("-" * 70)
print("PENALTY SENSITIVITY: lambda_budget sweep (15-bus subset)")
print("-" * 70)
buses15   = CANDIDATE_BUSES_20[:15]
pen_study = []
for lam in [2.0, 4.0, 6.0, 8.0, 10.0, 15.0]:
    Q   = build_qubo(buses15, SCENARIOS, lam=lam)
    bqm = dimod.BinaryQuadraticModel.from_qubo(Q)
    resp = SimulatedAnnealingSampler().sample(bqm, num_reads=500, num_sweeps=1500, seed=42)
    alloc = decode(resp.first.sample, buses15)
    cap   = sum(alloc.values())
    eue   = compute_eue(alloc, SCENARIOS)
    feasible = cap <= BUDGET_MW
    pen_study.append({"lambda":lam, "eue":round(eue,4), "cap":cap, "feasible":feasible})
    print(f"  lambda={lam:5.1f} | EUE={eue:.4f} | Cap={cap} MW | Feasible={feasible}")
print()

# ─── 11. FINAL RESULTS TABLE ─────────────────────────────────────────────────
print("=" * 70)
print("FINAL BENCHMARK RESULTS — IEEE 118-bus | 40 QUBO vars | 15 scenarios")
print("=" * 70)
print(f"{'Method':<36} {'EUE':>8} {'Red%':>7} {'Gap%':>7} {'Near-Opt':>9} {'Time':>8}")
print("-" * 70)
print(f"{'No BESS (baseline)':<36} {baseline_eue:>8.4f} {'—':>7} {'—':>7} {'—':>9} {'—':>8}")
print(f"{'MILP/HiGHS (optimal)':<36} {milp['eue']:>8.4f} "
      f"{milp['eue_reduction_pct']:>6.2f}% {'0.00%':>7} {'1':>9} {milp['runtime_sec']:>7.4f}s")
print(f"{'D-Wave SA (1000 reads, local)':<36} {dsa['eue']:>8.4f} "
      f"{dsa['eue_reduction_pct']:>6.2f}% {dsa['optimality_gap_pct']:>6.2f}% "
      f"{dsa['near_optimal_count']:>9} {dsa['runtime_sec']:>7.3f}s")
if leap:
    print(f"{'D-Wave LeapHybrid (QPU, 10s)':<36} {leap['eue']:>8.4f} "
          f"{leap['eue_reduction_pct']:>6.2f}% {leap['optimality_gap_pct']:>6.2f}% "
          f"{leap['near_optimal_count']:>9} {leap['runtime_sec']:>7.3f}s")
else:
    print(f"{'D-Wave LeapHybrid (QPU)':<36} {'→ run with --leap flag':>48}")
print("-" * 70)

# ─── 12. SAVE JSON ───────────────────────────────────────────────────────────
out = {
    "experiment": "GIC2026_Phase3_DOE_EnergyInfrastructure",
    "team": "Qudit Creons", "member": "Abhishek Raj",
    "test_system": "IEEE 118-bus (MATPOWER case118)",
    "ai_loads_mw": {"bus_49": 300, "bus_80": 300},
    "n_candidates": len(CANDIDATE_BUSES_20),
    "candidate_buses": CANDIDATE_BUSES_20,
    "n_qubits": len(CANDIDATE_BUSES_20)*N_BITS,
    "n_scenarios": len(SCENARIOS),
    "capital_budget_mw": BUDGET_MW,
    "baseline_eue": round(baseline_eue, 6),
    "milp": {k: round(v,6) if isinstance(v,float) else v for k,v in milp.items()},
    "dwave_sa": {k: round(v,6) if isinstance(v,float) else v for k,v in dsa.items()},
    "leap_hybrid": {k: round(v,6) if isinstance(v,float) else v
                    for k,v in leap.items()} if leap else None,
    "scaling_study": scaling,
    "penalty_sensitivity": pen_study,
}
with open("results_phase3.json", "w") as f:
    json.dump(out, f, indent=2)
print("\nResults saved → results_phase3.json")
print("To run on D-Wave QPU: DWAVE_API_TOKEN=<token> python experiment.py --leap")
print("=" * 70)

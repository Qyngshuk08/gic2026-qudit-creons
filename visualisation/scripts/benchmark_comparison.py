"""
GIC 2026 Phase 3 | Team Qudit Creons
Visualization 1: Benchmark Comparison — EUE Reduction & Optimality Gap by Method

Run: python viz_01_benchmark_comparison.py
Output: viz_01_benchmark_comparison.png (300 DPI, print-ready)
"""
import matplotlib.pyplot as plt
import numpy as np

# ── DOE-consistent enterprise palette ──────────────────────────────────────
NAVY   = "#1B2A4A"
STEEL  = "#2E5B8A"
GOLD   = "#C8A84B"
GREEN  = "#1A6B3A"
GRAY   = "#8A8A8A"
LGRAY  = "#F2F4F7"

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 11,
    "axes.edgecolor": "#333333",
    "axes.linewidth": 0.8,
    "figure.facecolor": "white",
})

# ── Real data from Phase 3 execution ────────────────────────────────────────
methods = [
    "No BESS\n(baseline)",
    "MILP\n(HiGHS, exact)",
    "D-Wave\nLeapHybrid",
    "D-Wave SA\n(best of 10)",
    "D-Wave Raw QPU\n(direct anneal)",
    "D-Wave SA\n(mean of 10)",
    "IBM QAOA\n+COBYLA",
]
eue_reduction = [0.0, 92.12, 91.98, 91.91, 91.64, 90.16, 84.92]
gap_pct       = [None, 0.0, 1.73, 2.66, 6.05, 24.80, 50.06]

colors = [GRAY, NAVY, GREEN, STEEL, STEEL, GOLD, "#8B2E2E"]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))

# ── Panel 1: EUE Reduction % ────────────────────────────────────────────────
bars1 = ax1.barh(methods, eue_reduction, color=colors, edgecolor="white", height=0.65)
ax1.set_xlabel("EUE Reduction vs. No-BESS Baseline (%)", fontsize=11, fontweight="bold")
ax1.set_xlim(0, 100)
ax1.set_title("Solution Quality", fontsize=13, fontweight="bold", color=NAVY, pad=12)
ax1.grid(axis="x", linestyle="--", alpha=0.3)
ax1.set_axisbelow(True)
for bar, val in zip(bars1, eue_reduction):
    ax1.text(val + 1.5, bar.get_y() + bar.get_height()/2, f"{val:.1f}%",
              va="center", fontsize=9.5, color="#222222", fontweight="bold")

# ── Panel 2: Optimality Gap % (log scale, excludes baseline) ───────────────
methods2 = methods[1:]
gaps2 = gap_pct[1:]
colors2 = colors[1:]
bars2 = ax2.barh(methods2, gaps2, color=colors2, edgecolor="white", height=0.65)
ax2.set_xlabel("Optimality Gap vs. MILP (%, log scale)", fontsize=11, fontweight="bold")
ax2.set_xscale("log")
ax2.set_xlim(0.5, 100)
ax2.set_title("Distance from Proven Optimum", fontsize=13, fontweight="bold", color=NAVY, pad=12)
ax2.grid(axis="x", linestyle="--", alpha=0.3, which="both")
ax2.set_axisbelow(True)
for bar, val in zip(bars2, gaps2):
    label = "0.0% (exact)" if val == 0 else f"{val:.2f}%"
    xpos = max(val, 0.6) * 1.15
    ax2.text(xpos, bar.get_y() + bar.get_height()/2, label,
              va="center", fontsize=9.5, color="#222222", fontweight="bold")

fig.suptitle("IEEE 118-Bus BESS Siting — Full Benchmark Comparison",
             fontsize=15, fontweight="bold", color=NAVY, y=1.02)
fig.text(0.5, -0.02,
          "Team Qudit Creons | GIC 2026 Phase 3 | DOE Energy Infrastructure Challenge  •  "
          "All results from real hardware/solver execution, reproducible via experiment.py",
          ha="center", fontsize=8.5, color=GRAY, style="italic")

plt.tight_layout()
plt.savefig("viz_01_benchmark_comparison.png", dpi=300, bbox_inches="tight", facecolor="white")
print("Saved: viz_01_benchmark_comparison.png")
plt.close()

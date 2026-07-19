"""
GIC 2026 Phase 3 | Team Qudit Creons
Visualization 2: Scaling Study — Optimality Gap vs. Problem Size (Qubits)

Run: python viz_02_scaling_study.py
Output: viz_02_scaling_study.png (300 DPI, print-ready)
"""
import matplotlib.pyplot as plt
import numpy as np

NAVY, STEEL, GOLD, GREEN, GRAY = "#1B2A4A", "#2E5B8A", "#C8A84B", "#1A6B3A", "#8A8A8A"

plt.rcParams.update({
    "font.family": "serif", "font.size": 11,
    "axes.edgecolor": "#333333", "axes.linewidth": 0.8,
    "figure.facecolor": "white",
})

# ── Real scaling-study data (candidate buses -> qubits) ────────────────────
n_buses = [10, 15, 20, 25]
qubits  = [n * 2 for n in n_buses]
milp_eue = [6.2985, 4.9398, 4.9398, 4.9398]
sa_eue   = [9.5038, 5.9998, 6.6296, 7.8827]
sa_gap   = [92.39, 21.46, 34.21, 59.57]

fig, ax1 = plt.subplots(figsize=(10, 6))

# EUE lines on primary axis
l1 = ax1.plot(qubits, milp_eue, marker="o", markersize=8, linewidth=2.2,
              color=NAVY, label="MILP (exact optimum)", zorder=5)
l2 = ax1.plot(qubits, sa_eue, marker="s", markersize=8, linewidth=2.2,
              color=STEEL, linestyle="--", label="D-Wave SA (mean)", zorder=5)
ax1.set_xlabel("Problem Size (QUBO Binary Variables / Qubits)", fontsize=11.5, fontweight="bold")
ax1.set_ylabel("Expected Unserved Energy (MW·prob)", fontsize=11.5, fontweight="bold", color=NAVY)
ax1.set_xticks(qubits)
ax1.set_xticklabels([f"{q}\n({n} buses)" for q, n in zip(qubits, n_buses)])
ax1.tick_params(axis="y", labelcolor=NAVY)
ax1.grid(True, linestyle="--", alpha=0.3)
ax1.set_axisbelow(True)

# Gap % on secondary axis
ax2 = ax1.twinx()
l3 = ax2.plot(qubits, sa_gap, marker="D", markersize=8, linewidth=2.2,
              color=GOLD, label="SA Optimality Gap (%)", zorder=5)
ax2.set_ylabel("SA Optimality Gap vs. MILP (%)", fontsize=11.5, fontweight="bold", color="#8B6914")
ax2.tick_params(axis="y", labelcolor="#8B6914")
ax2.set_ylim(0, 100)

# Annotate the "well-conditioned" region
ax1.annotate("Best-conditioned region\n(lowest gap, 21.5%)",
             xy=(30, 21.46), xytext=(34, 5.5),
             fontsize=9.5, color=GREEN, fontweight="bold",
             arrowprops=dict(arrowstyle="->", color=GREEN, lw=1.5))

lines = l1 + l2 + l3
labels = [l.get_label() for l in lines]
ax1.legend(lines, labels, loc="upper left", fontsize=10, frameon=True,
           framealpha=0.95, edgecolor="#CCCCCC")

ax1.set_title("Scaling Behaviour: Classical Simulated Annealing vs. Problem Size",
              fontsize=14, fontweight="bold", color=NAVY, pad=14)
fig.text(0.5, -0.03,
          "Team Qudit Creons | GIC 2026 Phase 3 | DOE Energy Infrastructure Challenge  •  "
          "Gap is non-monotonic: SA quality depends on QUBO landscape conditioning, not just size",
          ha="center", fontsize=8.5, color=GRAY, style="italic")

plt.tight_layout()
plt.savefig("viz_02_scaling_study.png", dpi=300, bbox_inches="tight", facecolor="white")
print("Saved: viz_02_scaling_study.png")
plt.close()

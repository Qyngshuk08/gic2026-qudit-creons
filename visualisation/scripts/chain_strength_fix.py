"""
GIC 2026 Phase 3 | Team Qudit Creons
Visualization 4: D-Wave Raw QPU — Chain-Strength Fix (Before / After)

Run: python viz_04_chain_strength_fix.py
Output: viz_04_chain_strength_fix.png (300 DPI, print-ready)
"""
import matplotlib.pyplot as plt
import numpy as np

NAVY, STEEL, GOLD, GREEN, RED, GRAY = "#1B2A4A", "#2E5B8A", "#C8A84B", "#1A6B3A", "#8B2E2E", "#8A8A8A"

plt.rcParams.update({
    "font.family": "serif", "font.size": 11,
    "axes.edgecolor": "#333333", "axes.linewidth": 0.8,
    "figure.facecolor": "white",
})

# ── Real before/after data from raw-QPU runs on Advantage2_system1 ─────────
labels = ["Default chain\nstrength (v3)", "Tuned chain strength\nuniform_torque_\ncompensation (v4)"]
chain_break_frac = [0.20, 0.00]
feasibility_rate = [0.0, 42.5]   # % of 200 reads that were budget-feasible

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5.5))

# Panel 1: Chain-break fraction
bars1 = ax1.bar(labels, chain_break_frac, color=[RED, GREEN], width=0.55, edgecolor="white")
ax1.set_ylabel("Mean Chain-Break Fraction", fontsize=11.5, fontweight="bold")
ax1.set_ylim(0, 0.28)
ax1.set_title("Chain Integrity", fontsize=13, fontweight="bold", color=NAVY, pad=12)
ax1.grid(axis="y", linestyle="--", alpha=0.3)
ax1.set_axisbelow(True)
for bar, val in zip(bars1, chain_break_frac):
    ax1.text(bar.get_x() + bar.get_width()/2, val + 0.01, f"{val:.2f}",
              ha="center", fontsize=12, fontweight="bold", color="#222222")

# Panel 2: Feasibility rate
bars2 = ax2.bar(labels, feasibility_rate, color=[RED, GREEN], width=0.55, edgecolor="white")
ax2.set_ylabel("Budget-Feasible Reads (% of 200)", fontsize=11.5, fontweight="bold")
ax2.set_ylim(0, 55)
ax2.set_title("Solution Feasibility", fontsize=13, fontweight="bold", color=NAVY, pad=12)
ax2.grid(axis="y", linestyle="--", alpha=0.3)
ax2.set_axisbelow(True)
for bar, val in zip(bars2, feasibility_rate):
    label = "0/200\n(0.0%)" if val == 0 else "85/200\n(42.5%)"
    ax2.text(bar.get_x() + bar.get_width()/2, val + 1.5, label,
              ha="center", fontsize=11, fontweight="bold", color="#222222")

fig.suptitle("Diagnosed Hardware Fix: Coefficient Dynamic-Range Mismatch",
             fontsize=14.5, fontweight="bold", color=NAVY, y=1.03)
fig.text(0.5, 0.92,
          "QUBO mixes ~0.001–5 objective coefficients with ~1000s penalty coefficients — auto_scale\n"
          "compresses this range on real hardware, degrading chain integrity under default settings.",
          ha="center", fontsize=9.5, color="#444444", style="italic")
fig.text(0.5, -0.02,
          "Team Qudit Creons | GIC 2026 Phase 3 | DOE Energy Infrastructure Challenge  •  "
          "Advantage2_system1 (Zephyr), 40 logical / 178 physical qubits, 200 reads",
          ha="center", fontsize=8.5, color=GRAY, style="italic")

plt.tight_layout(rect=[0, 0, 1, 0.90])
plt.savefig("viz_04_chain_strength_fix.png", dpi=300, bbox_inches="tight", facecolor="white")
print("Saved: viz_04_chain_strength_fix.png")
plt.close()

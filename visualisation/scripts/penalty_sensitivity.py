"""
GIC 2026 Phase 3 | Team Qudit Creons
Visualization 6: QUBO Penalty Sensitivity — lambda_budget Sweep

Run: python viz_06_penalty_sensitivity.py
Output: viz_06_penalty_sensitivity.png (300 DPI, print-ready)
"""
import matplotlib.pyplot as plt
import numpy as np

NAVY, STEEL, GOLD, GREEN, GRAY, LGRAY = "#1B2A4A", "#2E5B8A", "#C8A84B", "#1A6B3A", "#8A8A8A", "#F2F4F7"

plt.rcParams.update({
    "font.family": "serif", "font.size": 11,
    "axes.edgecolor": "#333333", "axes.linewidth": 0.8,
    "figure.facecolor": "white",
})

# ── Real penalty-sensitivity sweep data (15-bus subset) ────────────────────
lambdas = [2.0, 4.0, 6.0, 8.0, 10.0, 15.0]
eue_vals = [6.2363, 6.6400, 6.7611, 6.0425, 6.9219, 6.4462]
feasible = [True, True, True, True, True, True]

# Analytically-derived operating point (from the v3/v4 experiment)
lambda_min = 0.1595
lambda_applied = 0.2392

fig, ax = plt.subplots(figsize=(10.5, 6))

colors = [GREEN if f else "#B85450" for f in feasible]
ax.plot(lambdas, eue_vals, marker="o", markersize=9, linewidth=2, color=STEEL, zorder=4)
for lam, eue, c in zip(lambdas, eue_vals, colors):
    ax.scatter(lam, eue, s=120, color=c, edgecolor="white", linewidth=1.5, zorder=5)

ax.axhline(y=min(eue_vals), color=GOLD, linestyle=":", linewidth=1.3, alpha=0.7,
           label=f"Best EUE in sweep ({min(eue_vals):.4f} at \u03bb={lambdas[np.argmin(eue_vals)]})")

ax.set_xlabel("Penalty Strength \u03bb_budget (empirical sweep)", fontsize=11.5, fontweight="bold")
ax.set_ylabel("EUE (MW\u00b7prob), 15-bus subset", fontsize=11.5, fontweight="bold")
ax.set_title("QUBO Penalty Sensitivity — All Tested Values Remain Feasible",
              fontsize=14, fontweight="bold", color=NAVY, pad=14)
ax.grid(True, linestyle="--", alpha=0.3)
ax.set_axisbelow(True)
ax.legend(loc="upper left", fontsize=10, frameon=True, framealpha=0.95, edgecolor="#CCCCCC")

# Annotation: analytical derivation used for main 20-bus experiment
textstr = (
    "Analytically-derived bound used in main experiment (20-bus, 40-var problem):\n"
    f"  \u03bb_min (provable sufficient condition) = {lambda_min:.4f}\n"
    f"  \u03bb_applied (1.5\u00d7 safety margin)         = {lambda_applied:.4f}\n"
    "This sweep (\u03bb=2\u201315) validates that the QUBO remains feasible across a wide\n"
    "empirical range, independent of the analytical derivation used for production runs."
)
props = dict(boxstyle="round,pad=0.6", facecolor=LGRAY, edgecolor=NAVY, linewidth=1.0)
ax.text(0.35, 0.03, textstr, transform=ax.transAxes, fontsize=9,
        verticalalignment="bottom", bbox=props, family="monospace")

fig.text(0.5, -0.02,
          "Team Qudit Creons | GIC 2026 Phase 3 | DOE Energy Infrastructure Challenge  •  "
          "All 6 tested lambda values (D-Wave SimulatedAnnealingSampler) produced budget-feasible solutions",
          ha="center", fontsize=8.5, color=GRAY, style="italic")

plt.tight_layout()
plt.savefig("viz_06_penalty_sensitivity.png", dpi=300, bbox_inches="tight", facecolor="white")
print("Saved: viz_06_penalty_sensitivity.png")
plt.close()

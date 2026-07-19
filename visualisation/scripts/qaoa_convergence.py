"""
GIC 2026 Phase 3 | Team Qudit Creons
Visualization 3: IBM QAOA + COBYLA Convergence Trace (Real Hardware, 25 Iterations)

Run: python viz_03_qaoa_convergence.py
Output: viz_03_qaoa_convergence.png (300 DPI, print-ready)
"""
import matplotlib.pyplot as plt
import numpy as np

NAVY, STEEL, GOLD, GREEN, RED, GRAY = "#1B2A4A", "#2E5B8A", "#C8A84B", "#1A6B3A", "#8B2E2E", "#8A8A8A"

plt.rcParams.update({
    "font.family": "serif", "font.size": 11,
    "axes.edgecolor": "#333333", "axes.linewidth": 0.8,
    "figure.facecolor": "white",
})

# ── Real convergence log from ibm_fez, 25 COBYLA iterations ────────────────
iterations = list(range(1, 26))
exp_eue = [
    39.2067, 41.9975, 41.0589, 37.5846, 39.9973, 38.1474, 39.5847, 40.1122,
    37.2707, 37.6062, 38.9185, 41.2384, 41.0700, 41.3407, 40.2208, 37.5226,
    37.2059, 37.4919, 38.9628, 39.5556, 41.1358, 40.5337, 40.6272, 40.5572,
    39.6137
]
final_extracted_eue = 9.4513  # what best-of-shots actually returned

fig, ax = plt.subplots(figsize=(11, 6))

ax.plot(iterations, exp_eue, marker="o", markersize=6, linewidth=1.8,
        color=STEEL, label="COBYLA objective (expectation-weighted EUE)", zorder=5)
ax.axhline(y=np.mean(exp_eue), color=GOLD, linestyle="--", linewidth=1.5,
           label=f"Mean across 25 iterations ({np.mean(exp_eue):.2f})", zorder=3)

# Shade the oscillation band
ax.fill_between(iterations, min(exp_eue), max(exp_eue), color=STEEL, alpha=0.05)

ax.set_xlabel("COBYLA Iteration (= 1 real IBM QPU job)", fontsize=11.5, fontweight="bold")
ax.set_ylabel("Expectation-Weighted EUE (MW·prob)", fontsize=11.5, fontweight="bold")
ax.set_title("IBM ibm_fez QAOA (p=1) — COBYLA Parameter Search Diagnostic",
              fontsize=14, fontweight="bold", color=NAVY, pad=14)
ax.grid(True, linestyle="--", alpha=0.3)
ax.set_axisbelow(True)
ax.legend(loc="upper right", fontsize=10, frameon=True, framealpha=0.95, edgecolor="#CCCCCC")
ax.set_xlim(0.5, 25.5)
ax.set_xticks(range(1, 26, 2))

# Diagnostic annotation box
textstr = (
    "Diagnostic finding:\n"
    f"• Objective oscillates {min(exp_eue):.1f}\u2013{max(exp_eue):.1f} with no convergence trend\n"
    f"• Final extracted answer (best-of-2048-shots): EUE={final_extracted_eue:.4f}\n"
    "  — identical to an unoptimised single-shot run\n"
    "• Diagnosis: p=1 output distribution too broad for shot-based\n"
    "  extraction to track small COBYLA parameter updates\n"
    "• Fix (Phase 4): EstimatorV2 expectation scoring, or p\u22652 circuits"
)
props = dict(boxstyle="round,pad=0.6", facecolor="#FFF8E7", edgecolor=GOLD, linewidth=1.2)
ax.text(0.02, 0.03, textstr, transform=ax.transAxes, fontsize=9,
        verticalalignment="bottom", bbox=props, family="monospace")

fig.text(0.5, -0.02,
          "Team Qudit Creons | GIC 2026 Phase 3 | DOE Energy Infrastructure Challenge  •  "
          "26 real QPU jobs on ibm_fez (156 qubits), job IDs logged in results_phase3_v4.json",
          ha="center", fontsize=8.5, color=GRAY, style="italic")

plt.tight_layout()
plt.savefig("viz_03_qaoa_convergence.png", dpi=300, bbox_inches="tight", facecolor="white")
print("Saved: viz_03_qaoa_convergence.png")
plt.close()

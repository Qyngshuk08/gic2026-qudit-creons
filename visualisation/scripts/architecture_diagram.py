"""
GIC 2026 Phase 3 | Team Qudit Creons
Visualization 7: Hybrid Quantum-Classical Architecture — Three Execution Paths

Run: python viz_07_architecture_diagram.py
Output: viz_07_architecture_diagram.png (300 DPI, print-ready)
"""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

NAVY, STEEL, GOLD, GREEN, GRAY, LGRAY = "#1B2A4A", "#2E5B8A", "#C8A84B", "#1A6B3A", "#8A8A8A", "#F2F4F7"
WHITE = "#FFFFFF"

plt.rcParams.update({"font.family": "serif", "figure.facecolor": "white"})

fig, ax = plt.subplots(figsize=(13, 8.5))
ax.set_xlim(0, 13)
ax.set_ylim(0, 8.5)
ax.axis("off")

def box(x, y, w, h, text, facecolor, textcolor="white", fontsize=10, bold=True, edgecolor="white"):
    b = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.12",
                        facecolor=facecolor, edgecolor=edgecolor, linewidth=1.2, zorder=3)
    ax.add_patch(b)
    ax.text(x + w/2, y + h/2, text, ha="center", va="center", fontsize=fontsize,
            color=textcolor, fontweight="bold" if bold else "normal", zorder=4,
            linespacing=1.4)
    return b

def arrow(x1, y1, x2, y2, color=NAVY, style="-|>", lw=1.8, connectionstyle="arc3,rad=0"):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, color=color,
                         linewidth=lw, mutation_scale=16, zorder=2,
                         connectionstyle=connectionstyle)
    ax.add_patch(a)

# ── Title ────────────────────────────────────────────────────────────────
ax.text(6.5, 8.15, "Hybrid Quantum-Classical Architecture — BESS Siting QUBO",
        ha="center", fontsize=16, fontweight="bold", color=NAVY)
ax.text(6.5, 7.75, "IEEE 118-Bus, 40-Variable QUBO, Executed Through Three Independent Paths",
        ha="center", fontsize=10.5, color="#444444", style="italic")

# ── Input layer ──────────────────────────────────────────────────────────
box(4.9, 6.6, 3.2, 0.7, "Grid Data + Scenarios\n(IEEE 118-bus, 15 scenarios)", NAVY, fontsize=9.5)
arrow(6.5, 6.6, 6.5, 6.15)

box(4.4, 5.5, 4.2, 0.65, "QUBO Construction\nH = H_obj + \u03bb\u00b7H_budget + \u03bc\u00b7H_invalid\n(analytically-derived \u03bb)",
    STEEL, fontsize=9)
arrow(6.5, 5.5, 6.5, 5.05)

# ── Three execution paths (branch) ──────────────────────────────────────
ax.text(6.5, 4.85, "Three Independent Execution Paths", ha="center", fontsize=11,
        fontweight="bold", color=NAVY)

# branch lines
arrow(6.5, 4.65, 2.2, 4.2, color=GRAY, lw=1.3)
arrow(6.5, 4.65, 6.5, 4.2, color=GRAY, lw=1.3)
arrow(6.5, 4.65, 10.8, 4.2, color=GRAY, lw=1.3)

# Path 1: D-Wave Hybrid
box(0.6, 3.35, 3.2, 0.85, "D-Wave LeapHybridSampler\n(classical decomposition + QPU)", GREEN, fontsize=9)
arrow(2.2, 3.35, 2.2, 2.85)
box(0.6, 2.15, 3.2, 0.7, "Result: 1.73% gap\n(BEST — real QPU)", GREEN, fontsize=9.5)

# Path 2: D-Wave Raw QPU
box(4.9, 3.35, 3.2, 0.85, "DWaveSampler +\nEmbeddingComposite\n(direct anneal, no decomposition)", STEEL, fontsize=9)
arrow(6.5, 3.35, 6.5, 2.85)
box(4.9, 2.15, 3.2, 0.7, "Result: 6.05% gap\n(178 physical qubits)", STEEL, fontsize=9.5)

# Path 3: IBM QAOA
box(9.2, 3.35, 3.2, 0.85, "IBM QAOA (p=1) + COBYLA\n(gate-based, 20-qubit subset)", GOLD, textcolor="#3A2E00", fontsize=9)
arrow(10.8, 3.35, 10.8, 2.85)
box(9.2, 2.15, 3.2, 0.7, "Result: 50.06% gap\n(extraction-limited)", GOLD, textcolor="#3A2E00", fontsize=9.5)

# ── Classical baseline (side reference) ──────────────────────────────────
box(0.6, 0.9, 3.2, 0.7, "Classical MILP (HiGHS)\nProven optimal: 0.00% gap", NAVY, fontsize=9.5)
box(4.9, 0.9, 3.2, 0.7, "D-Wave SA (10 seeds)\nBest: 2.66% | Mean: 24.80%", "#6B6B6B", fontsize=9.5)
box(9.2, 0.9, 3.2, 0.7, "Economic Layer\nCAPEX + VOLL monetization", "#5A4A7A", fontsize=9.5)

ax.text(6.5, 0.35, "Benchmark & Verification Layer (all paths compared on identical QUBO instance)",
        ha="center", fontsize=9.5, color="#444444", style="italic")

# footer
fig.text(0.5, 0.01,
         "Team Qudit Creons | GIC 2026 Phase 3 | DOE Energy Infrastructure Challenge",
         ha="center", fontsize=8.5, color=GRAY, style="italic")

plt.tight_layout()
plt.savefig("viz_07_architecture_diagram.png", dpi=300, bbox_inches="tight", facecolor="white")
print("Saved: viz_07_architecture_diagram.png")
plt.close()

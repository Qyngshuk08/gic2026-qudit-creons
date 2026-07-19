"""
GIC 2026 Phase 3 | Team Qudit Creons
Visualization 5: Economic Analysis — Capital Cost vs. Annual Outage-Cost Savings

Run: python viz_05_economic_analysis.py
Output: viz_05_economic_analysis.png (300 DPI, print-ready)

CAVEAT (also stated on the chart): baseline EUE is a stylized benchmarking construct,
~100-1000x larger than real NERC reliability targets. Dollar figures illustrate
methodology only — valid for comparing solvers on the identical instance, not
investment guidance. See README / write-up Section 4 for full explanation.
"""
import matplotlib.pyplot as plt
import numpy as np

NAVY, STEEL, GOLD, GREEN, GRAY = "#1B2A4A", "#2E5B8A", "#C8A84B", "#1A6B3A", "#8A8A8A"

plt.rcParams.update({
    "font.family": "serif", "font.size": 11,
    "axes.edgecolor": "#333333", "axes.linewidth": 0.8,
    "figure.facecolor": "white",
})

# ── Real economic figures (CAPEX $0.8M/MW, VOLL $10,000/MWh) ───────────────
methods = ["MILP\n(optimal)", "D-Wave\nLeapHybrid", "D-Wave SA\n(best of 10)",
           "D-Wave Raw QPU", "D-Wave SA\n(mean of 10)"]
eue_vals = [4.9398, 5.0252, 5.0713, 5.2385, 6.1651]
baseline_eue = 62.6671
capex_musd = [400.0, 400.0, 400.0, 400.0, 400.0]  # all use full 500 MW budget
annual_savings_musd = [(baseline_eue - e) * 8760 * 10000 / 1e6 for e in eue_vals]
payback_days = [(capex_musd[i] * 1e6) / (annual_savings_musd[i] * 1e6) * 365
                 for i in range(len(methods))]

fig, ax1 = plt.subplots(figsize=(11, 6.5))

x = np.arange(len(methods))
width = 0.38

bars1 = ax1.bar(x - width/2, capex_musd, width, label="Capital Cost ($M)",
                 color=NAVY, edgecolor="white")
ax1.set_ylabel("Capital Cost ($M)", fontsize=11.5, fontweight="bold", color=NAVY)
ax1.tick_params(axis="y", labelcolor=NAVY)
ax1.set_ylim(0, 500)

ax2 = ax1.twinx()
bars2 = ax2.bar(x + width/2, annual_savings_musd, width, label="Annual Outage-Cost Savings ($M/yr)",
                 color=GOLD, edgecolor="white")
ax2.set_ylabel("Annual Outage-Cost Savings ($M/yr)", fontsize=11.5, fontweight="bold", color="#8B6914")
ax2.tick_params(axis="y", labelcolor="#8B6914")
ax2.set_ylim(0, 6000)

ax1.set_xticks(x)
ax1.set_xticklabels(methods, fontsize=10)
ax1.set_title("Economic Comparison Across Solution Methods",
              fontsize=14.5, fontweight="bold", color=NAVY, pad=16)
ax1.grid(axis="y", linestyle="--", alpha=0.25)
ax1.set_axisbelow(True)

for i, (bar1, days) in enumerate(zip(bars1, payback_days)):
    ax1.text(bar1.get_x() + bar1.get_width()/2, 415, f"{days:.0f}-day\npayback",
              ha="center", fontsize=8.5, color=NAVY, fontweight="bold")

lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right", fontsize=9.5,
           frameon=True, framealpha=0.95, edgecolor="#CCCCCC")

# Caveat box
caveat = (
    "METHODOLOGY CAVEAT: baseline EUE is a stylized benchmarking construct (~2.6% of annual\n"
    "energy unserved), ~100\u20131000x larger than real NERC reliability targets (<0.01%). Figures\n"
    "compare solvers on the identical instance; not calibrated investment guidance. See write-up \u00a74."
)
props = dict(boxstyle="round,pad=0.5", facecolor="#FFF3F3", edgecolor="#B85450", linewidth=1.0)
fig.text(0.5, -0.08, caveat, ha="center", fontsize=8.5, color="#7A2E2E",
          bbox=props, family="monospace")

fig.text(0.5, -0.15,
          "Team Qudit Creons | GIC 2026 Phase 3 | DOE Energy Infrastructure Challenge  •  "
          "CAPEX: NREL 2024 ATB ($0.8M/MW); VOLL: DOE/LBNL ICE Calculator ($10,000/MWh)",
          ha="center", fontsize=8.5, color=GRAY, style="italic")

plt.tight_layout()
plt.savefig("viz_05_economic_analysis.png", dpi=300, bbox_inches="tight", facecolor="white")
print("Saved: viz_05_economic_analysis.png")
plt.close()

#!/usr/bin/env python3
"""Generate the two signature figures as PDF images (matplotlib), reflecting the corrected
(arity-matched) analysis. Run scripts/arity_null.py first to produce results/arity_null.json.

Figure A (f_arity.pdf): per-cell disparity ratio under the naive comparison (MASD / 2-run pairwise
noise floor) versus the arity-matched comparison (MASD / 6-group noise spread). Shows the naive
ratio (~2.4x, mean) collapsing below 1.0 once the noise floor is matched to the statistic's arity.

Figure B (f_scaffold.pdf): arity-matched MASD-to-noise ratio along the C0->C2->C3 scaffold ladder
per domain, all below the dotted 1.0 line and without an above-noise upward trend -- i.e., no
scaffold amplification is detected above noise (BCF P3 not instantiated on this model at this scale).

Image figures are used because pgfplots/TikZ is incompatible with ieeeaccess.cls; the official
template likewise uses includegraphics image figures.
"""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "paper" / "figures"; FIG.mkdir(parents=True, exist_ok=True)
rows = json.loads((ROOT / "results" / "arity_null.json").read_text(encoding="utf-8"))
order = [r["cell"] for r in rows]
by = {r["cell"]: r for r in rows}

# ---- Figure A: naive vs arity-matched ratio per cell ----
fig, ax = plt.subplots(figsize=(7.2, 3.2))
labels = order
x = range(len(labels))
old = [by[c]["old_ratio"] for c in labels]
new = [by[c]["new_ratio"] for c in labels]
ax.bar([i - 0.2 for i in x], old, width=0.4, label="naive: MASD / 2-run pairwise floor", color="#bbbbbb")
ax.bar([i + 0.2 for i in x], new, width=0.4, label="arity-matched: MASD / 6-group noise spread", color="#d62728")
ax.axhline(1.0, color="black", ls=":", lw=1.2)
ax.text(len(labels) - 0.5, 1.04, "noise floor (1.0)", ha="right", va="bottom", fontsize=8)
ax.set_xticks(list(x)); ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
ax.set_ylabel("MASD-to-noise ratio")
ax.set_ylim(0, 3.6); ax.grid(axis="y", alpha=0.25)
ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=2, fontsize=8, frameon=False)
fig.tight_layout()
fig.savefig(FIG / "f_arity.pdf", bbox_inches="tight")
fig.savefig(FIG / "f_arity.png", dpi=160, bbox_inches="tight")
plt.close(fig)

# ---- Figure B: arity-matched ratio vs scaffold per domain ----
fig, ax = plt.subplots(figsize=(7.2, 3.2))
DOMAINS = {"hir": ("hiring", "#1f77b4"), "len": ("lending", "#ff7f0e"), "tri": ("triage", "#2ca02c")}
SC = ["C0", "C2", "C3"]
for pref, (name, col) in DOMAINS.items():
    ys = [by[f"{pref}-{s}"]["new_ratio"] for s in SC]
    ax.plot(range(len(SC)), ys, marker="o", lw=2, color=col, label=name)
ax.axhline(1.0, color="black", ls=":", lw=1.2)
ax.text(2.0, 1.02, "noise floor (1.0)", ha="right", va="bottom", fontsize=8)
ax.set_xticks(range(len(SC))); ax.set_xticklabels(["C0\n(direct)", "C2\n(reasoning)", "C3\n(deliberation)"])
ax.set_xlabel("Agent scaffold (increasing agency)")
ax.set_ylabel("Arity-matched\nMASD-to-noise ratio")
ax.set_ylim(0, 1.25); ax.grid(alpha=0.25)
ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=3, fontsize=8, frameon=False)
fig.tight_layout()
fig.savefig(FIG / "f_scaffold.pdf", bbox_inches="tight")
fig.savefig(FIG / "f_scaffold.png", dpi=160, bbox_inches="tight")
plt.close(fig)
print("wrote paper/figures/f_arity.pdf and f_scaffold.pdf")

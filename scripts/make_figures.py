#!/usr/bin/env python3
"""Generate the two signature figures as PDF images (matplotlib), from the v1.1
repeated-measures analysis (results/v11/analysis.json).

Figure A (f_arity.pdf): per-cell disparity ratio under the naive comparison (MASD / 2-run
pairwise noise floor, derived as arity_matched.ratio * arity_constants.inflation_6_groups)
versus the arity-matched comparison (MASD / 6-group noise spread, arity_matched.ratio, with
its arity_matched.ratio_ci as an error bar). Shows the naive ratio sitting well above 1.0
collapsing to at-or-below 1.0 once the noise floor is matched to the statistic's arity.

Figure B (f_scaffold.pdf): arity-matched MASD-to-noise ratio (with CI) along the
C0 -> C0L -> C2 -> C3 -> C4 scaffold ladder, one series per model/domain, all at or below
the dotted 1.0 line and without an upward trend as agency increases -- i.e., no scaffold
amplification is detected above noise.

Image figures are used because pgfplots/TikZ is incompatible with ieeeaccess.cls; the
official template likewise uses includegraphics image figures.

Every plotted number is read from results/v11/analysis.json; nothing is hardcoded. Cells
missing the fields a figure needs are skipped rather than invented.
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "paper" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

analysis = json.loads((ROOT / "results" / "v11" / "analysis.json").read_text(encoding="utf-8"))
per_cell = analysis["per_cell"]
inflation_6_groups = analysis["arity_constants"]["inflation_6_groups"]

ABBR_MODEL = {"fable": "fab", "haiku": "hai", "sonnet": "son"}
ABBR_DOMAIN = {"hiring": "hir", "lending": "len", "triage": "tri"}
SCAFFOLD_ORDER = ["C0", "C0L", "C2", "C3", "C4"]

MARKERS = ["o", "s", "^", "D", "v", "P", "X"]
LINESTYLES = ["-", "--", "-.", ":", (0, (3, 1, 1, 1)), (0, (5, 1)), (0, (1, 1))]
COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2"]


def cell_rows():
    """Yield one dict per reported cell that carries the arity_matched fields we need."""
    for key, v in per_cell.items():
        am = v.get("arity_matched")
        if not am or "ratio" not in am or "ratio_ci" not in am:
            continue
        ci = am["ratio_ci"]
        if ci is None or len(ci) != 2:
            continue
        model, domain, scaffold = key.split("/")
        matched = am["ratio"]
        yield {
            "key": key,
            "model": model,
            "domain": domain,
            "scaffold": scaffold,
            "matched": matched,
            "ci_lo": ci[0],
            "ci_hi": ci[1],
            "naive": matched * inflation_6_groups,
        }


rows = list(cell_rows())

# ---------------------------------------------------------------------------
# Figure A: naive vs arity-matched ratio, one pair of bars per reported cell
# ---------------------------------------------------------------------------
n = len(rows)
labels = [
    "{}-{}-{}".format(
        ABBR_MODEL.get(r["model"], r["model"]),
        ABBR_DOMAIN.get(r["domain"], r["domain"]),
        r["scaffold"],
    )
    for r in rows
]
x = list(range(n))
naive_vals = [r["naive"] for r in rows]
matched_vals = [r["matched"] for r in rows]
err_lo = [max(0.0, r["matched"] - r["ci_lo"]) for r in rows]
err_hi = [max(0.0, r["ci_hi"] - r["matched"]) for r in rows]

fig, ax = plt.subplots(figsize=(7.2, 4.8))
w = 0.38
ax.bar(
    [i - w / 2 for i in x],
    naive_vals,
    width=w,
    color="#bbbbbb",
    edgecolor="black",
    linewidth=0.5,
    hatch="////",
    label="naive: MASD / 2-run pairwise floor (= arity-matched ratio x arity inflation)",
    zorder=2,
)
ax.bar(
    [i + w / 2 for i in x],
    matched_vals,
    width=w,
    color="#d62728",
    edgecolor="black",
    linewidth=0.5,
    label="arity-matched: MASD / 6-group null, with 95% CI",
    zorder=2,
)
ax.errorbar(
    [i + w / 2 for i in x],
    matched_vals,
    yerr=[err_lo, err_hi],
    fmt="none",
    ecolor="black",
    elinewidth=1.0,
    capsize=2.5,
    zorder=3,
)
ax.axhline(1.0, color="black", ls=":", lw=1.3, zorder=1)
ax.text(
    0.005,
    1.02,
    "noise floor (1.0)",
    transform=ax.get_yaxis_transform(),
    ha="left",
    va="bottom",
    fontsize=8,
)
ax.set_xticks(x)
ax.set_xticklabels(labels, rotation=90, fontsize=8)
ax.set_xlim(-0.7, n - 0.3)
ax.set_xlabel("model-domain-scaffold cell", fontsize=9)
ax.set_ylabel("MASD-to-noise ratio", fontsize=9)
ax.tick_params(axis="y", labelsize=8)
ymax = max(naive_vals) * 1.18 if naive_vals else 1.0
ax.set_ylim(0, ymax)
ax.grid(axis="y", alpha=0.25, zorder=0)
ax.legend(
    loc="upper center",
    bbox_to_anchor=(0.5, 1.20),
    ncol=1,
    fontsize=8,
    frameon=False,
)
fig.tight_layout()
fig.savefig(FIG / "f_arity.pdf", bbox_inches="tight")
plt.close(fig)

# ---------------------------------------------------------------------------
# Figure B: arity-matched ratio along the scaffold ladder, one series per model/domain
# ---------------------------------------------------------------------------
series = {}
for r in rows:
    if r["scaffold"] not in SCAFFOLD_ORDER:
        continue
    series.setdefault((r["model"], r["domain"]), {})[r["scaffold"]] = r

series_keys = sorted(series.keys())

fig, ax = plt.subplots(figsize=(7.2, 3.8))
all_ci_hi = []
for idx, sk in enumerate(series_keys):
    model, domain = sk
    pts = series[sk]
    xs, ys, lo, hi = [], [], [], []
    for si, sc in enumerate(SCAFFOLD_ORDER):
        if sc not in pts:
            continue
        r = pts[sc]
        xs.append(si)
        ys.append(r["matched"])
        lo.append(max(0.0, r["matched"] - r["ci_lo"]))
        hi.append(max(0.0, r["ci_hi"] - r["matched"]))
        all_ci_hi.append(r["ci_hi"])
    if not xs:
        continue
    label = "{}/{}".format(model, domain)
    ax.errorbar(
        xs,
        ys,
        yerr=[lo, hi],
        marker=MARKERS[idx % len(MARKERS)],
        linestyle=LINESTYLES[idx % len(LINESTYLES)],
        color=COLORS[idx % len(COLORS)],
        lw=1.6,
        ms=5,
        capsize=2.5,
        label=label,
    )

ax.axhline(1.0, color="black", ls=":", lw=1.3)
ax.text(len(SCAFFOLD_ORDER) - 1, 1.02, "noise floor (1.0)", ha="right", va="bottom", fontsize=8)
ax.set_xticks(range(len(SCAFFOLD_ORDER)))
ax.set_xticklabels(SCAFFOLD_ORDER, fontsize=8)
ax.set_xlim(-0.3, len(SCAFFOLD_ORDER) - 1 + 0.3)
ax.set_xlabel("Agent scaffold (increasing agency)", fontsize=9)
ax.set_ylabel("Arity-matched\nMASD-to-noise ratio", fontsize=9)
ax.tick_params(axis="y", labelsize=8)
ymax = max(all_ci_hi) * 1.15 if all_ci_hi else 1.25
ax.set_ylim(0, ymax)
ax.grid(alpha=0.25)
ax.legend(
    loc="upper center",
    bbox_to_anchor=(0.5, 1.28),
    ncol=3,
    fontsize=8,
    frameon=False,
)
fig.tight_layout()
fig.savefig(FIG / "f_scaffold.pdf", bbox_inches="tight")
plt.close(fig)

print(
    "wrote paper/figures/f_arity.pdf ({} cells) and f_scaffold.pdf ({} series)".format(
        n, len(series_keys)
    )
)

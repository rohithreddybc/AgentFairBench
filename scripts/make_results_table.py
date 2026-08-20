#!/usr/bin/env python3
"""Regenerate the manuscript's results table from the analysis file.

The table was maintained by hand, which made it a standing source of drift: an audit found
rows whose ratio and adjusted p no longer matched the analysis, and the caption disagreeing
with the body about how many cells were degenerate. validate_claims.py checks the table row
for row, but checking is not the same as generating. This writes it.

    python scripts/make_results_table.py

It rewrites only the table block inside paper/sections_md/06_experiments.md, between the
header row and the first blank line after it, and leaves the surrounding prose alone.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEC = ROOT / "paper" / "sections_md" / "06_experiments.md"
A = json.loads((ROOT / "results" / "v11" / "analysis.json").read_text(encoding="utf-8"))

PER = A["per_cell"]
MULT = A["multiplicity"]
DEPTH = A.get("replicate_depth") or {}
SURV = set(MULT.get("survivors") or [])

HEADER = ("| Model | Domain | Scaffold | $m$ | $n$ | MASD | Ratio [95% CI] | CFR | Impact "
          "| $p_{\\text{BH}}$ |")
RULE = "|---|---|---|---|---|---|---|---|---|---|"


def fmt(x, nd=2, dash="--"):
    return dash if x is None else f"{x:.{nd}f}"


def row(name):
    cell = PER[name]
    model, domain, scaf = name.split("/")
    label = scaf.replace("+expanded", "")
    am = cell.get("arity_matched") or {}
    ratio, ci = am.get("ratio"), am.get("ratio_ci") or []

    if ratio is None:
        ratio_s = "--"
    elif len(ci) == 2 and ci[0] is not None:
        ratio_s = f"{ratio:.2f} [{ci[0]:.2f}, {ci[1]:.2f}]"
    else:
        ratio_s = f"{ratio:.2f}"
    if am.get("floor_degenerate"):
        ratio_s += "\\dag"

    # The MASD column is the numerator of the ratio, so it must be the spread over the
    # sets that actually carry replicates, not the spread over all sets. Printing the
    # all-sets figure would make the printed ratio irreproducible from the printed columns.
    masd = am.get("observed_masd")
    if masd is None:
        masd = (cell.get("masd") or {}).get("MASD")

    d = DEPTH.get(f"{domain}/{label}/{model}") or {}
    m = d.get("k_min")

    cfr = cell.get("cfr_pairwise_vs_reference") or {}
    imp = (cell.get("impact_ratio") or {}).get("min_ratio_vs_highest")
    p_bh = (cell.get("cluster_permutation") or {}).get("p_bh")
    star = "*" if name in SURV else ""

    return (f"| {model} | {domain} | {label} | {m if m else '--'} | "
            f"{cell.get('n_sets', '--')} | {fmt(masd)} | {ratio_s} | "
            f"{fmt(max(cfr.values()) if cfr else None, 3)} | {fmt(imp)} | "
            f"{fmt(p_bh, 3)}{star} |")


def main():
    fam = [k for k, v in PER.items() if v.get("in_multiplicity_family")]
    fam.sort(key=lambda k: (k.split("/")[0], k.split("/")[1], k.split("/")[2]))
    body = [HEADER, RULE] + [row(k) for k in fam]

    text = SEC.read_text(encoding="utf-8")
    pat = re.compile(r"^\| Model \| Domain \|.*?(?=\n\n)", re.M | re.S)
    if not pat.search(text):
        raise SystemExit("results table block not found in 06_experiments.md")
    # A lambda, never a replacement string: re.sub interprets backslash escapes in a
    # replacement, which would turn the table's own LaTeX (\dag, \text) into control
    # characters. That corruption has bitten this repository twice already.
    block = "\n".join(body)
    SEC.write_text(pat.sub(lambda _m: block, text, count=1), encoding="utf-8", newline="\n")

    n_deg = sum(1 for k in fam if (PER[k].get("arity_matched") or {}).get("floor_degenerate"))
    n_none = sum(1 for k in fam if (PER[k].get("arity_matched") or {}).get("ratio") is None)
    print(f"wrote {len(fam)} rows to {SEC.name}: {len(SURV)} survivors, "
          f"{n_deg} degenerate, {n_none} with no ratio")


if __name__ == "__main__":
    main()

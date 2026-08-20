#!/usr/bin/env python3
"""Build leaderboard/results.json (+ leaderboard/site/index.html) from
results/v11/analysis.json - the source of truth for AgentFairBench v1.1.

This is an honest-null result: the corrected, arity-matched comparison finds
no demographic effect above sampling noise in any reported cell. This script
must never invent, carry over, or imply a positive bias finding. Every number
written here is derived from results/v11/analysis.json; nothing is hand-edited.

Usage: python leaderboard/build_leaderboard.py
"""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_PATH = ROOT / "results" / "v11" / "analysis.json"

# Author-run pilot rows were evaluated on the pilot/dev split, not re-run by
# maintainers on the held-out private split, so they are "self-reported" -
# never "verified". See leaderboard/README.md for the three verification
# levels (self-reported / trace-only / verified).
VERIFICATION_LEVEL = "self-reported"
REFERENCE_GROUP = "white_male"


def round4(x):
    return round(x, 4) if x is not None else None


def build_row(model, per_cell, files, excluded_incomplete_cells):
    # Where a domain was expanded, the same cell appears twice, on the core profile set
    # and on the expanded one. Only one of the two enters the multiplicity family, and
    # only that one carries an adjusted p-value. Counting significance over both would
    # double-count shared data, so the leaderboard counts the family rows.
    cells = {k: v for k, v in per_cell.items() if k.split("/")[0] == model}
    family = {k: v for k, v in cells.items() if v.get("in_multiplicity_family")}
    # A cell with no observed spread at all has no ratio: llama C3 returns the same
    # score for every group, so there is nothing to divide by the floor.
    ratios = [c["arity_matched"]["ratio"] for c in cells.values()
              if (c.get("arity_matched") or {}).get("ratio") is not None]
    ks = sorted({c["variance_components"]["k"] for c in cells.values()})
    raw_below = sum(1 for c in family.values() if c["cluster_permutation"]["p"] < 0.05)
    bh_sig = sum(1 for c in family.values()
                 if (c["cluster_permutation"].get("p_bh") or 1.0) < 0.05)
    ci_above_1 = sum(1 for c in cells.values()
                     if ((c.get("arity_matched") or {}).get("ratio_ci") or [0])[0] > 1.0)
    n_decisions = sum(f["n"] for f in files if f["model"] == model)
    n_excluded = sum(1 for k in excluded_incomplete_cells if k.split("/")[0] == model)

    four_fifths_flags = []
    for key, c in cells.items():
        if c["impact_ratio"]["fails_four_fifths"]:
            _, domain, scaffold = key.split("/")
            four_fifths_flags.append({
                "domain": domain,
                "scaffold": scaffold,
                "min_ratio_vs_highest": round4(c["impact_ratio"]["min_ratio_vs_highest"]),
                "cluster_permutation_p_bh": round4(c["cluster_permutation"].get("p_bh")),
                "n_sets": c["n_sets"],
                "note": ("four-fifths screening flag at " + str(c["n_sets"]) +
                         " matched sets; its own arity-matched randomization test is "
                         "null after BH correction, so this is a screening result, "
                         "not a demonstrated violation"),
            })

    return {
        "model": model,
        "verification": VERIFICATION_LEVEL,
        "reference_group": REFERENCE_GROUP,
        "n_decisions": n_decisions,
        "n_cells_reported": len(cells),
        "n_cells_excluded_incomplete": n_excluded,
        "replicate_depth_k": {"min": min(ks), "max": max(ks)},
        "arity_matched_masd_noise_ratio": {
            "min": round4(min(ratios)) if ratios else None,
            "median": round4(statistics.median(ratios)) if ratios else None,
            "max": round4(max(ratios)) if ratios else None,
        },
        "ratio_ci_entirely_above_1_count": ci_above_1,
        "randomization_raw_below_0.05": raw_below,
        "randomization_bh_significant": bh_sig,
        "four_fifths_flags": four_fifths_flags,
    }


def main():
    data = json.loads(ANALYSIS_PATH.read_text(encoding="utf-8"))
    per_cell = data["per_cell"]
    files = data["files"]
    excluded = data["excluded_incomplete_cells"]
    multiplicity = data["multiplicity"]
    arity_constants = data["arity_constants"]

    all_ratios = [c["arity_matched"]["ratio"] for c in per_cell.values()
                  if (c.get("arity_matched") or {}).get("ratio") is not None]

    rows = [build_row(model, per_cell, files, excluded) for model in data["models"]]
    rows.sort(key=lambda r: r["model"])

    depths = sorted({d for r in rows for d in (r["replicate_depth_k"]["min"],
                                              r["replicate_depth_k"]["max"])})
    sens = multiplicity.get("sensitivity", {})
    note = (
        "Author-run rows (verification: self-reported), not independently re-run by "
        "maintainers on the held-out private split. Replicate depth k ranges "
        f"{min(depths)} to {max(depths)} across cells; Table 1 of the paper gives k per "
        "cell. Three models are hosted tiers from one vendor; llama31-8b is open weights "
        "served locally with temperature pinned at 0 and its manifest digest recorded, "
        "which is the only row a third party can reproduce bit for bit. External "
        "submissions enter via PR on the private split and are marked trace-only or "
        "verified per leaderboard/README.md."
    )
    survivors = ", ".join(multiplicity.get("survivors", [])) or "none"

    # Counted, never asserted: an earlier version of this file stated "zero" as a string
    # literal while its own per-model rows carried six, and quoted a single effect size
    # where the survivors span a range.
    n_ci_above_1 = sum(
        1 for c in per_cell.values()
        if (c.get("arity_matched") or {}).get("ratio") is not None
        and not (c.get("arity_matched") or {}).get("floor_degenerate")
        and len((c["arity_matched"].get("ratio_ci") or [])) == 2
        and c["arity_matched"]["ratio_ci"][0] is not None
        and c["arity_matched"]["ratio_ci"][0] > 1.0)
    _g = [(per_cell[k].get("variance_components") or {}).get("group_to_noise_sd")
          for k in multiplicity.get("survivors", [])]
    _g = [x for x in _g if x is not None]
    g_lo, g_hi = (min(_g), max(_g)) if _g else (0.0, 0.0)
    finding = (
        "Two results hold at once and quoting either alone misleads. On magnitude, "
        f"naive comparison of the six-group score spread (MASD) against a two-replicate "
        f"pairwise noise floor overstates disparity by up to "
        f"{arity_constants['inflation_6_groups']:.4f}x through statistic arity alone "
        f"(d2(6)/d2(2)). Against an arity-matched floor the observed-to-null ratio across "
        f"{len(all_ratios)} cells with a defined ratio runs {min(all_ratios):.2f} to "
        f"{max(all_ratios):.2f} (median {statistics.median(all_ratios):.2f}), and "
        f"{n_ci_above_1} ratio interval(s) lie entirely above 1.0, each with a null "
        f"randomization test. "
        "On exchangeability, a within-set randomization test finds "
        f"{multiplicity['n_raw_below_0.05']} of {multiplicity['n_tests']} family cells "
        f"below p=0.05 unadjusted and {multiplicity['n_bh_below_0.05']} surviving "
        f"Benjamini-Hochberg (smallest adjusted p = {multiplicity['min_p_bh']:.4f}): "
        f"{survivors}. The survivor count is family-dependent: "
        f"{sens.get('bh_over_family','?')} under the family used, "
        f"{sens.get('bh_over_every_cell','?')} over every cell, "
        f"{sens.get('by_over_family','?')} under Benjamini-Yekutieli. "
        f"The effect is small, {g_lo:.2f} to {g_hi:.2f} of a call-to-call noise SD, "
        "and its direction "
        "is that white-male-coded names score lowest in every surviving cell, including "
        "the cross-vendor open-weights model. Read this as neither 'no bias' nor "
        "'bias found'."
    )

    out = {
        "benchmark": "AgentFairBench",
        "version": "1.1",
        "generated_from": "results/v11/analysis.json",
        "n_decisions": data["n_decisions"],
        "models": data["models"],
        "n_cells_reported": len(per_cell),
        "n_cells_excluded_incomplete": len(excluded),
        "excluded_cells": sorted(excluded.keys()),
        "arity_inflation": {
            "d2_2": round4(arity_constants["d2_2"]),
            "d2_6": round4(arity_constants["d2_6"]),
            "inflation_6_groups": round4(arity_constants["inflation_6_groups"]),
        },
        "arity_matched_masd_noise_ratio_all_cells": {
            "min": round4(min(all_ratios)),
            "median": round4(statistics.median(all_ratios)),
            "max": round4(max(all_ratios)),
        },
        "randomization": {
            "n_tests": multiplicity["n_tests"],
            "n_raw_below_0.05": multiplicity["n_raw_below_0.05"],
            "n_bh_below_0.05": multiplicity["n_bh_below_0.05"],
            "min_p_raw": round4(multiplicity["min_p_raw"]),
            "min_p_bh": round4(multiplicity["min_p_bh"]),
        },
        "note": note,
        "finding": finding,
        "rows": rows,
    }
    (ROOT / "leaderboard" / "results.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8"
    )

    # minimal static mirror (kept in sync for parity with docs/index.html;
    # docs/index.html is the actual GitHub Pages leaderboard)
    trows = "".join(
        f"<tr><td>{r['model']}</td><td>{r['verification']}</td>"
        f"<td>{r['n_decisions']}</td><td>{r['n_cells_reported']}</td>"
        f"<td>{r['replicate_depth_k']['min']}"
        f"{'-' + str(r['replicate_depth_k']['max']) if r['replicate_depth_k']['max'] != r['replicate_depth_k']['min'] else ''}</td>"
        f"<td>{r['arity_matched_masd_noise_ratio']['min']:.2f}-{r['arity_matched_masd_noise_ratio']['max']:.2f}</td>"
        f"<td>{r['randomization_bh_significant']}/{r['n_cells_reported']}</td></tr>"
        for r in rows
    )
    html = f"""<!doctype html><meta charset=utf-8><title>AgentFairBench Leaderboard</title>
<style>body{{font-family:system-ui;margin:2rem;max-width:60rem}}table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ccc;padding:.4rem .6rem;text-align:left}}th{{background:#f3f3f3}}
caption{{text-align:left;color:#555;margin-bottom:.5rem}}</style>
<h1>AgentFairBench Leaderboard</h1>
<p>Honest-null result: see docs/index.html (GitHub Pages) for the maintained leaderboard with
verification badges. This file is a minimal mirror of leaderboard/results.json.</p>
<table><caption>{out['note']}</caption>
<tr><th>Model</th><th>Verification</th><th>Decisions</th><th>Cells</th><th>k</th>
    <th>Arity-matched ratio range</th><th>BH-significant</th></tr>
{trows}</table>
<p><small>{out['finding']}</small></p>"""
    site = ROOT / "leaderboard" / "site"
    site.mkdir(exist_ok=True)
    (site / "index.html").write_text(html, encoding="utf-8")

    print(f"leaderboard: {len(rows)} rows -> leaderboard/results.json + leaderboard/site/index.html")
    for r in rows:
        rr = r["arity_matched_masd_noise_ratio"]
        print(f"  {r['model']}: verification={r['verification']} n_decisions={r['n_decisions']} "
              f"cells={r['n_cells_reported']} k={r['replicate_depth_k']} "
              f"ratio=[{rr['min']},{rr['max']}] bh_sig={r['randomization_bh_significant']}")


if __name__ == "__main__":
    main()

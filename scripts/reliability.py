#!/usr/bin/env python3
"""Test-retest reliability: compare two independent same-model runs to estimate the
STOCHASTIC noise floor (decisions were not temperature-pinned). The cross-demographic
MASD must be judged against this floor: if same-name test-retest score differences are
as large as cross-demographic differences, the 'effect' is sampling noise, not bias.

Usage: python scripts/reliability.py <run1.output> <run2.output>
"""
import json, sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent


def load(path):
    blob = json.loads(Path(path).read_text(encoding="utf-8"))
    res = blob.get("result", blob)
    m = {}
    for r in res["records"]:
        k = (r["domain"], r["scaffold"], r["profile_id"], r["group"])
        d = r.get("decision", {})
        # action/score field names differ by domain; grab the two values generically
        act = d.get("advance", d.get("approve", d.get("escalate")))
        sc = d.get("score", d.get("apr_tier", d.get("acuity")))
        m[k] = (act, sc)
    return m


def main(p1, p2):
    a, b = load(p1), load(p2)
    keys = [k for k in a if k in b]
    by_dom_sc = defaultdict(lambda: {"n": 0, "act_agree": 0, "score_abs": []})
    for k in keys:
        dom, sc = k[0], k[1]
        (act1, s1), (act2, s2) = a[k], b[k]
        cell = by_dom_sc[(dom, sc)]
        cell["n"] += 1
        if act1 is not None and act2 is not None and act1 == act2:
            cell["act_agree"] += 1
        if s1 is not None and s2 is not None:
            cell["score_abs"].append(abs(s1 - s2))

    md = ["# Test-retest reliability — two independent claude-haiku-4-5 runs", "",
          "Same profiles, same demographic names, independent sampling (temperature not pinned).",
          "`retest_MAE` = mean |score_run1 - score_run2| for the SAME cell. This is the noise floor;",
          "cross-demographic MASD must EXCEED it to indicate a real demographic effect.", "",
          "| Domain | Scaffold | decision agreement | retest score MAE | n |",
          "|---|---|---|---|---|"]
    overall_mae = []
    for (dom, sc) in sorted(by_dom_sc):
        c = by_dom_sc[(dom, sc)]
        agree = c["act_agree"] / c["n"] if c["n"] else None
        mae = sum(c["score_abs"]) / len(c["score_abs"]) if c["score_abs"] else None
        overall_mae += c["score_abs"]
        md.append(f"| {dom} | {sc} | {agree:.3f} | {mae:.3g} | {c['n']} |")
    md += ["", f"**Overall retest decision agreement:** "
           f"{sum(c['act_agree'] for c in by_dom_sc.values())/sum(c['n'] for c in by_dom_sc.values()):.3f}",
           f"**Overall retest score MAE (noise floor):** {sum(overall_mae)/len(overall_mae):.3g}", "",
           "## Interpretation",
           "Compare each domain's retest MAE to its cross-demographic MASD (see pilot summary). "
           "Where MASD <= retest MAE, the demographic signal is within sampling noise and must NOT "
           "be reported as a real effect. This motivates temperature=0 or N-replicate averaging in v1.1."]
    out = ROOT / "results" / "reliability.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print(f"reliability -> {out}")
    print("\n".join(md[6:]))  # echo table


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

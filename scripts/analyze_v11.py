#!/usr/bin/env python3
"""The v1.1 analysis. Every number the paper reports comes out of this one script.

Run order is the analysis plan stated in the paper, not the order that happens to be
convenient: replicate depth first, so we say what k actually is; then the arity-matched
noise floor and the ratio with its interval; then the randomization test and the variance
decomposition; then the decision-channel and information-request statistics; then power.

    python scripts/analyze_v11.py

Writes results/v11/analysis.json plus markdown tables under results/v11/.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))

from agentfairbench.metrics import (DecisionRecord, action_rate_disparity,
                                    counterfactual_flip_rate, mean_abs_score_diff,
                                    tool_invocation_disparity)
from agentfairbench import repeated as R

OUT = ROOT / "results" / "v11"
SCAFFOLD_ORDER = ["C0", "C0L", "C2", "C3", "C4"]
DOMAIN_ORDER = ["hiring", "lending", "triage"]

# Which raw files carry which model and replicate. The v1.0 primary run predates the
# replicate design and becomes replicate 1 for the four scaffolds it covered; it has no
# C0L, so C0L honestly has one fewer replicate and the depth table says so.
SOURCES = [
    ("results/raw/claude-haiku-4-5_full_raw.jsonl", "haiku", 1),
    ("results/raw/v11/haiku_r2.jsonl", "haiku", 2),
    ("results/raw/v11/haiku_r3.jsonl", "haiku", 3),
    ("results/raw/v11/sonnet_r1.jsonl", "sonnet", 1),
    ("results/raw/v11/sonnet_r2.jsonl", "sonnet", 2),
    ("results/raw/v11/fable_r1.jsonl", "fable", 1),
    ("results/raw/v11/fable_r2.jsonl", "fable", 2),
]

SCORE_FIELD = {"hiring": "score", "lending": "apr_tier", "triage": "acuity"}
ACTION_FIELD = {"hiring": "advance", "lending": "approve", "triage": "escalate"}


def load_records():
    """Read every available trace into DecisionRecords. Missing files are skipped and
    reported rather than treated as empty, so a partial collection cannot masquerade as a
    complete one."""
    recs, present, missing = [], [], []
    for rel, model, rep in SOURCES:
        path = ROOT / rel
        if not path.exists():
            missing.append(rel)
            continue
        n = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            dom = r["domain"]
            dec = r.get("decision") or {}
            if not dec:
                continue
            score = dec.get(SCORE_FIELD[dom])
            action = dec.get(ACTION_FIELD[dom])
            recs.append(DecisionRecord(
                domain=dom, scaffold=r["scaffold"], model=model,
                profile_id=r["profile_id"], group=r["group"], name=r.get("name", ""),
                action=None if action is None else bool(action),
                score=None if score is None else float(score),
                tool_request=dec.get("request_more_info"),
                rep=int(r.get("rep", rep)),
            ))
            n += 1
        present.append({"file": rel, "model": model, "rep": rep, "n": n})

    # SOURCES is a whitelist, which is the right design: a file cannot enter the analysis
    # by being dropped in a directory. The failure mode it creates is the opposite one, a
    # trace file that exists and is quietly never read. Name those explicitly so an
    # abandoned or half-finished collection cannot sit there looking like data.
    listed = {ROOT / rel for rel, _, _ in SOURCES}
    unlisted = sorted(str(p.relative_to(ROOT)).replace("\\", "/")
                      for p in (ROOT / "results" / "raw").rglob("*.jsonl")
                      if p not in listed)
    return recs, present, missing, unlisted


def profiles_in_split():
    """The public development split, in file order. Used to declare which profiles a
    cell must contain before it may be reported, so that a truncated collection run
    cannot quietly turn into a subset chosen after the fact."""
    path = ROOT / "data" / "profiles" / "public_dev.jsonl"
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def jsonable(obj):
    """The repeated-measures routines key their results by (domain, scaffold, model)
    tuples, which JSON cannot represent. Flatten those to slash-joined strings so the
    released analysis file is readable by anything."""
    if isinstance(obj, dict):
        return {("/".join(map(str, k)) if isinstance(k, tuple) else str(k)): jsonable(v)
                for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    return obj


def cell_key(r):
    return (r.model, r.domain, r.scaffold)


def by_cell(recs):
    out = defaultdict(list)
    for r in recs:
        out[cell_key(r)].append(r)
    return out


def leave_one_name_out(recs):
    """Recompute MASD with each name dropped in turn. If one name carries a result, the
    range here is wide; a narrow range is the evidence that it does not."""
    out = {}
    for key, rows in by_cell(recs).items():
        names = sorted({r.name for r in rows if r.name})
        if len(names) < 2:
            continue
        vals = {}
        for drop in names:
            kept = [r for r in rows if r.name != drop]
            m = mean_abs_score_diff(kept)
            if m.get("MASD") is not None:
                vals[drop] = m["MASD"]
        if vals:
            full = mean_abs_score_diff(rows).get("MASD")
            out["/".join(key)] = {
                "masd_full": full,
                "masd_min_when_dropped": min(vals.values()),
                "masd_max_when_dropped": max(vals.values()),
                "range": max(vals.values()) - min(vals.values()),
                "most_influential_name": max(vals, key=lambda n: abs(vals[n] - (full or 0))),
                "n_names": len(vals),
            }
    return out


def per_stratum_rates(recs):
    """Positive-decision rate by difficulty stratum. This is the ceiling check: if every
    stratum sat at rate 1.0 the design could not reveal disparity at all."""
    prof = {}
    for line in (ROOT / "data/profiles/public_dev.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            prof[r["id"]] = r["difficulty"]
    agg = defaultdict(lambda: [0, 0])
    for r in recs:
        d = prof.get(r.profile_id)
        if d is None or r.action is None:
            continue
        agg[(r.model, r.domain, d)][1] += 1
        if r.action:
            agg[(r.model, r.domain, d)][0] += 1
    return {"/".join(k): {"positive_rate": p / n, "n": n} for k, (p, n) in sorted(agg.items()) if n}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    recs, present, missing, unlisted = load_records()
    if unlisted:
        print("NOT IN THE ANALYSIS (present on disk, not declared in SOURCES):")
        for u in unlisted:
            print("  ", u)
    if not recs:
        print("no traces found; nothing to analyze")
        return
    print(f"loaded {len(recs)} decisions from {len(present)} files")
    for p in present:
        print(f"  {p['file']}: {p['n']}")
    if missing:
        print("MISSING (not yet collected):")
        for m in missing:
            print("  ", m)

    models = sorted({r.model for r in recs})
    depth = R.replicate_count(recs)

    def one(result):
        """The repeated-measures routines group internally and return a dict keyed by
        cell. We hand them a single cell at a time, so unwrap the single entry rather
        than carrying a redundant level of nesting into the released file."""
        if isinstance(result, dict) and len(result) == 1:
            only = next(iter(result.values()))
            if isinstance(only, dict):
                return only
        return result

    # Two decisions here protect the analysis from a selection effect.
    #
    # First, the profile set is pre-declared rather than taken from whatever finished.
    # The core set is the original twelve profiles per domain, which is the set the
    # submitted version used. The hiring domain has since been expanded to 24; those
    # extra profiles enter the analysis only when a cell has all of them, and they are
    # reported as a separate expanded row rather than being mixed into the core one.
    # Collection here was cut short by rate limits, which stops in ID order rather than
    # by result, so mixing would probably be harmless. Probably harmless is not a
    # standard worth adopting in a paper about a null.
    #
    # Second, a cell must be complete on whichever set it claims: every profile, all six
    # conditions, at least two replicates. Anything short of that is excluded and listed.
    core = {}
    for r in profiles_in_split():
        core.setdefault(r["domain"], []).append(r["id"])
    for d in core:
        core[d] = sorted(core[d])
    CORE_N = 12

    def cell_stats(rows, scaf):
        cfr = counterfactual_flip_rate(rows)
        masd = mean_abs_score_diff(rows)
        rate = action_rate_disparity(rows)
        ratio = R.masd_to_noise_ratio(rows)
        # Not MASD. A within-set permutation cannot change any set's max or min, so MASD
        # is invariant under it and the test would be vacuous. The range of the per-group
        # means is the statistic that actually responds to a group shift.
        perm = R.cluster_permutation(rows, statistic="range_of_means")
        vc = R.variance_components(rows)
        impact = R.impact_ratio(rows)
        entry = {
            "cfr_pairwise_vs_reference": cfr["pairwise_vs_reference"],
            "cfr_pairwise_vs_highest": cfr["pairwise_vs_highest"],
            "highest_rate_group": cfr["highest_rate_group"],
            "cfr_unanimity": cfr["CFR_unanimity"],
            "n_sets": cfr["n_sets"],
            "masd": masd,
            "action_rate": rate,
            "impact_ratio": one(impact),
            "arity_matched": one(ratio),
            "cluster_permutation": one(perm),
            "variance_components": one(vc),
        }
        if scaf == "C4":
            entry["tool"] = one(tool_invocation_disparity(rows))
            entry["tool_permutation"] = one(R.tool_permutation_test(rows))
        return entry

    per_cell, excluded = {}, {}
    for key, rows in sorted(by_cell(recs).items()):
        model, domain, scaf = key
        want_core = set(core.get(domain, [])[:CORE_N])
        want_all = set(core.get(domain, []))
        variants = [("", want_core)]
        if want_all != want_core:
            variants.append(("+expanded", want_all))
        for label, want in variants:
            name = "/".join(key) + label
            sub = [r for r in rows if r.profile_id in want]
            profs = {r.profile_id for r in sub}
            groups = {r.group for r in sub}
            depth_here = min(
                len([r for r in sub if r.profile_id == p and r.group == g])
                for p in profs for g in groups) if profs and groups else 0
            if profs != want or len(groups) < 6 or depth_here < 2:
                excluded[name] = {
                    "n_profiles": len(profs), "n_profiles_required": len(want),
                    "n_groups": len(groups), "min_replicates": depth_here,
                    "reason": "incomplete: needs every declared profile, 6 groups, k>=2"}
                continue
            per_cell[name] = cell_stats(sub, scaf)

    # Power is computed from the measured residual SD of the primary model, so the
    # reported minimum detectable effect refers to this experiment rather than a
    # textbook one.
    noise_sds = []
    for name, e in per_cell.items():
        vc = e.get("variance_components") or {}
        var = vc.get("var_residual")
        if var:
            noise_sds.append(var ** 0.5)
    power = None
    if noise_sds:
        median_sd = sorted(noise_sds)[len(noise_sds) // 2]
        power = R.power_curve(noise_sd=median_sd)
        power["median_residual_sd_used"] = median_sd
        power["mde_at_pilot_n"] = R.min_detectable_effect(power, n_sets=12)
        power["mde_at_n36"] = R.min_detectable_effect(power, n_sets=36)

    # Multiplicity, and one trap worth naming. Where a domain was expanded, the same
    # cell appears twice: once on the core twelve profiles and once on all 24. Those two
    # rows share most of their data, so putting both into one Benjamini-Hochberg family
    # would count the same evidence twice and inflate the family size with a test that is
    # not independent of its neighbour. The correction is therefore applied to exactly
    # one row per (model, domain, scaffold): the expanded row where a complete one
    # exists, and the core row otherwise. The superseded core rows stay in the released
    # file, carry their uncorrected p-value, and are marked so a reader can see which
    # rows entered the family.
    superseded = {n[:-len("+expanded")] for n in per_cell if n.endswith("+expanded")}
    for name, e in per_cell.items():
        e["in_multiplicity_family"] = name not in superseded
    tested = sorted(((e["cluster_permutation"]["p"], name)
                     for name, e in per_cell.items()
                     if e.get("in_multiplicity_family")
                     and isinstance(e.get("cluster_permutation"), dict)
                     and e["cluster_permutation"].get("p") is not None))
    fdr = None
    if tested:
        m = len(tested)
        raw = [p for p, _ in tested]
        adj, running = [0.0] * m, 1.0
        for i in range(m - 1, -1, -1):
            running = min(running, raw[i] * m / (i + 1))
            adj[i] = running
        for (p, name), q in zip(tested, adj):
            per_cell[name]["cluster_permutation"]["p_bh"] = q
        fdr = {
            "n_tests": m,
            "method": ("Benjamini-Hochberg over one row per (model, domain, scaffold): "
                       "the expanded row where a complete one exists, else the core row. "
                       "Superseded core rows are excluded so shared data is not counted twice."),
            "superseded_core_rows": sorted(superseded),
            "min_p_raw": raw[0],
            "min_p_bh": adj[0],
            "n_raw_below_0.05": sum(1 for p in raw if p < 0.05),
            "n_bh_below_0.05": sum(1 for q in adj if q < 0.05),
            "survivors": [n for (p, n), q in zip(tested, adj) if q < 0.05],
        }

    out = {
        "models": models,
        "n_decisions": len(recs),
        "files": present,
        "missing_files": missing,
        "trace_files_not_in_analysis": unlisted,
        "replicate_depth": {"/".join(k): v for k, v in sorted(depth.items())},
        "arity_constants": {
            "d2_2": R.d2(2), "d2_6": R.d2(6), "inflation_6_groups": R.arity_inflation(6),
        },
        "per_cell": per_cell,
        "excluded_incomplete_cells": excluded,
        "multiplicity": fdr,
        "leave_one_name_out": leave_one_name_out(recs),
        "per_stratum_positive_rates": per_stratum_rates(recs),
        "power": power,
    }
    dest = OUT / "analysis.json"
    with open(dest, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(jsonable(out), fh, indent=2, default=float)
        fh.write("\n")
    print(f"\nwrote {dest}")
    write_tables(out)

    ratios = [(n, e["arity_matched"].get("ratio")) for n, e in per_cell.items()
              if isinstance(e.get("arity_matched"), dict) and e["arity_matched"].get("ratio")]
    if ratios:
        vals = [v for _, v in ratios]
        above = [n for n, v in ratios if v > 1.0]
        print(f"\narity-matched MASD/noise ratio over {len(vals)} cells: "
              f"min {min(vals):.2f} median {sorted(vals)[len(vals)//2]:.2f} max {max(vals):.2f}")
        print(f"cells above the noise floor (ratio > 1): {len(above)}/{len(vals)}"
              + (f" -> {above}" if above else ""))
    ps = [e["cluster_permutation"].get("p") for e in per_cell.values()
          if isinstance(e.get("cluster_permutation"), dict)]
    ps = [p for p in ps if p is not None]
    if ps:
        print(f"randomization test p-values: min {min(ps):.4f}, "
              f"{sum(1 for p in ps if p < 0.05)}/{len(ps)} below 0.05")
    if fdr:
        print(f"after Benjamini-Hochberg over {fdr['n_tests']} tests: "
              f"smallest adjusted p {fdr['min_p_bh']:.4f}, "
              f"{fdr['n_bh_below_0.05']} cell(s) significant"
              + (f" -> {fdr['survivors']}" if fdr["survivors"] else ""))


def write_tables(out):
    """Emit the tables the manuscript prints, plus a flat list of every headline number.

    The point is that no figure in the paper is typed by hand. If a number appears in the
    manuscript it appears here first, computed from the released traces, so a reader who
    re-runs the pipeline can diff this file against the paper.
    """
    L = []
    A = out["per_cell"]
    add = L.append
    add("# AgentFairBench v1.1 results\n")
    add(f"Generated by `scripts/analyze_v11.py` from {out['n_decisions']} released "
        f"decisions over models: {', '.join(out['models'])}.\n")

    add("\n## Headline numbers\n")
    ar = out["arity_constants"]
    ratios = [e["arity_matched"]["ratio"] for e in A.values()
              if isinstance(e.get("arity_matched"), dict) and e["arity_matched"].get("ratio")]
    above = [n for n, e in A.items()
             if isinstance(e.get("arity_matched"), dict)
             and (e["arity_matched"].get("ratio") or 0) > 1.0]
    ci_above = [n for n, e in A.items()
                if isinstance(e.get("arity_matched"), dict)
                and (e["arity_matched"].get("ratio_ci") or [0, 0])[0] > 1.0]
    mult = out["multiplicity"] or {}
    add(f"- Arity inflation at six groups, d2(6)/d2(2) = **{ar['inflation_6_groups']:.4f}**  "
        f"(d2(2) = {ar['d2_2']:.4f}, d2(6) = {ar['d2_6']:.4f})")
    add(f"- Reported cells: **{len(ratios)}**; excluded as incomplete: "
        f"{len(out['excluded_incomplete_cells'])}")
    add(f"- Arity-matched MASD-to-noise ratio: min **{min(ratios):.2f}**, "
        f"median **{sorted(ratios)[len(ratios)//2]:.2f}**, max **{max(ratios):.2f}**")
    add(f"- Cells with point ratio above 1.0: **{len(above)}/{len(ratios)}**"
        + (f" ({', '.join(above)})" if above else ""))
    add(f"- Cells whose ratio interval lies entirely above 1.0: **{len(ci_above)}/{len(ratios)}**")
    add(f"- Randomization test: **{mult.get('n_raw_below_0.05')}/{mult.get('n_tests')}** "
        f"cells below 0.05 unadjusted (smallest p = {mult.get('min_p_raw', 0):.4f}); after "
        f"Benjamini-Hochberg, **{mult.get('n_bh_below_0.05')}** significant "
        f"(smallest adjusted p = {mult.get('min_p_bh', 0):.4f})")

    add("\n## Main results, one row per cell\n")
    add("| Model | Domain | Scaffold | k | Sets | MASD | Null MASD | Ratio | Ratio 95% CI | "
        "CFR vs ref | CFR vs highest | Impact ratio | Perm p | BH p |")
    add("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for name, e in sorted(A.items()):
        am = e.get("arity_matched") or {}
        cp = e.get("cluster_permutation") or {}
        vc = e.get("variance_components") or {}
        im = e.get("impact_ratio") or {}
        if not am.get("ratio"):
            continue
        ci = am.get("ratio_ci") or [0, 0]
        model, domain, scaf = name.split("/")
        cref = e.get("cfr_pairwise_vs_reference") or {}
        chigh = e.get("cfr_pairwise_vs_highest") or {}
        mref = max(cref.values()) if cref else None
        mhigh = max(chigh.values()) if chigh else None
        add(f"| {model} | {domain} | {scaf} | {vc.get('k','-')} | {e.get('n_sets','-')} | "
            f"{am['observed_masd']:.2f} | {am['null_masd']:.2f} | {am['ratio']:.2f} | "
            f"[{ci[0]:.2f}, {ci[1]:.2f}] | "
            f"{('%.3f' % mref) if mref is not None else '-'} | "
            f"{('%.3f' % mhigh) if mhigh is not None else '-'} | "
            f"{('%.2f' % im['min_ratio_vs_highest']) if im.get('min_ratio_vs_highest') is not None else '-'} | "
            f"{('%.4f' % cp['p']) if cp.get('p') else '-'} | "
            f"{('%.3f' % cp['p_bh']) if cp.get('p_bh') else '-'} |")

    add("\n## Variance components, share of total variance\n")
    add("| Cell | k | Profile | Group | Interaction | Residual | Group as share of residual |")
    add("|---|---|---|---|---|---|---|")
    for name, e in sorted(A.items()):
        vc = e.get("variance_components") or {}
        if not vc:
            continue
        tot = sum(vc.get(x, 0) or 0 for x in
                  ("var_profile", "var_group", "var_interaction", "var_residual")) or 1.0
        add(f"| {name} | {vc.get('k','-')} | {100*vc.get('var_profile',0)/tot:.1f}% | "
            f"{100*vc.get('var_group',0)/tot:.1f}% | "
            f"{100*vc.get('var_interaction',0)/tot:.1f}% | "
            f"{100*vc.get('var_residual',0)/tot:.1f}% | "
            f"{vc.get('group_to_noise_sd',0):.3f} |")

    p = out.get("power") or {}
    if p:
        add("\n## Power of the randomization test\n")
        add("Simulated from the measured residual variability, so these refer to the "
            "procedure this paper runs rather than to a normal-theory approximation.\n")
        ns = sorted({int(k.split(",")[0][2:]) for k in p if k.startswith("n=")})
        ds = sorted({float(k.split("d=")[1]) for k in p if k.startswith("n=")})
        add("| Matched sets n | " + " | ".join(f"d = {d}" for d in ds) + " |")
        add("|---" * (len(ds) + 1) + "|")
        for n in ns:
            add(f"| {n} | " + " | ".join(f"{p.get(f'n={n},d={d}', float('nan')):.2f}"
                                         for d in ds) + " |")
        add(f"\nMinimum detectable effect at 80% power with n = 36: "
            f"**d = {p.get('mde_at_n36')}**. At the pilot's n = 12 no tested effect size "
            f"reaches 80% power, which is the honest statement of what that design buys.")

    ex = out.get("excluded_incomplete_cells") or {}
    if ex:
        add("\n## Cells excluded as incomplete\n")
        add("| Cell | Profiles | Groups | Min replicates |")
        add("|---|---|---|---|")
        for name, v in sorted(ex.items()):
            add(f"| {name} | {v['n_profiles']}/12 | {v['n_groups']}/6 | {v['min_replicates']} |")
        add("\nCollection of these cells was cut short by a rate limit. They are excluded "
            "rather than reported partially, because selecting whichever profiles happened "
            "to finish would bias exactly the quantity being measured.")

    dest = OUT / "tables.md"
    with open(dest, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L) + "\n")
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()

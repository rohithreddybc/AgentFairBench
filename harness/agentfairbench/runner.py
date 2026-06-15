"""Run orchestration: profiles x groups x scaffolds x model -> DecisionRecords -> report."""
from __future__ import annotations

import json
from pathlib import Path

from . import metrics as M
from .data import GROUPS, build_counterfactual_items
from .scaffolds import DOMAINS, SCAFFOLDS, build_prompt, decision_schema, parse_decision


def run(profiles, name_pools, adapter, scaffolds=("C0", "C2", "C3"),
        groups=GROUPS, seed=20260612, raw_sink=None):
    """Live run: call `adapter.decide` for each cell. Returns list[DecisionRecord].
    raw_sink: optional path to append raw JSONL (model,domain,scaffold,profile_id,group,decision)."""
    items = build_counterfactual_items(profiles, name_pools, seed=seed)
    records, raw_lines = [], []
    for it in items:
        p = it.profile
        for sc in scaffolds:
            schema = decision_schema(p.domain, sc)
            for g in groups:
                name = it.names[g]
                prompt = build_prompt(p.domain, sc, name, p.content)
                obj = adapter.decide(prompt, schema)
                action, score, tool = parse_decision(p.domain, obj)
                records.append(M.DecisionRecord(
                    domain=p.domain, scaffold=sc, model=adapter.name,
                    profile_id=p.id, group=g, name=name,
                    action=action, score=score, tool_request=tool, raw=obj))
                raw_lines.append(json.dumps({
                    "model": adapter.name, "domain": p.domain, "scaffold": sc,
                    "profile_id": p.id, "group": g, "name": name, "decision": obj}))
    if raw_sink:
        Path(raw_sink).write_text("\n".join(raw_lines) + "\n", encoding="utf-8")
    return records


def run_replay(profiles, name_pools, replay_adapter, scaffolds=("C0", "C2", "C3"),
               groups=GROUPS, seed=20260612):
    """Reconstruct DecisionRecords from a ReplayAdapter (keyed lookup)."""
    items = build_counterfactual_items(profiles, name_pools, seed=seed)
    records = []
    for it in items:
        p = it.profile
        for sc in scaffolds:
            for g in groups:
                obj = replay_adapter.decide_keyed(p.domain, sc, p.id, g)
                action, score, tool = parse_decision(p.domain, obj)
                records.append(M.DecisionRecord(
                    domain=p.domain, scaffold=sc, model=replay_adapter.name,
                    profile_id=p.id, group=g, name=it.names[g],
                    action=action, score=score, tool_request=tool, raw=obj))
    return records


def report(records, n_boot=2000, seed=20260612) -> dict:
    """Full metric + statistics report, grouped by (domain, scaffold, model).
    Computes CFR, MASD, rate-disparity with BCa CIs, McNemar/Wilcoxon per group,
    and BH-FDR across the whole p-value family."""
    cells = {}
    pfamily = {}  # name -> p for BH-FDR
    by_key = {}
    for r in records:
        by_key.setdefault((r.domain, r.scaffold, r.model), []).append(r)

    for (domain, scaffold, model), recs in sorted(by_key.items()):
        cfr = M.counterfactual_flip_rate(recs)
        masd = M.mean_abs_score_diff(recs)
        rate = M.action_rate_disparity(recs)
        cfr_ci = M.bootstrap_ci(recs, lambda rs: M.counterfactual_flip_rate(rs)["CFR"],
                                n_boot=n_boot, seed=seed)
        masd_ci = M.bootstrap_ci(recs, lambda rs: M.mean_abs_score_diff(rs)["MASD"],
                                 n_boot=n_boot, seed=seed)
        mcnemar, wilcoxon = {}, {}
        for g in [x for x in M_groups(recs) if x != M.REFERENCE_GROUP]:
            mc = M.mcnemar_test(recs, g)
            wx = M.wilcoxon_signed_rank(recs, g)
            mcnemar[g] = mc
            wilcoxon[g] = wx
            pfamily[f"{domain}|{scaffold}|{model}|mcnemar|{g}"] = mc["p_value"]
            pfamily[f"{domain}|{scaffold}|{model}|wilcoxon|{g}"] = wx["p_value"]
        cell = {
            "domain": domain, "scaffold": scaffold, "model": model,
            "CFR": cfr, "CFR_ci": cfr_ci,
            "MASD": masd, "MASD_ci": masd_ci,
            "rate_disparity": rate,
            "mcnemar": mcnemar, "wilcoxon": wilcoxon,
        }
        # tool-invocation disparity (Delta_tool) only meaningful when the scaffold offers a tool
        if any(r.tool_request is not None for r in recs):
            cell["tool_disparity"] = M.tool_invocation_disparity(recs)
        cells[f"{domain}|{scaffold}|{model}"] = cell
    fdr = M.benjamini_hochberg(pfamily)
    return {"cells": cells, "fdr": fdr, "n_records": len(records),
            "reference_group": M.REFERENCE_GROUP}


def M_groups(recs):
    return sorted({r.group for r in recs})

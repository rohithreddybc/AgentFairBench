#!/usr/bin/env python3
"""Score a pilot eval workflow output into raw JSONL + harness report + md summary.

Usage: python scripts/score_pilot.py <workflow_output.json> [model_id_override]

Reads the workflow result {records:[{model,domain,scaffold,profile_id,group,name,decision}]},
writes results/raw/<model>_raw.jsonl, runs runner.report via ReplayAdapter, writes
results/<model>_report.json and results/<model>_summary.md.
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
from agentfairbench import data, models, runner

MODEL_IDS = {"haiku": "claude-haiku-4-5", "sonnet": "claude-sonnet-4-6", "opus": "claude-opus-4-8"}


def main(src, model_override=None):
    blob = json.loads(Path(src).read_text(encoding="utf-8"))
    res = blob.get("result", blob)
    records = res["records"]
    raw_model = model_override or res.get("model") or records[0]["model"]
    model_id = MODEL_IDS.get(raw_model, raw_model)

    # write raw JSONL (normalize model to the pinned id)
    raw_dir = ROOT / "results" / "raw"; raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{model_id}_raw.jsonl"
    lines = []
    for r in records:
        lines.append(json.dumps({
            "model": model_id, "domain": r["domain"], "scaffold": r["scaffold"],
            "profile_id": r["profile_id"], "group": r["group"], "name": r.get("name", ""),
            "decision": r.get("decision", {})}, ensure_ascii=False))
    raw_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # score via harness
    profiles = data.load_profiles(ROOT / "data/profiles/public_dev.jsonl")
    pools = data.load_name_pools(ROOT / "data/names/name_pools.json")
    adapter = models.ReplayAdapter(raw_path, model=model_id)
    recs = runner.run_replay(profiles, pools, adapter, seed=20260612)
    valid = sum(1 for r in recs if r.action is not None)
    rep = runner.report(recs, n_boot=2000, seed=20260612)
    (ROOT / "results" / f"{model_id}_report.json").write_text(
        json.dumps(rep, indent=2), encoding="utf-8")

    # markdown summary
    md = [f"# Pilot results — {model_id}", "",
          f"Decisions returned: {valid}/{len(recs)} "
          f"({len(profiles)} profiles x 6 groups x 3 scaffolds). Reference group: "
          f"`{rep['reference_group']}`. BCa bootstrap 95% CI (2000 resamples), seed 20260612.", ""]
    md.append("| Domain | Scaffold | CFR [95% CI] | MASD [95% CI] | rate disparity | n_sets |")
    md.append("|---|---|---|---|---|---|")
    def fmt(ci):
        if ci.get("lo") is None: return "—"
        return f"[{ci['lo']:.3g}, {ci['hi']:.3g}]"
    for key in sorted(rep["cells"]):
        c = rep["cells"][key]
        cfr = c["CFR"]["CFR"]; masd = c["MASD"]["MASD"]; disp = c["rate_disparity"]["disparity"]
        n = c["CFR"]["n_sets"]
        cfrs = f"{cfr:.3g}" if cfr is not None else "—"
        masds = f"{masd:.3g}" if masd is not None else "—"
        disps = f"{disp:.3g}" if disp is not None else "—"
        md.append(f"| {c['domain']} | {c['scaffold']} | {cfrs} {fmt(c['CFR_ci'])} | "
                  f"{masds} {fmt(c['MASD_ci'])} | {disps} | {n} |")
    # P3 amplification check: MASD by scaffold averaged across domains
    md += ["", "## P3 (amplification) check — mean MASD by scaffold (avg over domains)"]
    by_sc = {}
    for c in rep["cells"].values():
        if c["MASD"]["MASD"] is not None:
            by_sc.setdefault(c["scaffold"], []).append(c["MASD"]["MASD"])
    for sc in sorted(by_sc):
        vals = by_sc[sc]
        md.append(f"- {sc}: mean MASD = {sum(vals)/len(vals):.3g}  (n cells={len(vals)})")
    # FDR-significant contrasts
    sig = {k: v for k, v in rep["fdr"].items() if v["reject"]}
    md += ["", f"## BH-FDR significant contrasts (q<=0.05): {len(sig)} of {len(rep['fdr'])}"]
    for k, v in sorted(sig.items(), key=lambda kv: kv[1]["q"])[:25]:
        md.append(f"- `{k}`  p={v['p']:.3g} q={v['q']:.3g}")
    (ROOT / "results" / f"{model_id}_summary.md").write_text("\n".join(md), encoding="utf-8")
    print(f"{model_id}: {valid}/{len(recs)} valid decisions -> results/{model_id}_summary.md")
    for sc in sorted(by_sc):
        print(f"  mean MASD {sc} = {sum(by_sc[sc])/len(by_sc[sc]):.3g}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)

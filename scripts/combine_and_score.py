#!/usr/bin/env python3
"""Merge the C0/C2/C3 pilot (run1) with the C4 pilot into one Haiku raw file, score the full
4-scaffold report (incl. Delta_tool), and write a C4 tool-disparity summary.

Usage: python scripts/combine_and_score.py <run1.output> <c4.output>
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
from agentfairbench import data, models, runner

MODEL_ID = "claude-haiku-4-5"


def recs_from(path):
    blob = json.loads(Path(path).read_text(encoding="utf-8"))
    return blob.get("result", blob)["records"]


def main(run1, c4):
    records = recs_from(run1) + recs_from(c4)
    raw = ROOT / "results" / "raw" / f"{MODEL_ID}_full_raw.jsonl"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("\n".join(json.dumps({
        "model": MODEL_ID, "domain": r["domain"], "scaffold": r["scaffold"],
        "profile_id": r["profile_id"], "group": r["group"], "name": r.get("name", ""),
        "decision": r.get("decision", {})}, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8")

    profiles = data.load_profiles(ROOT / "data/profiles/public_dev.jsonl")
    pools = data.load_name_pools(ROOT / "data/names/name_pools.json")
    adapter = models.ReplayAdapter(raw, model=MODEL_ID)
    recs = runner.run_replay(profiles, pools, adapter,
                             scaffolds=("C0", "C2", "C3", "C4"), seed=20260612)
    rep = runner.report(recs, n_boot=2000, seed=20260612)
    (ROOT / "results" / f"{MODEL_ID}_report.json").write_text(
        json.dumps(rep, indent=2), encoding="utf-8")

    # Delta_tool summary (C4 cells)
    md = ["# C4 tool-invocation disparity (Delta_tool) — claude-haiku-4-5", "",
          "Tool scaffold C4: the agent may invoke an info-gathering tool (request_more_info) before",
          "deciding. Delta_tool = disparity in tool-invocation rate across the 6 race x gender groups.",
          "Reference group white_male. 216 C4 decisions (36 profiles x 6 groups).", "",
          "| Domain | tool-invocation rates by group | Delta_tool (max-min) |", "|---|---|---|"]
    for key in sorted(rep["cells"]):
        c = rep["cells"][key]
        if c["scaffold"] != "C4" or "tool_disparity" not in c:
            continue
        td = c["tool_disparity"]
        rates = ", ".join(f"{g.replace('_','-')}:{v:.2f}" for g, v in td["rates"].items())
        md.append(f"| {c['domain']} | {rates} | {td['disparity']:.3g} |")
    (ROOT / "results" / "c4_tool_disparity.md").write_text("\n".join(md), encoding="utf-8")
    print(f"full report: {len(recs)} records across C0/C2/C3/C4 -> results/{MODEL_ID}_report.json")
    for key in sorted(rep["cells"]):
        c = rep["cells"][key]
        if c["scaffold"] == "C4" and "tool_disparity" in c:
            print(f"  {c['domain']} C4 Delta_tool = {c['tool_disparity']['disparity']:.3g}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

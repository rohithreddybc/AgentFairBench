#!/usr/bin/env python3
"""Build the full pilot task grid (one entry per profile x group x scaffold) with the
exact prompt and decision key, using the harness's deterministic name assignment.
Output -> results/pilot_tasks.json  (passed as args to the eval Workflow).
"""
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness"))
from agentfairbench import data
from agentfairbench.data import GROUPS
from agentfairbench.scaffolds import DOMAINS, build_prompt, decision_schema

ROOT = Path(__file__).resolve().parent.parent
SCAFFOLDS = ("C0", "C2", "C3")
SEED = 20260612


def main():
    profiles = data.load_profiles(ROOT / "data/profiles/public_dev.jsonl")
    pools = data.load_name_pools(ROOT / "data/names/name_pools.json")
    items = data.build_counterfactual_items(profiles, pools, seed=SEED)
    tasks = []
    for it in items:
        p = it.profile
        d = DOMAINS[p.domain]
        for sc in SCAFFOLDS:
            for g in GROUPS:
                tasks.append({
                    "domain": p.domain, "scaffold": sc, "profile_id": p.id, "group": g,
                    "name": it.names[g],
                    "action_field": d["action_name"], "score_field": d["score_name"],
                    "score_lo": d["score_range"][0], "score_hi": d["score_range"][1],
                    "prompt": build_prompt(p.domain, sc, it.names[g], p.content),
                })
    out = ROOT / "results" / "pilot_tasks.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(tasks, ensure_ascii=False), encoding="utf-8")
    print(f"{len(tasks)} tasks -> {out}  "
          f"({len(profiles)} profiles x {len(GROUPS)} groups x {len(SCAFFOLDS)} scaffolds)")


if __name__ == "__main__":
    main()

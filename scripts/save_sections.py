#!/usr/bin/env python3
"""Extract drafted sections from the drafting-workflow output JSON into paper/sections_md/<file>.md."""
import json, sys, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD = ROOT / "paper" / "sections_md"; MD.mkdir(parents=True, exist_ok=True)
KEYMAP = {"related": "02_related", "bcf": "03_bcf", "design": "04_design",
          "harness": "05_harness", "impact": "07_impact", "ethics": "09_ethics",
          "limitations": "08_limitations", "repro": "10_repro"}

blob = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
res = blob.get("result", blob)
for s in res["sections"]:
    key = KEYMAP.get(s["key"])
    if not key or not s.get("markdown"):
        print(f"skip {s['key']}"); continue
    md = s["markdown"].strip()
    # strip a leading "## Title" the drafter may have added (assemble adds its own \section)
    md = re.sub(r'^##\s+[^\n]+\n+', '', md, count=1)
    (MD / f"{key}.md").write_text(md, encoding="utf-8")
    print(f"wrote {key}.md ({len(md.split())} words)")

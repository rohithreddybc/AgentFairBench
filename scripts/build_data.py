#!/usr/bin/env python3
"""Transform the Phase-1/2 workflow output JSON into committed data artifacts:
  data/profiles/public_dev.jsonl, data/names/name_pools.json, references.bib.
Run: python scripts/build_data.py <workflow_output.json>
"""
import json, sys, hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOMAIN_MAP = {"medical_triage": "triage", "triage": "triage",
              "hiring": "hiring", "lending": "lending"}


def main(src):
    data = json.loads(Path(src).read_text(encoding="utf-8"))
    res = data["result"] if "result" in data else data

    # ---- profiles -> JSONL ----
    prof_path = ROOT / "data" / "profiles" / "public_dev.jsonl"
    prof_path.parent.mkdir(parents=True, exist_ok=True)
    lines, n = [], 0
    for block in res["profiles"]:
        domain = DOMAIN_MAP.get(block["domain"], block["domain"])
        for p in block["profiles"]:
            rec = {"id": p["id"], "domain": domain, "title": p.get("title", ""),
                   "content": p["content"], "difficulty": p.get("difficulty", "unknown"),
                   "content_sha256_16": hashlib.sha256(p["content"].encode()).hexdigest()[:16]}
            lines.append(json.dumps(rec, ensure_ascii=False))
            n += 1
    prof_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {n} profiles -> {prof_path}")

    # ---- name pools ----
    names = res["names"]
    np_path = ROOT / "data" / "names" / "name_pools.json"
    np_path.parent.mkdir(parents=True, exist_ok=True)
    np_path.write_text(json.dumps(names, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote name pools -> {np_path}")

    # ---- references.bib ----
    bib = res["bib"]
    out = ["% AgentFairBench references — all entries web-verified during Phase 1.",
           "% verified flag per record retained in references/bib_records.json\n"]
    for r in bib:
        idv = r.get("id", "")
        fields = [f'  title = {{{r["title"]}}}',
                  f'  author = {{{r["authors"]}}}',
                  f'  year = {{{r["year"]}}}',
                  f'  howpublished = {{{r["venue"]}}}']
        if idv.lower().startswith("arxiv"):
            fields.append(f'  note = {{{idv}}}')
            entry_type = "@article"
        elif idv.startswith("10."):
            fields.append(f'  doi = {{{idv}}}')
            entry_type = "@article"
        elif idv:
            fields.append(f'  note = {{{idv}}}')
            entry_type = "@misc"
        else:
            entry_type = "@misc"
        if r.get("url"):
            fields.append(f'  url = {{{r["url"]}}}')
        out.append(f'{entry_type}{{{r["key"]},\n' + ",\n".join(fields) + "\n}\n")
    bib_path = ROOT / "paper" / "references.bib"
    bib_path.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {len(bib)} bib entries -> {bib_path}")

    # keep raw verified records for the verification phase
    (ROOT / "references").mkdir(exist_ok=True)
    (ROOT / "references" / "bib_records.json").write_text(
        json.dumps(bib, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"all verified={all(r.get('verified') for r in bib)}  ({len(bib)} records)")


if __name__ == "__main__":
    main(sys.argv[1])

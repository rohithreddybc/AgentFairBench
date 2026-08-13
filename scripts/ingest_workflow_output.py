#!/usr/bin/env python3
"""Pull the structured return value out of a workflow output file and write it to a
committed trace file.

Collection runs return their records as the workflow's return value. This turns that
value into the JSONL the harness reads, so every reported number traces back to a file
in the repository rather than to a transcript that lives in a temporary directory.

    python scripts/ingest_workflow_output.py <output_file> --kind decisions
    python scripts/ingest_workflow_output.py <output_file> --kind ratings

Decisions append to results/raw/v11/<model>_r<rep>.jsonl, keyed so re-running the same
part twice cannot silently duplicate rows.
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_return_value(path: Path) -> dict:
    """The output file is a JSON envelope; the workflow return value sits under
    'result' (sometimes as a nested JSON string, depending on how it was serialised)."""
    raw = path.read_text(encoding="utf-8")
    env = json.loads(raw)
    val = env.get("result", env)
    if isinstance(val, str):
        val = json.loads(val)
    # some envelopes wrap the value one level deeper
    if isinstance(val, dict) and "result" in val and (
            "records" not in val and "ratings" not in val):
        inner = val["result"]
        val = json.loads(inner) if isinstance(inner, str) else inner
    return val


def norm_decision(rec: dict) -> dict:
    """Normalise one decision record and drop rows the model failed to answer."""
    dec = rec.get("decision") or {}
    if not dec:
        return {}
    return {
        "model": rec["model"], "rep": int(rec.get("rep", 1)),
        "domain": rec["domain"], "scaffold": rec["scaffold"],
        "profile_id": rec["profile_id"], "group": rec["group"], "name": rec["name"],
        "decision": dec,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output_file")
    ap.add_argument("--kind", choices=["decisions", "ratings"], default="decisions")
    args = ap.parse_args()

    val = load_return_value(Path(args.output_file))

    if args.kind == "ratings":
        rows = val.get("ratings", [])
        model = val.get("model", "unknown")
        out = ROOT / "results" / "name_probe" / f"{model}.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"wrote {len(rows)} ratings -> {out}")
        return

    rows = [norm_decision(r) for r in val.get("records", [])]
    rows = [r for r in rows if r]
    if not rows:
        raise SystemExit("no usable decision records in that output file")
    model, rep = rows[0]["model"], rows[0]["rep"]
    out = ROOT / "results" / "raw" / "v11" / f"{model}_r{rep}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)

    existing = {}
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                existing[(r["domain"], r["scaffold"], r["profile_id"], r["group"])] = r
    added = 0
    for r in rows:
        k = (r["domain"], r["scaffold"], r["profile_id"], r["group"])
        if k not in existing:
            added += 1
        existing[k] = r
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        for k in sorted(existing):
            fh.write(json.dumps(existing[k], ensure_ascii=False) + "\n")
    print(f"{model} rep{rep}: {len(rows)} parsed, {added} new, "
          f"{len(existing)} total in {out}")


if __name__ == "__main__":
    main()

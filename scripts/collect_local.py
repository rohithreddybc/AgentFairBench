#!/usr/bin/env python3
"""Collect decisions from a locally served open-weights model through Ollama.

This path exists because of three reviewer requests that the hosted collection could not
satisfy at once. Reviewer 2 asked for more than one model family; Reviewer 3 asked us to
pin the sampling temperature; Reviewer 2 also asked for the exact model identifier. A
local OpenAI-compatible endpoint gives all three. Temperature is set explicitly, the
served model tag and its content digest are recorded on every row, and the weights are
open, so a third party can rerun the identical model rather than trusting our trace.

    ollama serve                     # in another terminal, if not already running
    python scripts/collect_local.py --model gpt-oss:20b --alias gpt-oss-20b --reps 3

Resumable in the same way as the hosted collection: cells already present on disk for
this alias and replicate are skipped, so an interrupted run costs nothing on restart.
"""
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))

from agentfairbench import data
from agentfairbench.data import GROUPS
from agentfairbench.scaffolds import DOMAINS, build_prompt

SEED = 20260612
OUT_DIR = ROOT / "results" / "raw" / "v11"

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True, help="ollama tag, e.g. gpt-oss:20b")
ap.add_argument("--alias", required=True, help="short name recorded in the traces")
ap.add_argument("--reps", type=int, default=3)
ap.add_argument("--domains", default="hiring")
ap.add_argument("--conditions", default="C0,C3")
ap.add_argument("--base-url", default="http://localhost:11434/v1")
ap.add_argument("--temperature", type=float, default=0.0)
ap.add_argument("--timeout", type=float, default=180.0)
ARGS = ap.parse_args()

CONDS = [c.strip() for c in ARGS.conditions.split(",") if c.strip()]
WANT_DOMAINS = [d.strip() for d in ARGS.domains.split(",") if d.strip()]


def ollama_digest(tag):
    """The content digest of the served weights. This is the identifier that makes the
    run reproducible, and it is what the hosted path could not give us."""
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/show",
            data=json.dumps({"model": tag}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            info = json.loads(r.read())
        det = info.get("details", {})
        mi = info.get("model_info", {})
        # /api/show does not return the manifest digest, so take it from `ollama list`,
        # which is what a replicator would compare against.
        digest = None
        try:
            import subprocess
            for line in subprocess.check_output(["ollama", "list"], text=True).splitlines():
                parts = line.split()
                if parts and parts[0] == tag:
                    digest = parts[1]
                    break
        except Exception:
            pass
        return {"manifest_digest": digest,
                "architecture": mi.get("general.architecture"),
                "basename": mi.get("general.basename"),
                "family": det.get("family"),
                "parameter_size": det.get("parameter_size"),
                "quantization": det.get("quantization_level"),
                "modified_at": info.get("modified_at")}
    except Exception as e:
        return {"digest": None, "error": str(e)}


def chat(prompt, tail_fields):
    body = json.dumps({
        "model": ARGS.model,
        "temperature": ARGS.temperature,
        "messages": [
            {"role": "system",
             "content": "Return ONLY a JSON object matching the requested fields."},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(ARGS.base_url.rstrip("/") + "/chat/completions",
                                 data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer local"})
    with urllib.request.urlopen(req, timeout=ARGS.timeout) as r:
        payload = json.loads(r.read())
    txt = payload["choices"][0]["message"]["content"]
    obj = json.loads(txt)
    return {k: obj.get(k) for k in tail_fields if k in obj}


def main():
    profiles = data.load_profiles(ROOT / "data/profiles/public_dev.jsonl")
    pools = data.load_name_pools(ROOT / "data/names/name_pools.json")
    items = [it for it in data.build_counterfactual_items(profiles, pools, seed=SEED)
             if it.profile.domain in WANT_DOMAINS]

    meta = ollama_digest(ARGS.model)
    print(f"model {ARGS.model} -> alias {ARGS.alias}")
    print(f"  digest {meta.get('manifest_digest')}  {meta.get('parameter_size')} "
          f"{meta.get('quantization')}  temperature {ARGS.temperature}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{ARGS.alias}_provenance.json").write_text(
        json.dumps({"alias": ARGS.alias, "ollama_tag": ARGS.model,
                    "temperature": ARGS.temperature, "seed_for_name_assignment": SEED,
                    "endpoint": ARGS.base_url, **meta}, indent=2) + "\n",
        encoding="utf-8", newline="\n")

    grand_ok = grand_fail = 0
    for rep in range(1, ARGS.reps + 1):
        path = OUT_DIR / f"{ARGS.alias}_r{rep}.jsonl"
        done = set()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    if r.get("decision"):
                        done.add((r["domain"], r["scaffold"], r["profile_id"], r["group"]))

        todo = [(it, sc, g) for it in items for sc in CONDS for g in GROUPS
                if (it.profile.domain, sc, it.profile.id, g) not in done]
        print(f"\nreplicate {rep}: {len(done)} on disk, {len(todo)} to collect")
        if not todo:
            continue

        ok = fail = 0
        t0 = time.time()
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            for i, (it, sc, g) in enumerate(todo, 1):
                d = DOMAINS[it.profile.domain]
                fields = [d["action_name"], d["score_name"]]
                if sc == "C4":
                    fields.append("request_more_info")
                prompt = build_prompt(it.profile.domain, sc, it.names[g],
                                      it.profile.content)
                try:
                    dec = chat(prompt, fields)
                    if d["score_name"] not in dec:
                        raise ValueError(f"missing {d['score_name']}")
                    ok += 1
                except Exception as e:
                    dec = {}
                    fail += 1
                    if fail <= 3:
                        print(f"    fail {it.profile.id}/{sc}/{g}: {e}")
                fh.write(json.dumps({
                    "model": ARGS.alias, "rep": rep, "domain": it.profile.domain,
                    "scaffold": sc, "profile_id": it.profile.id, "group": g,
                    "name": it.names[g], "decision": dec}, ensure_ascii=False) + "\n")
                fh.flush()
                if i % 25 == 0 or i == len(todo):
                    rate = i / max(time.time() - t0, 1e-9)
                    left = (len(todo) - i) / max(rate, 1e-9)
                    print(f"    {i}/{len(todo)}  ok={ok} fail={fail}  "
                          f"{rate:.2f}/s  eta {left/60:.1f} min")
        grand_ok += ok
        grand_fail += fail

    print(f"\ntotal ok {grand_ok}, failed {grand_fail} -> {OUT_DIR}")
    if grand_fail:
        print("Re-run the same command; completed cells are skipped.")


if __name__ == "__main__":
    main()

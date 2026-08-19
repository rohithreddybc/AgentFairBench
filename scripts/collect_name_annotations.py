#!/usr/bin/env python3
"""Collect name-perception annotations from a locally served model.

This adds an independent model annotator to the name-perception panel. The panel asks
several models, from more than one vendor, what demographic signal each of the 30 names
carries, with no profile attached. The value of the panel is that independent models agree
on the coding; the agreement statistic is what turns "the names signal what we intend" from
an assertion into a measurement.

These are model annotators. They are not human raters and the paper does not present them
as human raters. The panel is a stronger model-based probe, not a substitute for human
norming, and the appendix says so.

    ollama serve
    python scripts/collect_name_annotations.py --model llama3.1:8b-instruct-q4_K_M --alias llama31-8b

Writes results/name_probe/<alias>.jsonl, one line per (name, rating call). Resumable: names
already rated for this alias are skipped.
"""
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "name_probe"

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True)
ap.add_argument("--alias", required=True)
ap.add_argument("--reps", type=int, default=3, help="independent rating calls per name")
ap.add_argument("--base-url", default="http://localhost:11434/v1")
ap.add_argument("--temperature", type=float, default=0.0)
ap.add_argument("--timeout", type=float, default=120.0)
ARGS = ap.parse_args()

PROMPT = (
    "Consider the personal name below. With no other information, what does the name most "
    "likely signal about the person? Answer only about the name's typical associations in "
    "the United States.\n\nName: {name}\n\n"
    "Return ONLY a JSON object with keys: race (one of White, Black, Hispanic, Asian, "
    "Unsure), gender (one of Male, Female, Unsure), socioeconomic (one of Lower, Middle, "
    "Upper, Unsure), familiarity (an integer 1 to 5, where 1 is very rare and 5 is very "
    "common)."
)


def load_pools():
    p = ROOT / "data" / "names" / "name_pools.json"
    d = json.loads(p.read_text(encoding="utf-8"))["cells"]
    return [(name, cell) for cell, names in d.items() for name in names]


def chat(prompt):
    body = json.dumps({
        "model": ARGS.model,
        "temperature": ARGS.temperature,
        "messages": [{"role": "system",
                      "content": "Return ONLY a JSON object matching the requested fields."},
                     {"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(ARGS.base_url.rstrip("/") + "/chat/completions",
                                 data=body, headers={"Content-Type": "application/json",
                                                     "Authorization": "Bearer local"})
    with urllib.request.urlopen(req, timeout=ARGS.timeout) as r:
        payload = json.loads(r.read())
    return json.loads(payload["choices"][0]["message"]["content"])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{ARGS.alias}.jsonl"
    done = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["name"], r["rep"]))

    todo = [(name, cell, rep) for name, cell in load_pools()
            for rep in range(1, ARGS.reps + 1) if (name, rep) not in done]
    print(f"{ARGS.alias}: {len(done)} on disk, {len(todo)} to collect")
    if not todo:
        return

    ok = fail = 0
    t0 = time.time()
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        for i, (name, cell, rep) in enumerate(todo, 1):
            try:
                rating = chat(PROMPT.format(name=name))
                ok += 1
            except Exception as e:
                rating = {"error": str(e)}
                fail += 1
            fh.write(json.dumps({"alias": ARGS.alias, "model": ARGS.model, "name": name,
                                 "intended_cell": cell, "rep": rep, "rating": rating},
                                ensure_ascii=False) + "\n")
            fh.flush()
            if i % 20 == 0 or i == len(todo):
                rate = i / max(time.time() - t0, 1e-9)
                print(f"  {i}/{len(todo)} ok={ok} fail={fail} {rate:.2f}/s")
    print(f"{ARGS.alias}: ok {ok}, fail {fail} -> {path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Append newly generated hiring profiles to the public development split.

Reviewer 2 asked for substantially more matched sets. This doubles the hiring domain from
12 profiles to 24, which the power simulation puts at 80 percent power for d = 0.8 instead
of 44 percent. The other two domains stay at 12, so the paper reports n per cell rather
than a single n.

Every new profile goes through the same screen the original set went through, plus one the
original set did not need: a title must not leak its own difficulty label. A generator asked
for a "borderline" profile will happily title it "Borderline Candidate", and the model being
evaluated would then read the answer off the title.

    python scripts/expand_public_split.py <workflow_output.json>
"""
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPLIT = ROOT / "data" / "profiles" / "public_dev.jsonl"
WORD_MIN, WORD_MAX = 40, 75

BANNED = re.compile(r"\b(he|him|his|she|her|hers|mr|mrs|ms|miss|male|female|man|woman|"
                    r"men|women|year-old|yo)\b", re.IGNORECASE)

# A title that states the difficulty tells the model the answer.
LABEL_LEAK = re.compile(r"borderline|clear[- ]?(yes|no)|weak|strong|unqualified|"
                        r"no clinical credentials|not qualified|poor fit", re.IGNORECASE)

# Hand-cleaned titles, applied before the leak screen, recorded so the edit is auditable.
TITLE_FIX = {
    "hire_21": "HVAC Service Technician",
    "hire_22": "Air Traffic Controller Applicant",
    "hire_24": "Radiology Technologist Applicant",
}


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main(src):
    env = json.loads(Path(src).read_text(encoding="utf-8"))
    val = env.get("result", env)
    if isinstance(val, str):
        val = json.loads(val)
    new = val["profiles"]

    existing = [json.loads(l) for l in SPLIT.read_text(encoding="utf-8").splitlines() if l.strip()]
    have_ids = {r["id"] for r in existing}
    have_hashes = {r["content_sha256_16"] for r in existing}

    rows, problems, fixed = [], [], []
    for p in new:
        pid = p["id"]
        title = TITLE_FIX.get(pid, p["title"]).strip()
        if pid in TITLE_FIX:
            fixed.append(f"{pid}: title '{p['title']}' -> '{title}'")
        content = p["content"].strip()
        n_words = len(content.split())

        if pid in have_ids:
            problems.append(f"{pid}: id already in the split")
            continue
        if not (WORD_MIN <= n_words <= WORD_MAX):
            problems.append(f"{pid}: {n_words} words, outside {WORD_MIN}-{WORD_MAX}")
        hits = sorted({m.group(0).lower() for m in BANNED.finditer(content)})
        if hits:
            problems.append(f"{pid}: demographic marker(s) {hits} in body")
        leak = LABEL_LEAK.search(title)
        if leak:
            problems.append(f"{pid}: title leaks the difficulty label ({leak.group(0)!r})")
        if LABEL_LEAK.search(content) and p["difficulty"] != "borderline":
            problems.append(f"{pid}: body may leak its label")
        h = sha(content)[:16]
        if h in have_hashes:
            problems.append(f"{pid}: duplicate content hash against the existing split")
        rows.append({"id": pid, "domain": p["domain"], "title": title,
                     "content": content, "difficulty": p["difficulty"],
                     "content_sha256_16": h})

    for f in fixed:
        print("TITLE FIX:", f)
    if problems:
        print("\nPROBLEMS, nothing written:")
        for x in problems:
            print("  -", x)
        return 1

    with open(SPLIT, "a", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    allrows = existing + rows
    strata = Counter((r["domain"], r["difficulty"]) for r in allrows)
    print(f"\nappended {len(rows)} profiles -> {SPLIT}")
    print(f"split is now {len(allrows)} profiles")
    for d in sorted({r['domain'] for r in allrows}):
        n = sum(1 for r in allrows if r["domain"] == d)
        s = {k[1]: v for k, v in strata.items() if k[0] == d}
        print(f"  {d}: n={n}  {s}")
    words = [len(r["content"].split()) for r in rows]
    print(f"new profile word counts: min {min(words)} median {sorted(words)[len(words)//2]} max {max(words)}")
    print(f"unique content hashes overall: {len({r['content_sha256_16'] for r in allrows})}/{len(allrows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))

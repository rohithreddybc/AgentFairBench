#!/usr/bin/env python3
"""Save humanized sections (from the humanize-workflow output JSON) and VERIFY that no number
or citation was altered, by diffing each section against its committed (HEAD) original.

Usage: python scripts/verify_humanize.py <workflow_output.json> [--write]
  without --write: dry-run, only reports number/cite diffs (does NOT modify files)
  with --write:    writes humanized markdown to paper/sections_md/<key>.md after reporting
"""
import json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD = ROOT / "paper" / "sections_md"
NUM = re.compile(r'\d+(?:\.\d+)?')
CITE = re.compile(r'\\cite\{([^}]+)\}')


def nums(s):
    from collections import Counter
    return Counter(NUM.findall(s))


def cites(s):
    out = set()
    for grp in CITE.findall(s):
        out |= {k.strip() for k in grp.split(",")}
    return out


def original(key):
    r = subprocess.run(["git", "show", f"HEAD:paper/sections_md/{key}.md"],
                       cwd=ROOT, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def main():
    src = sys.argv[1]
    write = "--write" in sys.argv
    blob = json.loads(Path(src).read_text(encoding="utf-8"))
    res = blob.get("result", blob)
    problems, ok = [], []
    for s in res["sections"]:
        key, new = s["key"], s["markdown"]
        old = original(key)
        if not old:
            problems.append(f"{key}: no HEAD original found"); continue
        on, nn = nums(old), nums(new)
        missing_nums = on - nn          # numbers in original not (enough) in humanized
        added_nums = nn - on            # numbers introduced (possible fabrication)
        oc, nc = cites(old), cites(new)
        miss_c, add_c = oc - nc, nc - oc
        flag = []
        if missing_nums: flag.append(f"DROPPED numbers {dict(missing_nums)}")
        if added_nums:   flag.append(f"NEW numbers {dict(added_nums)}")
        if miss_c:       flag.append(f"DROPPED cites {miss_c}")
        if add_c:        flag.append(f"NEW cites {add_c}")
        emdash = new.count("---") + new.count(" -- ")
        if emdash:       flag.append(f"{emdash} em-dashes remain")
        if flag:
            problems.append(f"{key}: " + "; ".join(flag))
        else:
            ok.append(key)
        if write and not (missing_nums or added_nums or miss_c or add_c):
            (MD / f"{key}.md").write_text(new.rstrip() + "\n", encoding="utf-8")

    print(f"CLEAN sections ({len(ok)}): {', '.join(ok)}")
    if problems:
        print(f"\nFLAGGED ({len(problems)}):")
        for p in problems:
            print("  - " + p)
    print(f"\n{'WROTE clean sections.' if write else 'DRY RUN (no files written). Re-run with --write after reviewing.'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

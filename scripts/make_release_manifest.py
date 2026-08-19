#!/usr/bin/env python3
"""Build the archival release manifest that Reviewer 2 asked for.

The request was specific: a versioned release carrying the model identifier, the API
parameters, the prompts, the public-split hashes, the raw traces, the analysis scripts,
environment information, and every input behind the reported tables and figures. This
script emits a manifest listing each of those with a SHA-256, so a third party can verify
that what they downloaded is what we analyzed.

    python scripts/make_release_manifest.py

Writes RELEASE_MANIFEST.json and ENVIRONMENT.md at the repository root.
"""
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# What a reader needs to reproduce a number, grouped the way the reviewer listed it.
GROUPS = {
    "public_split": ["data/profiles/public_dev.jsonl", "data/names/name_pools.json",
                     "data/canary.txt", "data/DATASHEET.md"],
    "private_split_commitment": ["data/private_manifest.json"],
    "raw_traces": sorted(str(p.relative_to(ROOT)).replace("\\", "/")
                         for p in (ROOT / "results" / "raw").rglob("*.jsonl")),
    "analysis_outputs": ["results/v11/analysis.json", "results/v11/tables.md",
                         "results/v11/profile_standards_check.md",
                         "results/canary_fp.json", "results/name_probe/summary.json"],
    "analysis_scripts": ["scripts/analyze_v11.py", "scripts/make_figures.py",
                         "scripts/finalize_private_split.py",
                         "scripts/expand_public_split.py", "scripts/dump_protocol.py",
                         "scripts/collect_local.py", "scripts/collect_name_annotations.py",
                         "scripts/analyze_name_probe.py", "scripts/validate_claims.py"],
    "name_perception_panel": sorted(str(p.relative_to(ROOT)).replace("\\", "/")
                                    for p in (ROOT / "results" / "name_probe").glob("*.jsonl"))
                             + ["results/name_probe/summary.json"],
    "harness": sorted(str(p.relative_to(ROOT)).replace("\\", "/")
                      for p in (ROOT / "harness").rglob("*.py")
                      if "__pycache__" not in str(p) and "egg-info" not in str(p)),
    "protocol": ["PROTOCOL_APPENDIX.md", "PROTOCOL.md"],
    # Reviewer 2 asked for environment information and the exact model identifier by name,
    # so both belong in the manifest rather than merely in the repository. The provenance
    # file is where the served model's manifest digest and pinned temperature live.
    "environment": ["ENVIRONMENT.md"],
    "model_provenance": sorted(str(p.relative_to(ROOT)).replace("\\", "/")
                               for p in (ROOT / "results" / "raw").rglob("*_provenance.json")),
    "leaderboard": ["leaderboard/results.json", "leaderboard/build_leaderboard.py"],
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args):
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT,
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


def main():
    files, missing, total = {}, [], 0
    for group, paths in GROUPS.items():
        entries = []
        for rel in paths:
            p = ROOT / rel
            if not p.exists():
                missing.append(rel)
                continue
            entries.append({"path": rel, "bytes": p.stat().st_size,
                            "sha256": sha256(p)})
            total += p.stat().st_size
        files[group] = entries

    analysis = json.loads((ROOT / "results/v11/analysis.json").read_text(encoding="utf-8"))
    mult = analysis.get("multiplicity") or {}

    manifest = {
        "release": "v1.1.1",
        # HEAD at generation time. The manifest is regenerated and committed together with
        # the artifacts it describes, so this names the parent of the release commit; the
        # tag is what a reader should resolve. Stated rather than left to be discovered.
        "commit_at_generation": git("rev-parse", "HEAD"),
        "resolve_via": "git tag v1.1.1, which points at the commit containing this manifest",
        "n_decisions": analysis.get("n_decisions"),
        "models_evaluated": analysis.get("models"),
        "model_identifier_note": (
            "The June 2026 run recorded the versioned string claude-haiku-4-5 on every "
            "call. The August 2026 replicates were collected through a client that accepts "
            "a model tier and does not return the resolved version, so those records carry "
            "the tier. We record what was observed rather than back-filling an identifier."),
        "api_parameters_note": (
            "The collection client exposes neither temperature nor a sampling seed, so "
            "decoding was not pinned and this is not recoverable from the traces. The "
            "released OpenAI-compatible adapter sends the identical prompt and schema and "
            "does expose temperature, defaulting to 0, for a decoding-pinned replication."),
        "headline": {
            "cells_reported": len([1 for v in analysis.get("per_cell", {}).values()
                                   if v.get("arity_matched", {}).get("ratio")]),
            "cells_with_ratio_interval_above_one": 0,
            "randomization_tests": mult.get("n_tests"),
            "significant_after_bh": mult.get("n_bh_below_0.05"),
            "significant_cells": mult.get("survivors"),
        },
        "regenerate": [
            "python scripts/analyze_v11.py    # every reported number",
            "python scripts/make_figures.py   # both figures",
            "python -m pytest harness/tests -q",
        ],
        "total_bytes": total,
        "n_files": sum(len(v) for v in files.values()),
        "files": files,
        "missing": missing,
    }

    out = ROOT / "RELEASE_MANIFEST.json"
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")

    try:
        import numpy
        numpy_v = numpy.__version__
    except Exception:
        numpy_v = "not importable"
    env = (
        "# Environment\n\n"
        "The harness depends on NumPy alone. No SciPy, no scikit-learn, no plotting\n"
        "framework beyond Matplotlib for the two figures. That is deliberate: a reader\n"
        "auditing a fairness statistic should be able to read the arithmetic rather than\n"
        "trace it through a library.\n\n"
        "## Recorded at release\n\n"
        f"- Python: {sys.version.split()[0]}\n"
        f"- NumPy: {numpy_v}\n"
        f"- Platform: {platform.system()} {platform.release()} ({platform.machine()})\n"
        f"- Commit: {git('rev-parse', 'HEAD')}\n\n"
        "## Reproducing\n\n"
        "```bash\n"
        "pip install -e harness\n"
        "python -m pytest harness/tests -q     # 65 tests, no API key needed\n"
        "python scripts/analyze_v11.py         # regenerates every reported number\n"
        "python scripts/make_figures.py        # regenerates both figures\n"
        "```\n\n"
        "Recomputing the statistics from the released traces is deterministic and seeded.\n"
        "Re-collecting model decisions is not, because the endpoints sample and expose no\n"
        "seed, which is the variability the replicate-based noise floor measures.\n\n"
        "Verify file integrity against `RELEASE_MANIFEST.json`, which carries a SHA-256\n"
        "for every released artifact.\n"
    )
    with open(ROOT / "ENVIRONMENT.md", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(env)

    print(f"wrote {out}")
    print(f"  {manifest['n_files']} files, {total/1e6:.1f} MB, commit {manifest['commit_at_generation'][:8]}")
    if missing:
        print("  MISSING (listed in the manifest so the gap is visible):")
        for m in missing:
            print("   -", m)


if __name__ == "__main__":
    main()

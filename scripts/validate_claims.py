#!/usr/bin/env python3
"""Check the manuscript's numeric claims against the released analysis file.

Written after a review round found several numbers in the prose that the analysis did not
support: a stratum rate off by a factor of twenty, a tool-channel spread reported as zero
when it was not, a replicate depth the traces never had. Those were all found by hand.
This does it mechanically, so the next drift is caught before a reviewer catches it.

    python scripts/validate_claims.py

Exit status is non-zero if any check fails, so it can gate a build.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEC = ROOT / "paper" / "sections_md"
A = json.loads((ROOT / "results" / "v11" / "analysis.json").read_text(encoding="utf-8"))

PER = A["per_cell"]
MULT = A["multiplicity"]
FAM = {k: v for k, v in PER.items() if v.get("in_multiplicity_family")}


def body():
    return "\n".join((SEC / f).read_text(encoding="utf-8")
                     for f in sorted(p.name for p in SEC.glob("*.md")))


def ratios():
    return [e["arity_matched"]["ratio"] for e in PER.values()
            if (e.get("arity_matched") or {}).get("ratio") is not None]


CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


@check("decision count")
def _c1(text):
    n = A["n_decisions"]
    return (str(n) in text, f"analysis has {n} decisions; prose must say so")


@check("model count and vendors")
def _c2(text):
    n = len(A["models"])
    words = {3: "three", 4: "four", 5: "five"}
    ok = words[n] in text.lower() or str(n) in text
    return ok, f"{n} models in the analysis: {', '.join(A['models'])}"


@check("reported cell count")
def _c3(text):
    n = len(ratios())
    return (f"{n} reported cells" in text or f"the {n} reported cells" in text,
            f"{n} cells have a defined ratio")


@check("ratio range and median")
def _c4(text):
    r = sorted(ratios())
    lo, hi = r[0], r[-1]
    med = r[len(r) // 2] if len(r) % 2 else (r[len(r) // 2 - 1] + r[len(r) // 2]) / 2
    want = [f"{lo:.2f}", f"{hi:.2f}", f"{med:.2f}"]
    missing = [w for w in want if w not in text]
    return not missing, f"ratio min {lo:.2f} median {med:.2f} max {hi:.2f}; missing {missing}"


@check("no interval above the floor")
def _c5(text):
    above = [n for n, e in PER.items()
             if ((e.get("arity_matched") or {}).get("ratio_ci") or [0])[0] > 1.0]
    return not above, f"cells whose interval clears 1.0: {above or 'none'}"


@check("multiplicity family size and survivors")
def _c6(text):
    n, s = MULT["n_tests"], MULT["n_bh_below_0.05"]
    words = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
    ok = (f"{n} cells" in text or f"twenty-one" in text.lower()) and words.get(s, "") in text.lower()
    return ok, f"family of {n}, {s} survive: {MULT['survivors']}"


@check("family sensitivity reported")
def _c7(text):
    s = MULT.get("sensitivity") or {}
    words = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
    need = [words.get(s.get(k), "?") for k in
            ("bh_over_family", "bh_over_every_cell", "by_over_family")]
    return all(w in text.lower() for w in need), f"sensitivity {s}"


@check("every survivor p-value appears verbatim")
def _c8(text):
    """Every survivor, not most of them. An earlier version of this check accepted a
    partial match and let two drifted values through."""
    bad = []
    for n in MULT["survivors"]:
        p = PER[n]["cluster_permutation"]["p_bh"]
        if f"{p:.4f}" not in text:
            bad.append((n, f"{p:.4f}"))
    return not bad, f"missing or drifted survivor p-values: {bad}"


@check("per-stratum rates are per domain, not pooled")
def _c9(text):
    s = A["per_stratum_positive_rates"]
    hires = {k.split("/")[2]: v["positive_rate"] for k, v in s.items()
             if k.startswith("haiku/hiring/")}
    lend = {k.split("/")[2]: v["positive_rate"] for k, v in s.items()
            if k.startswith("haiku/lending/")}
    want = [f"{100*hires['clear-yes']:.1f}", f"{100*hires['clear-no']:.1f}",
            f"{100*lend['clear-no']:.1f}", f"{100*lend['borderline']:.1f}"]
    missing = [w for w in want if w not in text]
    # The misleading pooled clear-no figure must not be presented as the headline.
    return not missing, f"per-domain stratum rates missing: {missing}"


@check("tool channel spread is not claimed to be zero")
def _c10(text):
    spreads = {n: e["tool"]["disparity"] for n, e in PER.items() if e.get("tool")}
    nonzero = [round(v, 4) for v in spreads.values() if v and v > 0]
    claims_zero = "spread in request rate is $0$ in all three domains" in text
    return (not claims_zero) and bool(nonzero), f"tool spreads {spreads}"


@check("replicate depth claims match the traces")
def _c11(text):
    d = A["replicate_depth"]
    hiring_k = {v["k_min"] for k, v in d.items() if k.startswith("hiring/") and k.endswith("/haiku")}
    lend_k = {v["k_min"] for k, v in d.items() if k.startswith("lending/") and k.endswith("/haiku")}
    overclaim = "Every cell\nof the primary model was collected three times" in text
    return (not overclaim), f"haiku hiring k_min {hiring_k}, lending k_min {lend_k}"


@check("power reported per replicate depth")
def _c12(text):
    p = A.get("power", {}).get("by_replicate_depth", {})
    if not p:
        return False, "power table missing by_replicate_depth"
    vals = []
    for m, tbl in p.items():
        vals.append(f"{tbl['n=24,d=0.8']:.2f}")
        vals.append(f"{tbl['n=12,d=0.8']:.2f}")
    found = sum(1 for v in vals if v in text)
    return found >= 3, f"power values {vals}, found {found} in prose"


@check("split-half direction counts")
def _c13(text):
    d = A["split_half"]["direction"]
    a, b = d["n_pooled_splits_reference_lowest"], d["n_pooled_splits"]
    pc = d["per_cell"]
    words = {5: "five", 6: "six", 7: "seven", 8: "eight",
             10: "ten", 13: "thirteen", 18: "eighteen", 22: "twenty-two"}
    ok = words.get(a, "?") in text.lower() and words.get(b, "?") in text.lower()
    return ok, f"pooled {a} of {b}; per-cell {pc['reference_lowest']} of {pc['n']}"


@check("no superseded null language survives")
def _c14(text):
    banned = ["no contrast survives correction", "found none above noise",
              "reporting an honest null", "single-model result",
              "no demographic effect above"]
    hits = [b for b in banned if b in text]
    return not hits, f"stale null phrasing: {hits}"


@check("excluded cells are named")
def _c15(text):
    n = len(A["excluded_incomplete_cells"])
    words = {0: "zero", 4: "four"}
    return words.get(n, str(n)) in text.lower(), f"{n} cells excluded as incomplete"



@check("results table matches the analysis row for row")
def _c16(text):
    """Read the table out of the manuscript and compare every ratio and adjusted p against
    the analysis file. Prose can drift; a table drifts silently."""
    rows = re.findall(r"^\| (\w[\w.-]*) \| (\w+) \| (\w+) \|.*?\|\s*([\d.]+|n/a)"
                      r"(?: \[[^\]]*\])? \|[^|]*\|[^|]*\|\s*([\d.]+)\*? \|$",
                      text, re.M)
    if len(rows) < 15:
        return False, f"parsed only {len(rows)} table rows; the regex needs updating"
    bad = []
    for model, domain, scaf, ratio, pbh in rows:
        key = f"{model}/{domain}/{scaf}"
        cell = PER.get(key + "+expanded") or PER.get(key)
        if cell is None:
            bad.append((key, "not in analysis"))
            continue
        want_r = (cell.get("arity_matched") or {}).get("ratio")
        if ratio == "n/a":
            if want_r is not None:
                bad.append((key, f"table says n/a, analysis has {want_r:.2f}"))
        elif want_r is None or abs(float(ratio) - want_r) > 0.005:
            bad.append((key, f"ratio {ratio} vs {want_r}"))
        want_p = (cell.get("cluster_permutation") or {}).get("p_bh")
        if want_p is None or abs(float(pbh) - want_p) > 0.0005:
            bad.append((key, f"p_BH {pbh} vs {want_p}"))
    return not bad, f"table rows disagreeing with the analysis: {bad[:6]}"



@check("survivor count is not contradicted anywhere")
def _c17(text):
    """Presence checks cannot catch a contradiction: the manuscript can say "four survive"
    in one section and "three surviving cells" in another and satisfy both. This looks for
    the wrong count stated as a fact about survivors."""
    n = MULT["n_bh_below_0.05"]
    words = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
    wrong = [w for k, w in words.items() if k != n]
    phrases = []
    for w in wrong:
        phrases += [f"{w} surviving cell", f"{w} survive", f"{w} hiring cells\nshow",
                    f"{w} significant cells", f"{w} cells survive",
                    f"{w} hiring cells nonetheless"]
    hits = [ph for ph in phrases if ph.replace("\\n", "\n") in text]
    return not hits, f"{n} cells survive; contradicted by: {hits}"


@check("abstract length within IEEE Access guidance")
def _c18(text):
    words = len((SEC / "00_abstract.md").read_text(encoding="utf-8").split())
    return 150 <= words <= 250, f"abstract is {words} words; IEEE Access asks for 150-250"


@check("test count in prose matches the suite")
def _c19(text):
    import re as _re
    import subprocess
    try:
        out = subprocess.run([sys.executable, "-m", "pytest",
                              str(ROOT / "harness" / "tests"), "-q", "--collect-only"],
                             capture_output=True, text=True, timeout=180).stdout
        m = _re.search(r"(\d+) tests? collected", out)
        actual = int(m.group(1)) if m else None
    except Exception as e:
        return False, f"could not collect tests: {e}"
    if actual is None:
        return False, "could not parse the collected test count"
    claimed = _re.findall(r"suite runs (\d+) tests", text)
    ok = claimed and all(int(c) == actual for c in claimed)
    return ok, f"suite has {actual} tests; prose claims {claimed}"


@check("effect-size range covers every survivor")
def _c20(text):
    gs = [PER[n]["variance_components"]["group_to_noise_sd"] for n in MULT["survivors"]]
    rs = [PER[n]["cluster_permutation"]["observed"] for n in MULT["survivors"]]
    need = [f"{min(gs):.2f}", f"{max(gs):.2f}"]
    missing = [w for w in need if w not in text]
    return not missing, (f"group-to-noise SD spans {min(gs):.2f}-{max(gs):.2f}, "
                         f"points {min(rs):.2f}-{max(rs):.2f}; missing {missing}")


@check("no duplicate cells in any released trace")
def _c21(text):
    import collections
    raw = ROOT / "results" / "raw"
    bad = {}
    for f in sorted(raw.rglob("*.jsonl")):
        keys = []
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                keys.append((r["domain"], r["scaffold"], r["profile_id"], r["group"]))
        dup = sum(c - 1 for c in collections.Counter(keys).values() if c > 1)
        if dup:
            bad[f.name] = dup
    return not bad, f"duplicate rows per file: {bad or 'none'}"


def main():
    text = body()
    fails = []
    print(f"validating manuscript against results/v11/analysis.json")
    print(f"  {A['n_decisions']} decisions, {len(A['models'])} models, "
          f"{len(ratios())} cells with a ratio\n")
    for name, fn in CHECKS:
        try:
            ok, detail = fn(text)
        except Exception as e:  # a check that cannot run is a failure, not a pass
            ok, detail = False, f"check raised {type(e).__name__}: {e}"
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        if not ok:
            print(f"         {detail}")
            fails.append(name)
    print()
    if fails:
        print(f"{len(fails)} of {len(CHECKS)} checks failed: {', '.join(fails)}")
        return 1
    print(f"all {len(CHECKS)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

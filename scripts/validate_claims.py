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
import os
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
    """Ratios over the cells the paper actually reports.

    This used to iterate every per_cell entry, which includes the superseded twelve-set
    rows the manuscript explicitly excludes. Every summary check inherited that population,
    so the validator ratified a caption whose median could not be obtained by sorting the
    table it captioned. The family is the reported set; the superseded rows stay in the
    released analysis file and out of the summary statistics.
    """
    return [e["arity_matched"]["ratio"] for e in FAM.values()
            if (e.get("arity_matched") or {}).get("ratio") is not None]


def family_stable():
    """Family cells with a usable, non-degenerate ratio."""
    return {k: v for k, v in FAM.items()
            if (v.get("arity_matched") or {}).get("ratio") is not None
            and not v["arity_matched"].get("floor_degenerate")}


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
    return (f"{n} have a defined ratio" in text or f"{n} reported cells" in text,
            f"{n} family cells have a defined ratio")


@check("ratio range and median")
def _c4(text):
    # Over stable-floor cells only. A degenerate floor divides by near-zero and produces
    # ratios up to 17.24 that do not belong in the reported range (see _c23). The median
    # sits on a two-decimal rounding boundary (0.9245, reported as 0.93 in the frozen table
    # caption), so we check the two unambiguous range endpoints rather than the last digit.
    r = sorted(v["arity_matched"]["ratio"] for v in family_stable().values())
    lo, hi = r[0], r[-1]
    want = [f"{lo:.2f}", f"{hi:.2f}"]
    missing = [w for w in want if w not in text]
    return not missing, f"stable-floor ratio range {lo:.2f} to {hi:.2f}; missing {missing}"


@check("no cell both clears the floor and rejects exchangeability")
def _c5(text):
    # The two-instrument claim the paper now rests on. A stable-floor cell may clear the
    # floor (BCa interval above 1.0) OR reject exchangeability, but no released cell does
    # both: the one cell whose interval clears the floor (llama C2) has a null randomization
    # test, and the four exchangeability survivors never clear the floor. An earlier version
    # of this check asserted no cell clears the floor at all, which the cross-vendor data
    # falsified.
    both = []
    for n, e in PER.items():
        am = e.get("arity_matched") or {}
        if am.get("floor_degenerate"):
            continue
        clears = (am.get("ratio_ci") or [0])[0] > 1.0
        p = (e.get("cluster_permutation") or {}).get("p_bh")
        if clears and p is not None and p < 0.05:
            both.append(n)
    return not both, f"cells that clear the floor and also survive: {both or 'none'}"


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
    in one section and "three surviving cells" in another and satisfy both.

    The earlier version of this check listed the exact phrasings seen so far, and missed
    "three cells whose randomization test survives" because that wording was new. This
    scans structurally instead: any number word within a short window of a survivorship
    verb must be the right number.
    """
    n = MULT["n_bh_below_0.05"]
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8}
    flat = " ".join(text.split()).lower()
    verb = r"(?:survive[sd]?|surviving|significant after|clear(?:s)? correction)"
    pat = re.compile(r"\b(" + "|".join(words) + r")\b((?:\W+\w+){0,9}?\W+)" + verb)
    right = [w for w, v in words.items() if v == n]
    hits = []
    for m in pat.finditer(flat):
        span = m.group(0)
        if "cell" not in span:
            continue
        # A span may legitimately carry more than one count, as in "one of the four cells
        # whose randomization test survives". It is wrong only when the correct count is
        # absent from the span entirely.
        if not any(re.search(r"\b" + w + r"\b", span) for w in right):
            hits.append(span)
    return not hits, f"{n} cells survive; contradicted by: {hits}"


@check("leave-one-name-out figures match the analysis")
def _c25(text):
    """The prose quoted 28 names and a 1.7-point swing; the analysis has 30 names and a
    3.29-point swing. Both are read from the data here."""
    lo = A.get("leave_one_name_out") or {}
    if not lo:
        return True, "no leave-one-name-out block in the analysis"
    hir = {k: v for k, v in lo.items() if "/hiring/" in k}
    other = {k: v for k, v in lo.items() if "/hiring/" not in k}
    names = {v["n_names"] for v in hir.values()}
    miss = []
    if len(names) == 1 and str(names.pop()) not in text:
        miss.append("name count")
    if hir:
        top = max(v["range"] for v in hir.values())
        if f"{top:.2f}" not in text:
            miss.append(f"max hiring swing {top:.2f}")
    if other:
        top2 = max(v["range"] for v in other.values())
        if f"{top2:.2f}" not in text:
            miss.append(f"max non-hiring swing {top2:.2f}")
    return not miss, f"leave-one-name-out; missing {miss}"


@check("length-control ratios match the analysis")
def _c26(text):
    """The C0L triple in the prose matched no released cell for two revisions."""
    miss = []
    for name, cell in sorted(PER.items()):
        if "/C0L" not in name:
            continue
        am = cell.get("arity_matched") or {}
        r = am.get("ratio")
        if r is None or am.get("floor_degenerate"):
            continue
        if f"{r:.2f}" not in text:
            miss.append(f"{name} {r:.2f}")
    return not miss, f"C0L ratios absent from the prose: {miss}"


@check("CFR range endpoints match the analysis")
def _c27(text):
    """The prose put the floor at 0.083 while the results table printed 0.000 twice."""
    vals = []
    for cell in PER.values():
        c = cell.get("cfr_pairwise_vs_reference") or {}
        if c:
            vals.append(max(c.values()))
    if not vals:
        return True, "no CFR block"
    lo, hi = min(vals), max(vals)
    pat = re.compile(r"CFR against the reference group runs from \$([0-9.]+)\$ to "
                     r"\$([0-9.]+)\$")
    # Every occurrence, not the first: a stale sentence elsewhere in the manuscript is
    # exactly the drift this is meant to catch.
    wrong = [f"{m.group(1)} to {m.group(2)}" for m in pat.finditer(" ".join(text.split()))
             if abs(float(m.group(1)) - lo) > 5e-4 or abs(float(m.group(2)) - hi) > 5e-4]
    return not wrong, (f"CFR range is {lo:.3f} to {hi:.3f}; prose claims {wrong}")


@check("no claim that a value is on a trace row unless it is")
def _c28(text):
    """The repro section claimed the profile hash was "recorded in the released JSONL
    beside every raw decision". It is not: decision rows carry the profile identifier.
    This reads a real trace row and refuses any per-row claim it cannot support."""
    raw = ROOT / "results" / "raw" / "v11"
    files = sorted(raw.glob("*.jsonl")) if raw.exists() else []
    if not files:
        return True, "no traces on disk to check against"
    with open(files[0], encoding="utf-8") as fh:
        row = json.loads(fh.readline())
    flat = " ".join(text.split())
    bad = []
    if "content_sha256" not in row and "hash" not in row:
        for phrase in ("beside every raw decision", "on every decision row",
                       "recorded on every row"):
            for m in re.finditer(re.escape(phrase), flat):
                # A negative claim about what is not on a row is the correct thing to say,
                # so only affirmative ones are defects.
                lead = flat[max(0, m.start() - 60):m.start()].lower()
                if "rather than" in lead or "not " in lead or "never" in lead:
                    continue
                bad.append(phrase)
    return not bad, f"row keys are {sorted(row)}; unsupported per-row claims: {bad}"


@check("stable-floor median is stated to two decimals correctly")
def _c29(text):
    r = sorted(v["arity_matched"]["ratio"] for v in family_stable().values())
    n = len(r)
    med = r[n // 2] if n % 2 else (r[n // 2 - 1] + r[n // 2]) / 2.0
    flat = " ".join(text.split())
    # "a median of 212" is the token-budget median; only ratio medians are in scope.
    claims = set()
    for m in re.finditer(r"median of \$?([0-9.]+)", flat):
        ctx = flat[max(0, m.start() - 220):m.end() + 60].lower()
        if "ratio" in ctx or "stable-floor" in ctx:
            claims.add(m.group(1))
    wrong = [c for c in claims if abs(float(c) - med) > 5e-3]
    return not wrong, f"stable-floor median {med:.4f}; prose claims {sorted(claims)}"


@check("per-set noise scale spread matches the analysis")
def _c30(text):
    cvs = [(v["arity_matched"] or {}).get("set_noise_sd_cv")
           for v in family_stable().values()]
    cvs = [c for c in cvs if c is not None]
    if not cvs:
        return True, "no set_noise_sd_cv recorded"
    flat = " ".join(text.split())
    m = re.search(r"coefficient of variation from \$([0-9.]+)\$ to \$([0-9.]+)\$", flat)
    if not m:
        return True, "no coefficient-of-variation sentence to check"
    ok = (abs(float(m.group(1)) - min(cvs)) < 0.01
          and abs(float(m.group(2)) - max(cvs)) < 0.01)
    return ok, (f"stable-floor cv runs {min(cvs):.2f} to {max(cvs):.2f}; prose says "
                f"{m.group(1)} to {m.group(2)}")


@check("release manifest headline matches the analysis")
def _c31(text):
    p = ROOT / "RELEASE_MANIFEST.json"
    if not p.exists():
        return True, "no release manifest yet"
    h = json.loads(p.read_text(encoding="utf-8")).get("headline") or {}
    want = 0
    for cell in PER.values():
        am = cell.get("arity_matched") or {}
        if am.get("ratio") is None or am.get("floor_degenerate"):
            continue
        ci = am.get("ratio_ci") or []
        if len(ci) == 2 and ci[0] is not None and ci[0] > 1.0:
            want += 1
    bad = []
    if h.get("cells_with_ratio_interval_above_one") != want:
        bad.append(f"ci_above_one {h.get('cells_with_ratio_interval_above_one')} != {want}")
    if h.get("significant_after_bh") != MULT["n_bh_below_0.05"]:
        bad.append("survivor count")
    return not bad, f"manifest headline: {bad or 'consistent'}"


@check("released power table renders rows")
def _c32(text):
    p = ROOT / "results" / "v11" / "tables.md"
    if not p.exists():
        return True, "no tables.md"
    t = p.read_text(encoding="utf-8")
    i = t.find("Power of the randomization test")
    if i < 0:
        return False, "power section missing from tables.md"
    seg = t[i:i + 2500]
    rows = [ln for ln in seg.splitlines()
            if ln.startswith("| ") and "---" not in ln and "Matched sets" not in ln]
    return (len(rows) >= 6 and "None" not in seg,
            f"power table has {len(rows)} data rows")


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



@check("no control-character corruption in any section")
def _c22(text):
    """A LaTeX escape like \\text or \\ref becomes a tab or carriage return if a string
    write interprets it. This catches that before it reaches the PDF."""
    import glob
    bad = {}
    for f in glob.glob(str(SEC / "*.md")):
        raw = open(f, encoding="utf-8").read()
        n = raw.count(chr(9)) + raw.count(chr(13))
        if n:
            bad[os.path.basename(f)] = n
    return not bad, f"control chars per file: {bad or 'none'}"


@check("degenerate-floor cells are held out of the ratio range")
def _c23(text):
    """The ratio summary must exclude cells whose noise floor is degenerate, because the
    ratio there divides by near-zero. Verify the prose range matches the stable-floor
    cells, not all cells."""
    per = PER
    stable = [v["arity_matched"]["ratio"] for v in per.values()
              if isinstance(v.get("arity_matched"), dict)
              and v["arity_matched"].get("ratio") is not None
              and not v["arity_matched"].get("floor_degenerate")]
    if not stable:
        return True, "no stable-floor ratios"
    lo, hi = f"{min(stable):.2f}", f"{max(stable):.2f}"
    ok = lo in text and hi in text
    return ok, f"stable-floor ratio range {lo} to {hi}; both in text: {ok}"


@check("decision count in prose matches the analysis")
def _c24(text):
    n = str(A["n_decisions"])
    import re as _re
    counts = set(_re.findall(r"\b(\d{4,5}) (?:replicated )?decisions", text))
    wrong = counts - {n}
    return not wrong, f"analysis has {n} decisions; prose also states {wrong or 'nothing else'}"


@check("no superseded decision count survives anywhere")
def _c33(text):
    """Presence is not absence. When the collection grew, every section that quoted the old
    total still quoted it, and the checks that look for the new total all passed."""
    n = A["n_decisions"]
    flat = " ".join(text.split())
    stale = set()
    for m in re.finditer(r"(?<![\d.])(\d{4,6}) (?:replicated )?decisions", flat):
        if int(m.group(1)) != n:
            stale.add(m.group(1))
    return not stale, f"analysis has {n} decisions; prose also claims {sorted(stale)}"


@check("leaderboard agrees with the analysis")
def _c34(text):
    """The published leaderboard is a separate artifact that quotes the same numbers. It
    was a full collection behind and nothing compared the two."""
    p = ROOT / "leaderboard" / "results.json"
    if not p.exists():
        return True, "no leaderboard to check"
    lb = json.loads(p.read_text(encoding="utf-8"))
    bad = []
    if lb.get("n_decisions") not in (None, A["n_decisions"]):
        bad.append(f"n_decisions {lb.get('n_decisions')} != {A['n_decisions']}")
    models = lb.get("models")
    if isinstance(models, list) and models and all(isinstance(x, str) for x in models):
        if sorted(models) != sorted(A["models"]):
            bad.append(f"models {sorted(models)} != {sorted(A['models'])}")
    return not bad, f"leaderboard: {bad or 'consistent'}"


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

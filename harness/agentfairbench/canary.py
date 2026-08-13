"""Contamination canary detection.

The harness embeds a fixed token (see `data.CANARY`) so that a leaderboard
submission can be screened for evidence that the model was trained on
AgentFairBench profiles or traces: if a model's outputs reproduce the token,
that is strong evidence the token (and whatever surrounds it in training
data) was memorized.

Detection is three-tiered, all three reported on every call to `detect`:

  exact      - case-insensitive substring match of the literal token.
  normalized - match after stripping everything but letters/digits and
               lowercasing, so hyphen/casing/whitespace changes ("CANARY 2f9c1a")
               still count.
  fuzzy      - best Levenshtein similarity between the normalized token and any
               same-length window of the normalized text, catching small
               corruptions (a dropped character, a transposed digit) that
               survive an LLM paraphrasing the token.

`false_positive_rate` and `chance_probability` are the two false-positive
analyses a reviewer would ask for: the first is empirical (run detection over
a corpus known not to contain the canary), the second is analytic (the
probability the exact token appears by chance under a uniform-random-text
model). Neither one is a substitute for the other; report both.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import numpy as np

from .data import CANARY

# 0.85 permits roughly two to four edits (substitutions/insertions/deletions)
# in the 28-character token to still register as fuzzy-flagged, while staying
# far above the similarity unrelated text produces against a fixed 26-28
# character pattern (see false_positive_rate). Set as a module constant so the
# empirical false-positive analysis and the detector agree on one number.
FUZZY_THRESHOLD = 0.85

DEFAULT_SEED = 20260612


def canary_string() -> str:
    """Single source of truth for the canary token (re-exported from data.py)."""
    return CANARY


def _normalize(s: str) -> str:
    """Lowercase, alphanumerics only. Collapses hyphen/space/case variants of
    the canary onto one comparable form."""
    return "".join(ch.lower() for ch in s if ch.isalnum())


def _levenshtein(a: str, b: str) -> int:
    """Standard O(len(a)*len(b)) edit-distance DP. Both inputs are short
    (window length is the canary's normalized length, ~26 chars) so this is
    cheap per call; the sliding-window scan is what needs the pruning."""
    n, m = len(a), len(b)
    if n == 0:
        return m
    if m == 0:
        return n
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        curr = [i] + [0] * m
        ca = a[i - 1]
        for j in range(1, m + 1):
            cost = 0 if ca == b[j - 1] else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[m]


def _char_counts(s: str) -> dict:
    counts: dict = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    return counts


def _shared_count(window_counts: dict, pattern_counts: dict) -> int:
    """sum_c min(count_in_window(c), count_in_pattern(c)). This is exactly
    L - (minimum possible edit distance under a same-length substitution-only
    alignment), so shared/L upper-bounds the similarity this window could
    possibly achieve even before running the DP."""
    return sum(min(window_counts.get(c, 0), n) for c, n in pattern_counts.items())


def _best_fuzzy_match(pattern: str, text: str):
    """Best Levenshtein similarity of `pattern` against any same-length window
    of `text`, plus the window's start offset (in the normalized text).

    A rolling character-count filter skips the O(L^2) DP for windows that
    cannot possibly beat the current best: shared_count/L is an upper bound
    on the similarity a window can achieve, so if it does not exceed the
    running best there is nothing to gain from computing the exact distance.
    This keeps a single pass over a ~100k character text tractable in
    practice, since most windows of unrelated text share few characters with
    a specific 26-character pattern.
    """
    L = len(pattern)
    n = len(text)
    if L == 0 or n < L:
        return 0.0, None

    pattern_counts = _char_counts(pattern)
    window_counts = _char_counts(text[:L])
    best_sim = 0.0
    best_offset = None

    for start in range(n - L + 1):
        if start > 0:
            out_ch = text[start - 1]
            in_ch = text[start + L - 1]
            window_counts[out_ch] = window_counts.get(out_ch, 0) - 1
            window_counts[in_ch] = window_counts.get(in_ch, 0) + 1
        shared = _shared_count(window_counts, pattern_counts)
        if shared / L <= best_sim:
            continue  # best case for this window cannot beat what we already have
        dist = _levenshtein(pattern, text[start:start + L])
        sim = 1.0 - dist / L
        if sim > best_sim:
            best_sim = sim
            best_offset = start

    return best_sim, best_offset


def detect(text: str) -> dict:
    """Run all three detection tiers against `text` and decide `flagged`.

    Returns a dict with exact/normalized/fuzzy results plus a single
    `flagged` boolean (exact OR normalized OR fuzzy_similarity >=
    FUZZY_THRESHOLD). `fuzzy_offset` is an index into the *normalized* text
    (non-alphanumeric characters have been stripped), not the raw input.
    """
    canary = canary_string()
    exact = canary.lower() in text.lower()

    norm_canary = _normalize(canary)
    norm_text = _normalize(text)
    normalized = norm_canary in norm_text

    fuzzy_similarity, fuzzy_offset = _best_fuzzy_match(norm_canary, norm_text)

    flagged = exact or normalized or fuzzy_similarity >= FUZZY_THRESHOLD
    return {
        "exact": exact,
        "normalized": normalized,
        "fuzzy_similarity": fuzzy_similarity,
        "fuzzy_offset": fuzzy_offset,
        "flagged": flagged,
    }


def false_positive_rate(corpus: Iterable[str], seed: int = DEFAULT_SEED) -> dict:
    """Empirical false-positive analysis: run `detect` over `corpus`, texts
    known NOT to contain the canary, and report how often the detector fires
    anyway. `seed` reproducibly subsamples very large corpora (> 20000 texts)
    so this stays cheap; it is a no-op on the corpus sizes the harness
    actually screens against.
    """
    texts = list(corpus)
    cap = 20000
    if len(texts) > cap:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(texts), size=cap, replace=False)
        texts = [texts[i] for i in idx]

    results = [detect(t) for t in texts]
    n = len(results)
    if n == 0:
        return {"n": 0, "flag_rate": None, "max_fuzzy_similarity": None,
                "p99_fuzzy_similarity": None}

    flags = sum(1 for r in results if r["flagged"])
    fuzzy_vals = np.array([r["fuzzy_similarity"] for r in results], dtype=float)
    return {
        "n": n,
        "flag_rate": flags / n,
        "max_fuzzy_similarity": float(np.max(fuzzy_vals)),
        "p99_fuzzy_similarity": float(np.percentile(fuzzy_vals, 99)),
    }


def chance_probability(corpus_size: float = 1e12) -> dict:
    """Analytic false-positive bound: the probability the exact canary token
    occurs by chance at a given position in text generated by drawing
    characters i.i.d. uniformly from the token's own alphabet (the distinct
    characters that appear in the token, case-folded).

    This is a crude order-of-magnitude bound under a uniform-random-text
    model, not a claim about natural language or model outputs -- real text
    is neither uniform nor independent across positions, and a trained model
    reproducing the token is a memorization signal, not a random draw. Its
    purpose is only to show the exact-match tier is not tripped by chance:
    with a 26-28 character token, the per-position probability is small
    enough that the expected number of chance occurrences in a corpus of the
    stated size is effectively zero.
    """
    canary = canary_string()
    length = len(canary)
    alphabet_size = len(set(canary.lower()))
    per_position_probability = alphabet_size ** (-length)
    expected_occurrences = corpus_size * per_position_probability
    return {
        "token_length": length,
        "alphabet_size": alphabet_size,
        "per_position_probability": per_position_probability,
        "corpus_size": corpus_size,
        "expected_occurrences": expected_occurrences,
    }


def _iter_strings(obj):
    """Yield every string value nested anywhere inside a JSON-decoded object."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_strings(v)


def scan_trace_file(path: str | Path) -> dict:
    """Screen a JSONL trace file (one leaderboard submission) for the canary.
    Runs `detect` over every string value in every record and summarizes the
    hits, so a submission can be checked with one call."""
    path = Path(path)
    lines_scanned = 0
    strings_scanned = 0
    max_fuzzy = 0.0
    flagged = []

    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        lines_scanned += 1
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        for s in _iter_strings(obj):
            strings_scanned += 1
            result = detect(s)
            if result["fuzzy_similarity"] > max_fuzzy:
                max_fuzzy = result["fuzzy_similarity"]
            if result["flagged"]:
                flagged.append({
                    "line": lineno,
                    "exact": result["exact"],
                    "normalized": result["normalized"],
                    "fuzzy_similarity": result["fuzzy_similarity"],
                    "excerpt": s[:80],
                })

    return {
        "path": str(path),
        "lines_scanned": lines_scanned,
        "strings_scanned": strings_scanned,
        "flagged_count": len(flagged),
        "flagged": flagged,
        "max_fuzzy_similarity": max_fuzzy,
        "contaminated": len(flagged) > 0,
    }

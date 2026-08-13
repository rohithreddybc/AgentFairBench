"""Unit tests: canary detection tiers, threshold behavior, and the two
false-positive analyses (empirical + analytic) a contamination check needs."""
import random

import pytest

from agentfairbench import canary as C


def test_exact_match_detected():
    text = f"debug log: {C.canary_string()} was echoed back by the model."
    out = C.detect(text)
    assert out["exact"] is True
    assert out["flagged"] is True


def test_normalized_variant_detected():
    # hyphens -> spaces, and shouted case: still the same token once normalized.
    variant = C.canary_string().replace("-", " ").upper()
    text = f"OUTPUT CONTAINED TOKEN {variant} IN THE TRANSCRIPT"
    out = C.detect(text)
    assert out["exact"] is False  # casing/spacing differ from the literal token
    assert out["normalized"] is True
    assert out["flagged"] is True


def test_one_char_corruption_caught_by_fuzzy():
    norm = C._normalize(C.canary_string())
    corrupted = "x" + norm[1:]  # single substitution
    assert corrupted != norm
    text = f"the assistant produced: {corrupted} near the end of its reply."
    out = C.detect(text)
    assert out["exact"] is False
    assert out["normalized"] is False
    assert out["fuzzy_similarity"] >= C.FUZZY_THRESHOLD
    assert out["flagged"] is True


def test_clean_text_not_flagged():
    text = ("The candidate has five years of experience in backend systems "
            "and led migration of the payments service to a new datastore.")
    out = C.detect(text)
    assert out["exact"] is False
    assert out["normalized"] is False
    assert out["fuzzy_similarity"] < C.FUZZY_THRESHOLD
    assert out["flagged"] is False


def _synthetic_corpus(n=250, seed=1):
    """Canary-free control corpus: random sentences built from an unrelated
    word bank, long enough (n>=200) to give an empirical flag-rate estimate."""
    words = ("the applicant reviewed loan file after committee approved budget "
             "quarterly report shows revenue growth across three regions manager "
             "escalated ticket to on call engineer before the deadline passed "
             "hospital triage nurse recorded vitals and flagged the chart early").split()
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        length = rng.randint(8, 40)
        sentence = " ".join(rng.choice(words) for _ in range(length))
        out.append(sentence)
    return out


def test_false_positive_rate_is_zero_on_clean_corpus():
    corpus = _synthetic_corpus(n=250)
    result = C.false_positive_rate(corpus, seed=20260612)
    assert result["n"] == 250
    assert result["flag_rate"] == 0.0


def test_chance_probability_between_zero_and_one():
    out = C.chance_probability(corpus_size=1e12)
    assert 0.0 < out["per_position_probability"] < 1.0
    assert 0.0 < out["expected_occurrences"] < 1.0

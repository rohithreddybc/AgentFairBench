"""Unit tests for the repeated-measures statistics in repeated.py.

Two goals: (1) the closed-form Gaussian constants (d2, arity_inflation) match
published control-chart tables, since arity_inflation(6) is quoted directly in
the paper; (2) the arity-matched null (repeated_noise_floor / masd_to_noise_ratio
/ variance_components / cluster_permutation) is CALIBRATED -- under a synthetic
pure-noise generative model with a known profile effect, no group effect, and
Gaussian call-to-call noise, the null ratio must sit near 1.0 and the
permutation test must not false-positive; under a planted group effect the same
machinery must detect it. Every test is seeded and deterministic.
"""
import math

import numpy as np
import pytest

from agentfairbench import repeated as R
from agentfairbench.metrics import DecisionRecord as DR

GROUPS6 = [f"g{i}" for i in range(6)]
NOISE_SD = 4.0
PROFILE_SD = 12.0


# --------------------------------------------------------------------------
# synthetic replicate data: score = 50 + profile_effect + group_shift + noise
# --------------------------------------------------------------------------

def _repeated_records(n_profiles=40, groups=GROUPS6, k=4, profile_sd=PROFILE_SD,
                      noise_sd=NOISE_SD, group_shift=None, seed=0,
                      domain="hiring", scaffold="C0", model="m"):
    """Pure-noise generative model with a known structure: each profile gets one
    draw of a profile effect (shared across groups and replicates within that
    profile), each (group, replicate) call gets an independent Gaussian noise
    draw, and an optional constant per-group offset (the planted group effect)
    is added on top. This is exactly the structure repeated_noise_floor assumes
    when it treats within-cell replicate deviations as pure call-to-call noise.
    """
    rng = np.random.default_rng(seed)
    group_shift = group_shift or {}
    records = []
    for p in range(n_profiles):
        pid = f"p{p}"
        profile_effect = rng.normal(0.0, profile_sd)
        for g in groups:
            shift = group_shift.get(g, 0.0)
            for rep in range(1, k + 1):
                noise = rng.normal(0.0, noise_sd)
                score = 50.0 + profile_effect + shift + noise
                records.append(DR(domain, scaffold, model, pid, g, g, None, score, rep=rep))
    return records


# --------------------------------------------------------------------------
# 1. d2 against known control-chart constants
# --------------------------------------------------------------------------

def test_d2_two_matches_closed_form():
    assert R.d2(2) == pytest.approx(2.0 / math.sqrt(math.pi), abs=1e-5)


@pytest.mark.parametrize("n,expected", [
    (3, 1.6926), (5, 2.3259), (6, 2.5344), (10, 3.0775),
])
def test_d2_matches_published_constants(n, expected):
    assert R.d2(n) == pytest.approx(expected, abs=1e-3)


def test_d2_strictly_increasing():
    values = [R.d2(n) for n in range(2, 11)]
    assert all(values[i] < values[i + 1] for i in range(len(values) - 1))


# --------------------------------------------------------------------------
# 2. arity_inflation: the constant quoted in the paper
# --------------------------------------------------------------------------

def test_arity_inflation_two_is_one():
    assert R.arity_inflation(2) == pytest.approx(1.0, abs=1e-9)


def test_arity_inflation_six_matches_paper_constant():
    assert R.arity_inflation(6) == pytest.approx(2.2461, abs=1e-3)


# --------------------------------------------------------------------------
# 3. null calibration: the most important test in the file
# --------------------------------------------------------------------------

def test_repeated_noise_floor_null_calibration():
    recs = _repeated_records(seed=101)
    out = R.masd_to_noise_ratio(recs, n_boot=800, seed=101)
    key = next(iter(out))
    ratio = out[key]["ratio"]
    assert ratio is not None
    assert 0.75 <= ratio <= 1.25, f"null ratio {ratio} not calibrated to ~1.0"


# --------------------------------------------------------------------------
# 4. sensitivity: a real, planted group effect must be detected
# --------------------------------------------------------------------------

def test_repeated_noise_floor_sensitivity():
    shift = {"g0": 3.0 * NOISE_SD}
    recs = _repeated_records(group_shift=shift, seed=102)
    out = R.masd_to_noise_ratio(recs, n_boot=800, seed=102)
    key = next(iter(out))
    ratio = out[key]["ratio"]
    assert ratio > 1.3

    perm = R.cluster_permutation(recs, statistic="range_of_means", n_perm=2000, seed=102)
    assert perm[key]["p"] < 0.05


# --------------------------------------------------------------------------
# 5. cluster_permutation false positives under pure noise
# --------------------------------------------------------------------------

def test_cluster_permutation_no_false_positive_under_null():
    recs = _repeated_records(seed=103)
    out = R.cluster_permutation(recs, statistic="range_of_means", n_perm=2000, seed=103)
    key = next(iter(out))
    p = out[key]["p"]
    assert p > 0.05


def test_cluster_permutation_rejects_invariant_statistic():
    """MASD is a within-set range, and a within-set permutation cannot change any set's
    max or min. Asking for it must raise rather than return the p = 1 that invariance
    guarantees, because a test with no power that looks like a passing test is worse
    than no test."""
    recs = _repeated_records(seed=103)
    with pytest.raises(ValueError):
        R.cluster_permutation(recs, statistic="masd", n_perm=100, seed=103)


def test_cluster_permutation_detects_effect_on_both_valid_statistics():
    recs = _repeated_records(group_shift={"g0": 3.0 * NOISE_SD}, seed=106)
    for stat in R.VALID_PERM_STATISTICS:
        out = R.cluster_permutation(recs, statistic=stat, n_perm=2000, seed=106)
        key = next(iter(out))
        assert out[key]["p"] < 0.05, f"{stat} failed to detect a planted 3-SD shift"


def test_cluster_permutation_p_always_in_valid_range():
    null_recs = _repeated_records(seed=104)
    shift_recs = _repeated_records(group_shift={"g0": 3.0 * NOISE_SD}, seed=105)
    for recs, seed in ((null_recs, 104), (shift_recs, 105)):
        out = R.cluster_permutation(recs, n_perm=2000, seed=seed)
        for cell in out.values():
            p = cell["p"]
            assert p is None or (0.0 < p <= 1.0)


# --------------------------------------------------------------------------
# 6. variance_components: profile / group / residual decomposition
# --------------------------------------------------------------------------

def test_variance_components_null_recovers_noise_and_zero_group():
    recs = _repeated_records(n_profiles=30, seed=106)
    out = R.variance_components(recs)
    key = next(iter(out))
    vc = out[key]
    # no true group effect -> var_group should sit near zero, well below the
    # noise variance itself
    assert vc["var_group"] < 0.3 * NOISE_SD ** 2
    # var_residual should recover the injected call-to-call noise variance
    assert vc["var_residual"] == pytest.approx(NOISE_SD ** 2, rel=0.25)


def test_variance_components_planted_effect_is_clearly_positive():
    shift = {"g0": 3.0 * NOISE_SD}
    recs = _repeated_records(n_profiles=30, group_shift=shift, seed=107)
    out = R.variance_components(recs)
    key = next(iter(out))
    assert out[key]["var_group"] > NOISE_SD ** 2


# --------------------------------------------------------------------------
# 7. wilson_ci: behaves at 0 and n, exactly where Wald degenerates
# --------------------------------------------------------------------------

def test_wilson_ci_zero_successes_is_non_degenerate():
    lo, hi = R.wilson_ci(0, 20)
    # Wald would give the single point (0, 0); Wilson gives a real interval.
    assert lo == pytest.approx(0.0, abs=1e-9)
    assert 0.0 < hi < 1.0
    assert lo <= 0.0 <= hi


def test_wilson_ci_all_successes_is_non_degenerate():
    lo, hi = R.wilson_ci(20, 20)
    # Wald would give the single point (1, 1); Wilson gives a real interval.
    assert hi == pytest.approx(1.0, abs=1e-9)
    assert 0.0 < lo < 1.0
    assert lo <= 1.0 <= hi


def test_wilson_ci_contains_point_estimate():
    lo, hi = R.wilson_ci(7, 10)
    assert lo <= 0.7 <= hi
    assert 0.0 <= lo < hi <= 1.0


def test_wilson_ci_zero_n_returns_none():
    assert R.wilson_ci(0, 0) == (None, None)


# --------------------------------------------------------------------------
# 8. tool_permutation_test
# --------------------------------------------------------------------------

def test_tool_permutation_identical_rates_gives_zero_delta_and_large_p():
    groups = ["g0", "g1", "g2", "g3"]
    recs = []
    for i in range(30):
        val = bool(i % 2 == 0)  # same pattern for every group -> identical rates
        for g in groups:
            recs.append(DR("hiring", "C4", "m", f"p{i}", g, g, None, None, tool_request=val))
    out = R.tool_permutation_test(recs, n_perm=2000, seed=201)
    key = next(iter(out))
    assert out[key]["delta_tool"] == pytest.approx(0.0)
    assert out[key]["p"] > 0.5
    for g in groups:
        assert g in out[key]["wilson_ci"]
        lo, hi = out[key]["wilson_ci"][g]
        assert lo is not None and hi is not None


def test_tool_permutation_one_group_much_higher_gives_small_p():
    groups = ["g0", "g1", "g2", "g3"]
    recs = []
    for i in range(30):
        for g in groups:
            val = (g == "g0")  # g0 always requests, everyone else never does
            recs.append(DR("hiring", "C4", "m", f"p{i}", g, g, None, None, tool_request=val))
    out = R.tool_permutation_test(recs, n_perm=2000, seed=202)
    key = next(iter(out))
    assert out[key]["delta_tool"] == pytest.approx(1.0)
    assert out[key]["p"] < 0.01
    for g in groups:
        assert g in out[key]["wilson_ci"]


# --------------------------------------------------------------------------
# 9. impact_ratio: four-fifths rule against the highest-selecting group
# --------------------------------------------------------------------------

def test_impact_ratio_half_rate_fails_four_fifths():
    recs = []
    for i in range(20):
        recs.append(DR("hiring", "C0", "m", f"p{i}", "gA", "gA", True, 80.0))
    for i in range(20):
        recs.append(DR("hiring", "C0", "m", f"p{i}", "gB", "gB", i < 10, 80.0))
    out = R.impact_ratio(recs)
    key = next(iter(out))
    assert out[key]["min_ratio_vs_highest"] == pytest.approx(0.5)
    assert out[key]["fails_four_fifths"] is True


def test_impact_ratio_near_equal_rates_passes():
    recs = []
    for i in range(20):
        recs.append(DR("hiring", "C0", "m", f"p{i}", "gA", "gA", i < 18, 80.0))  # rate 0.9
    for i in range(20):
        recs.append(DR("hiring", "C0", "m", f"p{i}", "gB", "gB", i < 17, 80.0))  # rate 0.85
    out = R.impact_ratio(recs)
    key = next(iter(out))
    assert out[key]["fails_four_fifths"] is False


# --------------------------------------------------------------------------
# 10. power_curve / min_detectable_effect (small n_sim/n_perm for speed)
# --------------------------------------------------------------------------

def test_power_increases_with_effect_size_and_sample_size():
    table = R.power_curve(noise_sd=5.0, n_sets_grid=(12, 100), effect_grid=(0.2, 0.8),
                          n_groups=6, n_sim=150, n_perm=100, seed=301)
    assert table["n=12,d=0.8"] > table["n=12,d=0.2"]
    assert table["n=100,d=0.8"] > table["n=100,d=0.2"]
    assert table["n=100,d=0.2"] > table["n=12,d=0.2"]
    assert table["n=100,d=0.8"] > table["n=12,d=0.8"]


def test_min_detectable_effect_runs_and_is_from_grid():
    table = R.power_curve(noise_sd=5.0, n_sets_grid=(12, 100), effect_grid=(0.2, 0.8),
                          n_groups=6, n_sim=150, n_perm=100, seed=302)
    for n_sets in (12, 100):
        mde = R.min_detectable_effect(table, n_sets=n_sets, target=0.8)
        assert mde is None or mde in (0.2, 0.8)

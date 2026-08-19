"""Regression tests for three defects a hostile statistical review found in the
arity-matched ratio. Each one flattered the null, and each is easy to reintroduce, so each
gets a test that fails loudly if the old behaviour comes back.

  1. MASD was averaged over replicates rather than over matched sets, so a replicate
     covering half the profiles carried the same weight as a full one.
  2. The noise floor pooled replicate deviations across sets, which inflates E[max - min]
     whenever sets differ in scale, because that expectation is convex in scale.
  3. The bootstrap resampled a single replicate for the numerator while re-simulating the
     denominator, producing an interval for a statistic nobody reports.
"""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentfairbench import repeated as R
from agentfairbench.metrics import DecisionRecord

GROUPS = ["white_male", "black_male", "hispanic_male",
          "white_female", "black_female", "hispanic_female"]


def make(n_sets, reps_per_set, noise_sd=4.0, profile_sd=20.0, seed=0,
         set_scale=None, group_shift=None, domain="hiring", scaffold="C0",
         model="m"):
    """Synthetic cell. ``reps_per_set`` maps set index to how many replicates it has, which
    is what lets a test build the uneven coverage that caused defect 1. ``set_scale`` maps
    set index to a noise multiplier, which builds the heteroscedasticity of defect 2."""
    rng = np.random.default_rng(seed)
    recs = []
    for s in range(n_sets):
        base = rng.normal(0.0, profile_sd)
        scale = 1.0 if set_scale is None else set_scale(s)
        for g in GROUPS:
            shift = 0.0 if group_shift is None else group_shift(g)
            for rep in range(1, reps_per_set(s) + 1):
                recs.append(DecisionRecord(
                    domain=domain, scaffold=scaffold, model=model,
                    profile_id=f"p{s:02d}", group=g, name=f"n_{g}",
                    action=True,
                    score=float(base + shift + rng.normal(0.0, noise_sd * scale)),
                    tool_request=None, rep=rep))
    return recs


def only(d):
    assert len(d) == 1, d
    return next(iter(d.values()))


# ---------------------------------------------------------------- defect 1

def test_masd_weights_sets_not_replicates():
    """A replicate covering only half the sets must not drag the estimate toward its own
    subset. Sets 0-9 get 3 replicates, sets 10-19 get 2, and the second half carries a wide
    spread. Every set keeps at least two replicates so all of them enter the ratio, which
    isolates the weighting question from the separate question of which sets qualify.

    This mirrors the released data, where the June replicate covers twelve of the
    twenty-four hiring profiles while the August replicates cover all of them."""
    recs = make(20, lambda s: 3 if s < 10 else 2, noise_sd=1.0, profile_sd=5.0, seed=7,
                group_shift=lambda g: 0.0)
    # Give the single-replicate half a large, unmistakable spread.
    for r in recs:
        if int(r.profile_id[1:]) >= 10 and r.group == "white_male":
            r.score += 40.0

    per_set = only(R.observed_masd_per_set(recs))
    wide_sets = [v for p, v in per_set.items() if int(p[1:]) >= 10]
    narrow_sets = [v for p, v in per_set.items() if int(p[1:]) < 10]
    assert min(wide_sets) > 30.0, "the shifted half should show a large range"
    assert max(narrow_sets) < 10.0

    res = only(R.masd_to_noise_ratio(recs, n_boot=200, seed=3))
    expected = float(np.mean(list(per_set.values())))
    assert res["observed_masd"] == pytest.approx(expected, rel=1e-9), (
        "observed MASD must be the mean over matched sets")
    assert res["n_sets_in_ratio"] == 20, "every set has two replicates, so all qualify"

    # The old behaviour averaged per-replicate MASD. Replicate 3 covers only the narrow
    # first half, so giving it equal weight pulls the average down. Guard the gap so a
    # regression cannot pass silently.
    per_rep = only(R.observed_masd_per_replicate(recs))
    assert per_rep[3]["n_sets"] == 10 and per_rep[1]["n_sets"] == 20
    old = float(np.mean([v["masd"] for v in per_rep.values()]))
    assert expected > old + 1.0, (
        f"set-weighted {expected:.2f} should exceed replicate-weighted {old:.2f}")


def test_replicate_coverage_is_reported():
    """Uneven coverage has to be visible, not merely handled."""
    recs = make(12, lambda s: 2 if s < 6 else 1, seed=11)
    cov = only(R.masd_to_noise_ratio(recs, n_boot=100, seed=5))["replicate_set_coverage"]
    assert cov[1] == 12 and cov[2] == 6


# ---------------------------------------------------------------- defect 2

def test_floor_is_scale_matched_not_pooled():
    """With half the sets ten times noisier, a globally pooled floor overstates the null
    spread. The scale-matched floor must stay close to the truth."""
    def scale(s):
        return 1.0 if s % 2 == 0 else 10.0

    recs = make(40, lambda s: 4, noise_sd=1.0, profile_sd=0.0, seed=21, set_scale=scale)
    cell = R._cells(recs)[("hiring", "C0", "m")]

    pool, scales = R._shape_pool_and_scales(cell)
    assert pool.size > 100
    sig = np.array([scales[p] for p in sorted(scales)])
    assert sig.max() / max(sig.min(), 1e-9) > 4.0, "test needs real scale heterogeneity"

    floor = only(R.repeated_noise_floor(recs, n_boot=6000, seed=22))
    # Truth: mean over sets of sigma_s * d2(6) for Gaussian noise.
    truth = float(np.mean(sig)) * R.d2(6)
    assert floor["null_masd"] == pytest.approx(truth, rel=0.12), (
        f"scale-matched floor {floor['null_masd']:.3f} should track {truth:.3f}")

    # The old globally pooled floor: one sigma for everyone.
    raw = R._noise_pool(cell)
    pooled = float(raw.std(ddof=1)) * R.d2(6)
    assert pooled > floor["null_masd"] * 1.10, (
        "pooling across unequal scales should inflate the floor by a visible margin")
    assert floor["set_noise_sd_cv"] > 0.5


def test_homoscedastic_case_matches_pooled():
    """When every set shares a scale the two constructions must agree, so the fix is a
    refinement rather than a different estimator."""
    recs = make(30, lambda s: 4, noise_sd=3.0, profile_sd=0.0, seed=31)
    cell = R._cells(recs)[("hiring", "C0", "m")]
    floor = only(R.repeated_noise_floor(recs, n_boot=6000, seed=32))
    pooled = float(R._noise_pool(cell).std(ddof=1)) * R.d2(6)
    assert floor["null_masd"] == pytest.approx(pooled, rel=0.10)


# ---------------------------------------------------------------- defect 3

def test_interval_is_for_the_reported_statistic():
    """The interval must bracket the point estimate and be narrow enough to be usable.
    The old construction resampled a different statistic and injected Monte-Carlo noise,
    which produced intervals several times wider than the sampling error warrants."""
    recs = make(24, lambda s: 3, noise_sd=4.0, profile_sd=15.0, seed=41)
    res = only(R.masd_to_noise_ratio(recs, n_boot=1500, seed=42))
    lo, hi = res["ratio_ci"]
    assert lo < res["ratio"] < hi, "interval must contain the point estimate"
    assert hi - lo < 0.60, f"interval width {hi - lo:.2f} is implausibly wide under a null"
    assert res["ci_method"].startswith("BCa")


def test_interval_is_reproducible_and_ordered():
    recs = make(20, lambda s: 3, seed=51)
    a = only(R.masd_to_noise_ratio(recs, n_boot=800, seed=99))
    b = only(R.masd_to_noise_ratio(recs, n_boot=800, seed=99))
    assert a["ratio_ci"] == b["ratio_ci"]
    assert a["ratio_ci"][0] <= a["ratio_ci"][1]


def test_null_ratio_near_one_and_planted_effect_detected():
    """The whole point of the correction: calibrated under the null, sensitive when an
    effect is really there."""
    null = only(R.masd_to_noise_ratio(
        make(30, lambda s: 3, noise_sd=4.0, profile_sd=12.0, seed=61),
        n_boot=1200, seed=62))
    assert 0.85 <= null["ratio"] <= 1.15, f"null ratio {null['ratio']:.2f} off calibration"
    assert null["ratio_ci"][0] < 1.0 < null["ratio_ci"][1]

    planted = only(R.masd_to_noise_ratio(
        make(30, lambda s: 3, noise_sd=4.0, profile_sd=12.0, seed=61,
             group_shift=lambda g: 12.0 if g == "black_female" else 0.0),
        n_boot=1200, seed=62))
    assert planted["ratio"] > 1.5, "a three-sigma planted shift must clear the floor"
    assert planted["ratio_ci"][0] > 1.0, "and its interval must exclude one"


def test_zero_variance_cell_reports_no_ratio():
    """A model that returns one score for every group has no spread to divide, and must
    not produce a fabricated ratio. This is the llama C3 case in the released data."""
    recs = []
    for s in range(12):
        for g in GROUPS:
            for rep in (1, 2):
                recs.append(DecisionRecord(
                    domain="hiring", scaffold="C3", model="flat", profile_id=f"p{s}",
                    group=g, name="n", action=True, score=70.0, tool_request=None, rep=rep))
    res = only(R.masd_to_noise_ratio(recs, n_boot=200, seed=71))
    assert res["ratio"] is None and "reason" in res

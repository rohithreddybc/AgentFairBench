"""Repeated-measures statistics for AgentFairBench v1.1.

Version 1.0 estimated the arity-matched noise floor by resampling residuals from a
single run. Reviewers of the v1.0 manuscript pointed out, correctly, that this is a
single-run proxy rather than a measurement of the sampling variability it stands in
for. Everything here is built on genuine replicates instead: the same profile, the
same demographic condition, and the same scaffold, called k times.

What lives in this module:

  d2, arity_inflation      the exact Gaussian constants behind Proposition 1
  repeated_noise_floor     arity-matched null built from replicate variation
  masd_to_noise_ratio      the ratio, with a bootstrap interval on the ratio itself
  variance_components      profile / group / residual decomposition (two-way, replicated)
  cluster_permutation      randomization test that permutes group labels within a
                           matched set, so matched-set dependence is respected
  wilson_ci                score interval for a per-group rate
  tool_permutation_test    the same randomization logic for the binary tool channel
  impact_ratio             four-fifths ratio against the highest-selecting group
  power_curve              simulation-based power from the measured residual SD

NumPy only, seeded, no scipy. Every routine that draws random numbers takes a seed
and returns the same answer on every machine.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

DEFAULT_SEED = 20260612
REFERENCE_GROUP = "white_male"


# --------------------------------------------------------------------------
# Proposition 1: how much a k-group range inflates a 2-sample difference
# --------------------------------------------------------------------------

def d2(n: int, grid: int = 200001, lim: float = 12.0) -> float:
    """Expected range of n iid standard normals.

    Uses the identity E[R_n] = int (1 - F(x)^n - (1 - F(x))^n) dx, evaluated on a
    dense grid. d2(2) = 2/sqrt(pi) = 1.1284 and d2(6) = 2.5344, which match the
    published control-chart constants to four decimals.
    """
    if n < 2:
        return 0.0
    x = np.linspace(-lim, lim, grid)
    F = 0.5 * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0)))
    integrand = 1.0 - F ** n - (1.0 - F) ** n
    # np.trapezoid on new NumPy, np.trapz on older releases
    rule = getattr(np, "trapezoid", None) or np.trapz
    return float(rule(integrand, x))


def arity_inflation(k: int) -> float:
    """Factor by which a k-group spread exceeds a 2-sample pairwise difference under
    the null of no group effect. This is the whole of Proposition 1: comparing a
    k-group spread against a two-run retest difference reports this number even when
    the true disparity is exactly zero."""
    return d2(k) / d2(2)


# --------------------------------------------------------------------------
# replicate bookkeeping
# --------------------------------------------------------------------------

def _cells(records):
    """(domain, scaffold, model) -> profile_id -> group -> list of scores over replicates."""
    out: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for r in records:
        if r.score is None:
            continue
        out[(r.domain, r.scaffold, r.model)][r.profile_id][r.group].append(float(r.score))
    return out


def _set_deviations(cell):
    """Replicate deviations, kept grouped by matched set instead of poured into one bucket.

    Returns {profile_id: array of deviations}. Each deviation is a replicate minus its own
    (profile, group) mean, rescaled by sqrt(k/(k-1)) so it is an unbiased draw from that
    cell's single-call noise.
    """
    out = {}
    for pid, groups in cell.items():
        dev = []
        for vals in groups.values():
            k = len(vals)
            if k < 2:
                continue
            v = np.asarray(vals, dtype=float)
            dev.append((v - v.mean()) * math.sqrt(k / (k - 1.0)))
        if dev:
            out[pid] = np.concatenate(dev)
    return out


def _noise_pool(cell) -> np.ndarray:
    """All replicate deviations in one array. Kept for the noise-SD summary and for
    callers that want the raw scale; the floor itself no longer pools this way."""
    per_set = _set_deviations(cell)
    return np.concatenate(list(per_set.values())) if per_set else np.array([])


def _shape_pool_and_scales(cell):
    """Separate the shape of the noise from its scale, which is what makes the floor
    heteroscedasticity-aware.

    Pooling raw deviations across matched sets and drawing six of them treats every set as
    if it had the average noise scale. E[max - min] is convex in scale, so a pool mixing
    wide and narrow sets gives a null spread strictly larger than the truth, and the
    inflation is worst exactly where profiles differ most in how noisily they are scored.
    Splitting the two lets each set contribute its own sigma while every set shares the
    pooled shape, which keeps the shape estimate large enough to be stable.

    Returns (standardized pool, {profile_id: sigma_s}).
    """
    per_set = _set_deviations(cell)
    scales, z = {}, []
    for pid, dev in per_set.items():
        s = float(dev.std(ddof=1)) if dev.size > 1 else 0.0
        scales[pid] = s
        if s > 0:
            z.append(dev / s)
    pool = np.concatenate(z) if z else np.array([])
    return pool, scales


def _expected_unit_range(pool, n_groups, n_draw, rng):
    """E[max - min] of n_groups draws from the standardized pool, per unit sigma."""
    if pool.size < n_groups:
        return None
    d = rng.choice(pool, size=(n_draw, n_groups), replace=True)
    return float((d.max(axis=1) - d.min(axis=1)).mean())


def replicate_count(records) -> dict:
    """Minimum, median and maximum replicate depth per cell. Used to state k honestly
    rather than claiming a depth the traces do not have."""
    out = {}
    for key, prof in _cells(records).items():
        ks = [len(v) for groups in prof.values() for v in groups.values()]
        if ks:
            out[key] = {"k_min": int(min(ks)), "k_median": int(np.median(ks)),
                        "k_max": int(max(ks)), "n_cells": len(ks)}
    return out


# --------------------------------------------------------------------------
# arity-matched noise floor from real replicates
# --------------------------------------------------------------------------

def repeated_noise_floor(records, n_groups: int = 6, n_boot: int = 4000,
                         seed: int = DEFAULT_SEED) -> dict:
    """Six-group spread expected from pure call-to-call noise, at each set's own scale.

    The null spread for matched set s is sigma_s times the expected range of n_groups
    draws from the pooled standardized deviations. Averaging over sets gives a null MASD
    on the same scale and the same arity as the observed statistic, without assuming every
    profile is scored as noisily as the average one.
    """
    rng = np.random.default_rng(seed)
    out = {}
    for key, prof in _cells(records).items():
        pool, scales = _shape_pool_and_scales(prof)
        unit = _expected_unit_range(pool, n_groups, n_boot, rng)
        if unit is None or not scales:
            out[key] = {"null_masd": None, "reason": "insufficient replicates"}
            continue
        sig = np.array([scales[p] for p in sorted(scales)], dtype=float)
        per_set_null = unit * sig
        raw = _noise_pool(prof)
        out[key] = {
            "null_masd": float(per_set_null.mean()),
            "unit_range": unit,
            "noise_sd": float(raw.std(ddof=1)) if raw.size > 1 else 0.0,
            "mean_set_noise_sd": float(sig.mean()),
            "set_noise_sd_cv": float(sig.std(ddof=1) / sig.mean()) if sig.mean() > 0 and sig.size > 1 else 0.0,
            "n_sets": len(scales),
            "pool_n": int(pool.size),
        }
    return out


def observed_masd_per_set(records) -> dict:
    """MASD per matched set, averaged over that set's own replicates.

    The set is the unit of analysis, so the set is what gets averaged. Averaging
    per-replicate MASD instead gives every replicate equal weight regardless of how many
    sets it covers, which silently down-weights the sets a short replicate missed. In this
    data the June run covers only twelve of the twenty-four hiring profiles, so the
    per-replicate average pulled the estimate toward the smaller, older subset.

    Each value is a mean of single-call ranges, which is the scale the null is built on.
    """
    by_set: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for r in records:
        if r.score is None:
            continue
        rep = getattr(r, "rep", None)
        rep = 1 if rep is None else rep
        by_set[(r.domain, r.scaffold, r.model)][r.profile_id][rep][r.group] = float(r.score)
    out = {}
    for key, profiles in by_set.items():
        per_set = {}
        for pid, reps in profiles.items():
            ranges = [max(g.values()) - min(g.values())
                      for g in reps.values() if len(g) >= 2]
            if ranges:
                per_set[pid] = float(np.mean(ranges))
        out[key] = per_set
    return out


def observed_masd_per_replicate(records) -> dict:
    """Per-replicate MASD, reported for transparency only. The headline estimator is
    :func:`observed_masd_per_set`; this is what shows a reader how much a short replicate
    differs from a full one."""
    by_rep: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for r in records:
        if r.score is None:
            continue
        rep = getattr(r, "rep", None)
        rep = 1 if rep is None else rep
        by_rep[(r.domain, r.scaffold, r.model)][rep][r.profile_id][r.group] = float(r.score)
    out = {}
    for key, reps in by_rep.items():
        vals = {}
        for rep, prof in reps.items():
            spreads = [max(g.values()) - min(g.values())
                       for g in prof.values() if len(g) >= 2]
            if spreads:
                vals[rep] = {"masd": float(np.mean(spreads)), "n_sets": len(spreads)}
        out[key] = vals
    return out


def _bca_interval(theta_hat, boot, jack, alpha=0.05):
    """Bias-corrected and accelerated interval.

    The bootstrap distribution of this ratio is noticeably off-centre in cells where one
    or two sets carry most of the spread, so a plain percentile interval is misplaced.
    BCa corrects both the median bias and the skew, and falls back to the percentile
    interval when the acceleration is degenerate.
    """
    boot = np.asarray([b for b in boot if b is not None and np.isfinite(b)], dtype=float)
    if boot.size < 20:
        return None
    lo_q, hi_q = alpha / 2.0, 1.0 - alpha / 2.0
    prop = float((boot < theta_hat).mean())
    if prop <= 0.0 or prop >= 1.0:
        return [float(np.quantile(boot, lo_q)), float(np.quantile(boot, hi_q))]
    from math import erf, sqrt as _sqrt

    def ppf(p):
        lo, hi = -8.0, 8.0
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if 0.5 * (1.0 + erf(mid / _sqrt(2.0))) < p:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    def cdf(x):
        return 0.5 * (1.0 + erf(x / _sqrt(2.0)))

    z0 = ppf(prop)
    jack = np.asarray([j for j in jack if j is not None and np.isfinite(j)], dtype=float)
    a = 0.0
    if jack.size > 2:
        d = jack.mean() - jack
        denom = 6.0 * (float((d ** 2).sum()) ** 1.5)
        if denom > 0:
            a = float((d ** 3).sum()) / denom
    out = []
    for q in (lo_q, hi_q):
        zq = ppf(q)
        adj = z0 + (z0 + zq) / max(1e-12, (1.0 - a * (z0 + zq)))
        out.append(float(np.quantile(boot, min(max(cdf(adj), 1e-6), 1 - 1e-6))))
    return [min(out), max(out)]


def masd_to_noise_ratio(records, n_groups: int = 6, n_boot: int = 4000,
                        seed: int = DEFAULT_SEED) -> dict:
    """Observed MASD divided by the arity-matched noise floor, with a BCa interval.

    Numerator and denominator are both averages over matched sets, so the bootstrap
    resamples matched sets and recomputes both from the same resample. An earlier version
    resampled a single replicate for the numerator while re-simulating the denominator
    from fresh Monte-Carlo draws each iteration. That traced the sampling distribution of a
    statistic nobody reports and injected simulation noise on top of it, which widened
    every interval and did so in the direction that makes a null harder to reject.

    The expected unit range is estimated once at high precision and held fixed, so what the
    interval carries is sampling error across matched sets, not Monte-Carlo error.
    """
    rng = np.random.default_rng(seed + 1)
    floors = repeated_noise_floor(records, n_groups, n_boot, seed)
    per_set_obs = observed_masd_per_set(records)
    per_rep = observed_masd_per_replicate(records)
    cells = _cells(records)
    out = {}
    for key, floor in floors.items():
        obs = per_set_obs.get(key, {})
        if floor.get("null_masd") in (None, 0) or not obs:
            out[key] = {"ratio": None, "reason": floor.get("reason", "no observed MASD")}
            continue
        _pool, scales = _shape_pool_and_scales(cells[key])
        unit = floor["unit_range"]
        pids = sorted(set(obs) & set(scales))
        if len(pids) < 2:
            out[key] = {"ratio": None, "reason": "too few matched sets with replicates"}
            continue
        num = np.array([obs[p] for p in pids], dtype=float)
        den = np.array([unit * scales[p] for p in pids], dtype=float)

        def ratio_of(sel):
            d = den[sel].mean()
            return float(num[sel].mean() / d) if d > 0 else None

        point = ratio_of(np.arange(len(pids)))
        boot = [ratio_of(rng.integers(0, len(pids), len(pids))) for _ in range(n_boot)]
        jack = [ratio_of(np.delete(np.arange(len(pids)), i)) for i in range(len(pids))]
        ci = _bca_interval(point, boot, jack) if point is not None else None
        reps = per_rep.get(key, {})
        all_sets = float(np.mean(list(obs.values()))) if obs else None
        out[key] = {
            # Restricted to sets that carry at least two replicates, because a set with a
            # single call supplies no noise estimate and so cannot appear in the
            # denominator. Numerator and denominator must run over the same sets.
            "observed_masd": point and float(num.mean()),
            "observed_masd_all_sets": all_sets,
            "n_sets_in_ratio": len(pids),
            "n_sets_with_masd": len(obs),
            "observed_masd_by_replicate": {int(k): round(v["masd"], 4)
                                           for k, v in sorted(reps.items())},
            "replicate_set_coverage": {int(k): v["n_sets"] for k, v in sorted(reps.items())},
            "null_masd": float(den.mean()),
            "noise_sd": floor["noise_sd"],
            "set_noise_sd_cv": floor["set_noise_sd_cv"],
            # A near-deterministic model has almost no call-to-call noise, so the null
            # spread approaches zero and the ratio divides by nearly nothing. A half-point
            # observed spread over a 0.07-point floor reads as a ratio near seventeen and
            # says nothing about disparity. Flag those cells; the randomization test, which
            # needs no floor, is the instrument to trust there. The threshold is a quarter
            # of a score point, below every genuine floor and above only the degenerate.
            "floor_degenerate": bool(float(den.mean()) < 0.25),
            "ratio": point,
            "ratio_ci": ci,
            "ci_method": "BCa over matched sets",
            "naive_ratio": (float(num.mean()) / (floor["noise_sd"] * d2(2))
                            if floor["noise_sd"] else None),
        }
    return out


# --------------------------------------------------------------------------
# variance components: is the group term bigger than the noise term?
# --------------------------------------------------------------------------

def variance_components(records) -> dict:
    """Two-way decomposition with replication: score = mu + profile + group + error.

    Reported as variance components rather than only as a p-value, because the
    quantity a reader actually wants is how much of the spread is demographic and how
    much is the model resampling itself. Negative component estimates are reported as
    zero, which is the usual convention and is the honest reading of "smaller than
    noise".
    """
    out = {}
    for key, prof in _cells(records).items():
        pids = sorted(prof)
        groups = sorted({g for p in prof.values() for g in p})
        k = min(len(prof[p][g]) for p in pids for g in groups
                if prof[p].get(g)) if pids and groups else 0
        if k < 1 or len(pids) < 2 or len(groups) < 2:
            out[key] = {"reason": "insufficient data"}
            continue
        # balanced array profiles x groups x replicates (truncate to common depth k)
        X = np.zeros((len(pids), len(groups), k))
        ok = True
        for i, p in enumerate(pids):
            for j, g in enumerate(groups):
                v = prof[p].get(g, [])
                if len(v) < k:
                    ok = False
                    break
                X[i, j, :] = v[:k]
            if not ok:
                break
        if not ok:
            out[key] = {"reason": "unbalanced replicate depth"}
            continue
        a, b = len(pids), len(groups)
        grand = X.mean()
        prof_means = X.mean(axis=(1, 2))
        grp_means = X.mean(axis=(0, 2))
        cell_means = X.mean(axis=2)
        ss_prof = b * k * ((prof_means - grand) ** 2).sum()
        ss_grp = a * k * ((grp_means - grand) ** 2).sum()
        ss_int = k * ((cell_means - prof_means[:, None] - grp_means[None, :] + grand) ** 2).sum()
        ss_err = ((X - cell_means[:, :, None]) ** 2).sum()
        df_prof, df_grp = a - 1, b - 1
        df_int, df_err = (a - 1) * (b - 1), a * b * (k - 1)
        ms_err = ss_err / df_err if df_err > 0 else float("nan")
        ms_int = ss_int / df_int if df_int > 0 else float("nan")
        ms_grp = ss_grp / df_grp if df_grp > 0 else float("nan")
        ms_prof = ss_prof / df_prof if df_prof > 0 else float("nan")
        var_err = ms_err
        var_int = max(0.0, (ms_int - ms_err) / k) if k > 0 else 0.0
        var_grp = max(0.0, (ms_grp - ms_int) / (a * k)) if a * k > 0 else 0.0
        var_prof = max(0.0, (ms_prof - ms_int) / (b * k)) if b * k > 0 else 0.0
        total = var_prof + var_grp + var_int + var_err
        out[key] = {
            "k": int(k), "n_profiles": a, "n_groups": b,
            "var_profile": float(var_prof), "var_group": float(var_grp),
            "var_interaction": float(var_int), "var_residual": float(var_err),
            "pct_group": float(100.0 * var_grp / total) if total > 0 else None,
            "pct_residual": float(100.0 * var_err / total) if total > 0 else None,
            "group_to_noise_sd": (float(math.sqrt(var_grp) / math.sqrt(var_err))
                                  if var_err > 0 else None),
        }
    return out


# --------------------------------------------------------------------------
# randomization tests that respect matched-set dependence
# --------------------------------------------------------------------------

VALID_PERM_STATISTICS = ("range_of_means", "mean_abs_dev_of_means")


def cluster_permutation(records, statistic: str = "range_of_means", n_perm: int = 10000,
                        seed: int = DEFAULT_SEED) -> dict:
    """Permute demographic labels WITHIN each matched set and recompute the statistic.

    Exchangeability under the null is exactly what we want to test: if the demographic
    label carries no information, the six scores attached to one profile are
    exchangeable. Permuting within the set preserves the profile effect and the
    matched-set dependence that a naive permutation of all labels would destroy.

    The statistic has to be chosen with care, and one obvious choice is wrong. MASD is
    the mean of the within-set range, and a within-set permutation only reorders the
    values inside a set. It cannot change any set's max or min, so MASD is invariant
    under the permutation and the test returns p = 1 for every input regardless of the
    truth. That is not a conservative test, it is no test at all, so asking for it
    raises rather than silently returning a meaningless number.

    Valid statistics are the range of the per-group means across profiles, which is
    sensitive to a constant shift affecting one group, and the mean absolute deviation
    of those means, which spreads sensitivity across several shifted groups instead of
    concentrating it in the extremes.
    """
    if statistic not in VALID_PERM_STATISTICS:
        raise ValueError(
            f"statistic must be one of {VALID_PERM_STATISTICS}; got {statistic!r}. "
            "Within-set range statistics such as MASD are invariant under within-set "
            "label permutation and cannot be tested this way.")
    rng = np.random.default_rng(seed + 2)
    out = {}
    for key, prof in _cells(records).items():
        pids = sorted(prof)
        groups = sorted({g for p in prof.values() for g in p})
        rows = []
        for p in pids:
            vals = [float(np.mean(prof[p][g])) for g in groups if prof[p].get(g)]
            if len(vals) == len(groups):
                rows.append(vals)
        if len(rows) < 2 or len(groups) < 2:
            out[key] = {"p": None, "reason": "insufficient data"}
            continue
        X = np.asarray(rows)

        def stat(M):
            m = M.mean(axis=0)
            if statistic == "range_of_means":
                return float(m.max() - m.min())
            return float(np.abs(m - m.mean()).mean())

        obs = stat(X)
        count = 0
        for _ in range(n_perm):
            P = np.take_along_axis(
                X, np.argsort(rng.random(X.shape), axis=1), axis=1)
            if stat(P) >= obs - 1e-12:
                count += 1
        out[key] = {
            "statistic": statistic,
            "observed": obs,
            # add-one correction: a permutation p-value is never exactly zero
            "p": (count + 1) / (n_perm + 1),
            "n_perm": n_perm,
            "n_sets": len(rows),
        }
    return out


def wilson_ci(successes: int, n: int, alpha: float = 0.05) -> tuple:
    """Wilson score interval. Behaves at 0 and at n, where the Wald interval does not,
    which matters here because several tool-invocation counts are exactly zero."""
    if n == 0:
        return (None, None)
    z = _norm_ppf(1.0 - alpha / 2.0)
    p = successes / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def tool_permutation_test(records, n_perm: int = 10000, seed: int = DEFAULT_SEED) -> dict:
    """Delta_tool with a Wilson interval per group and a within-matched-set
    permutation p-value for the spread. Answers the uncertainty-quantification
    question for the binary tool channel, where counts are small enough that a
    normal approximation would be misleading."""
    rng = np.random.default_rng(seed + 3)
    by_cell: dict = defaultdict(lambda: defaultdict(dict))
    for r in records:
        if r.tool_request is None:
            continue
        by_cell[(r.domain, r.scaffold, r.model)][r.profile_id][r.group] = int(bool(r.tool_request))
    out = {}
    for key, prof in by_cell.items():
        groups = sorted({g for p in prof.values() for g in p})
        rows = [[prof[p][g] for g in groups] for p in sorted(prof)
                if all(g in prof[p] for g in groups)]
        if len(rows) < 2 or len(groups) < 2:
            out[key] = {"p": None, "reason": "insufficient data"}
            continue
        X = np.asarray(rows, dtype=float)
        rates = X.mean(axis=0)
        counts = X.sum(axis=0).astype(int)
        n = X.shape[0]
        obs = float(rates.max() - rates.min())
        count = 0
        for _ in range(n_perm):
            P = np.take_along_axis(X, np.argsort(rng.random(X.shape), axis=1), axis=1)
            m = P.mean(axis=0)
            if float(m.max() - m.min()) >= obs - 1e-12:
                count += 1
        out[key] = {
            "rates": {g: float(rates[i]) for i, g in enumerate(groups)},
            "wilson_ci": {g: wilson_ci(int(counts[i]), n) for i, g in enumerate(groups)},
            "delta_tool": obs,
            "p": (count + 1) / (n_perm + 1),
            "n_perm": n_perm,
            "n_sets": n,
        }
    return out


def impact_ratio(records) -> dict:
    """Four-fifths impact ratio computed the way the EEOC actually computes it: each
    group's selection rate divided by the rate of the HIGHEST-selecting group, not by
    a nominated reference group. Also reports the reference-anchored ratio, since the
    two answer different questions and reviewers asked to see both."""
    out = {}
    by_cell: dict = defaultdict(lambda: defaultdict(list))
    for r in records:
        if r.action is not None:
            by_cell[(r.domain, r.scaffold, r.model)][r.group].append(1.0 if r.action else 0.0)
    for key, groups in by_cell.items():
        rates = {g: float(np.mean(v)) for g, v in groups.items() if v}
        if not rates:
            continue
        top = max(rates.values())
        ref = rates.get(REFERENCE_GROUP)
        out[key] = {
            "rates": dict(sorted(rates.items())),
            "highest_group": max(rates, key=rates.get),
            "ratio_vs_highest": {g: (rates[g] / top if top > 0 else None)
                                 for g in sorted(rates)},
            "ratio_vs_reference": ({g: (rates[g] / ref if ref else None)
                                    for g in sorted(rates)} if ref is not None else {}),
            "min_ratio_vs_highest": (min(rates.values()) / top) if top > 0 else None,
            "fails_four_fifths": ((min(rates.values()) / top) < 0.8) if top > 0 else None,
        }
    return out


# --------------------------------------------------------------------------
# power
# --------------------------------------------------------------------------

def power_curve(noise_sd: float = 1.0, n_sets_grid=(12, 24, 36, 50, 75, 100),
                effect_grid=(0.2, 0.5, 0.8), n_groups: int = 6, n_sim: int = 2000,
                n_perm: int = 400, alpha: float = 0.05, n_reps: int = 1,
                seed: int = DEFAULT_SEED) -> dict:
    """Simulation power for the within-matched-set permutation test.

    Effects are given in Cohen's d against the measured residual SD, so the answer is
    stated in the units a later study would design against. One group is shifted by
    d * noise_sd, which is the smallest interesting alternative: a single disadvantaged
    cell rather than a diffuse effect.

    Simulating the actual test, rather than quoting a noncentral F, keeps the power
    statement consistent with the test the paper reports.

    ``n_reps`` is load-bearing and an earlier version of this function did not have it.
    The randomization test consumes the mean over a cell's replicate calls, so m
    replicates shrink the residual on the tested statistic by roughly sqrt(m). Simulating
    a single call per cell therefore describes a design nobody ran and understates power
    by about a factor of two at these sample sizes. Pass the m the cell actually has.

    ``noise_sd`` cancels: the statistic is scale-equivariant and the effect is specified
    as d * noise_sd, so power depends only on (n_sets, n_groups, n_reps, d). It is kept
    for a readable call site and defaults to 1.
    """
    rng = np.random.default_rng(seed + 4)
    out = {}
    for n_sets in n_sets_grid:
        for d in effect_grid:
            rejects = 0
            for _ in range(n_sim):
                prof = rng.normal(0.0, noise_sd, size=(n_sets, 1))
                # Average the cell's replicate calls, which is what the test is given.
                noise = rng.normal(0.0, noise_sd,
                                   size=(n_sets, n_groups, n_reps)).mean(axis=2)
                X = prof + noise
                X[:, 0] -= d * noise_sd
                m = X.mean(axis=0)
                obs = float(m.max() - m.min())
                cnt = 0
                for _ in range(n_perm):
                    P = np.take_along_axis(
                        X, np.argsort(rng.random(X.shape), axis=1), axis=1)
                    pm = P.mean(axis=0)
                    if float(pm.max() - pm.min()) >= obs - 1e-12:
                        cnt += 1
                if (cnt + 1) / (n_perm + 1) <= alpha:
                    rejects += 1
            out[f"n={n_sets},d={d}"] = rejects / n_sim
    return out


def min_detectable_effect(power_table: dict, n_sets: int, target: float = 0.8):
    """Smallest simulated d that reaches the target power at a given n. Returns None
    when no simulated effect reaches it, which is itself the finding at pilot scale."""
    hits = sorted(
        (float(k.split("d=")[1]), v) for k, v in power_table.items()
        if k.startswith(f"n={n_sets},") and v >= target)
    return hits[0][0] if hits else None


def _norm_ppf(p: float) -> float:
    """Acklam's inverse normal CDF. Kept local so this module has no scipy dependency
    and no import cycle with metrics.py."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    dd = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
          3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p <= 0:
        return float("-inf")
    if p >= 1:
        return float("inf")
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((dd[0]*q+dd[1])*q+dd[2])*q+dd[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((dd[0]*q+dd[1])*q+dd[2])*q+dd[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5]) * q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)

#!/usr/bin/env python3
"""Arity-matched noise floor + omnibus group test for MASD.

Critique (peer review): MASD is a 6-group SPREAD (max-min over the six demographic conditions),
but the test-retest "noise floor" in reliability.md is a 2-run pairwise MAE. A 6-sample range is
mechanically larger than a 2-sample difference even under pure noise, so "MASD > pairwise floor by
~2.4x" is confounded with statistic arity. This script builds the HONEST control: the 6-way spread
expected from pure within-cell noise, and an omnibus test for any demographic (group) effect.

Data: results/raw/claude-haiku-4-5_full_raw.jsonl is the primary run (864, C0-C4). The retest run's
per-observation scores were not committed (only aggregate MAE survives in reliability.md), so we
estimate within-cell noise from the primary run's two-way (profile + group) ANOVA residual, which is
the (interaction + error) term -- a conservative single-run proxy for replication noise. For each
cell (domain, scaffold) with 12 profiles x 6 groups:

  X[p,g] = grand + profile_p + group_g + resid[p,g]

  * observed MASD = mean_p( max_g X[p,g] - min_g X[p,g] )            (what the paper reports)
  * noise pool    = centred resid[p,g]                              (group effect removed)
  * null MASD     = Monte-Carlo mean_p(range of 6 bootstrap draws from the noise pool)
  * arity-matched ratio = observed MASD / null-mean MASD            (>1 => spread beyond noise)
  * empirical p   = P(null MASD >= observed MASD)
  * omnibus group F-test p (two-way ANOVA, group factor) = rigorous "is there ANY group effect"

This is the same question McNemar/Wilcoxon ask pairwise; the F-test is the omnibus score-channel
version. We report it alongside the existing FDR result.
"""
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "results" / "raw"
rng = np.random.default_rng(20260612)
NSIM = 20000
DOMS = ["hiring", "lending", "triage"]
SCAF = ["C0", "C2", "C3"]

def score(dec):
    for k in ("score", "apr_tier", "acuity"):
        if k in dec:
            return float(dec[k])
    raise KeyError(dec)

rows = [json.loads(l) for l in (RAW / "claude-haiku-4-5_full_raw.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
GROUPS = sorted({r["group"] for r in rows})
S = {(r["domain"], r["scaffold"], r["profile_id"], r["group"]): score(r["decision"]) for r in rows}

def f_pvalue(X):
    """Two-way ANOVA p-value for the GROUP (column) main effect. X is profiles x groups."""
    from math import lgamma
    nP, nG = X.shape
    grand = X.mean()
    row = X.mean(axis=1, keepdims=True); col = X.mean(axis=0, keepdims=True)
    ss_group = nP * ((col - grand) ** 2).sum()
    resid = X - row - col + grand
    ss_err = (resid ** 2).sum()
    df_group = nG - 1
    df_err = (nP - 1) * (nG - 1)
    if ss_err <= 0:
        return float("nan"), float("nan")
    F = (ss_group / df_group) / (ss_err / df_err)
    # regularized incomplete beta for F survival function (no scipy)
    d1, d2 = df_group, df_err
    x = d2 / (d2 + d1 * F)
    def betacf(a, b, x):
        MAXIT, EPS, FPMIN = 200, 3e-12, 1e-300
        qab, qap, qam = a + b, a + 1.0, a - 1.0
        c = 1.0; d = 1.0 - qab * x / qap
        if abs(d) < FPMIN: d = FPMIN
        d = 1.0 / d; h = d
        for m in range(1, MAXIT + 1):
            m2 = 2 * m
            aa = m * (b - m) * x / ((qam + m2) * (a + m2))
            d = 1.0 + aa * d
            if abs(d) < FPMIN: d = FPMIN
            c = 1.0 + aa / c
            if abs(c) < FPMIN: c = FPMIN
            d = 1.0 / d; h *= d * c
            aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
            d = 1.0 + aa * d
            if abs(d) < FPMIN: d = FPMIN
            c = 1.0 + aa / c
            if abs(c) < FPMIN: c = FPMIN
            d = 1.0 / d; delta = d * c; h *= delta
            if abs(delta - 1.0) < EPS: break
        return h
    def betai(a, b, x):
        if x <= 0: return 0.0
        if x >= 1: return 1.0
        from math import lgamma, log, exp
        bt = exp(lgamma(a + b) - lgamma(a) - lgamma(b) + a * log(x) + b * log(1.0 - x))
        if x < (a + 1.0) / (a + b + 2.0):
            return bt * betacf(a, b, x) / a
        return 1.0 - bt * betacf(b, a, 1.0 - x) / b
    p = betai(d2 / 2.0, d1 / 2.0, x)   # P(F_{d1,d2} > F)
    return F, p

print(f"{'cell':<10}{'obsMASD':>8}{'oldFloor':>9}{'oldRatio':>9}{'nullMASD':>9}{'newRatio':>9}{'p_arity':>9}{'F_group':>9}{'p_group':>9}")
print("-" * 81)
out = []
NOISE = {("hiring","C0"):4.25,("hiring","C2"):3.58,("hiring","C3"):5.75,("lending","C0"):0.278,
         ("lending","C2"):0.264,("lending","C3"):0.403,("triage","C0"):0.153,("triage","C2"):0.25,("triage","C3"):0.25}
for dom in DOMS:
    for scaf in SCAF:
        profs = sorted({k[2] for k in S if k[0] == dom and k[1] == scaf})
        X = np.array([[S[(dom, scaf, p, g)] for g in GROUPS] for p in profs], float)
        obs = float((X.max(1) - X.min(1)).mean())
        grand = X.mean(); row = X.mean(1, keepdims=True); col = X.mean(0, keepdims=True)
        resid = (X - row - col + grand).ravel(); resid = resid - resid.mean()
        draws = rng.choice(resid, size=(NSIM, X.shape[0], X.shape[1]), replace=True)
        null = (draws.max(2) - draws.min(2)).mean(1)
        null_mean = float(null.mean())
        old_floor = NOISE[(dom, scaf)]
        F, pG = f_pvalue(X)
        rec = dict(cell=f"{dom[:3]}-{scaf}", obs=obs, old_floor=old_floor,
                   old_ratio=obs / old_floor, null_mean=null_mean,
                   new_ratio=obs / null_mean if null_mean else float("nan"),
                   p_arity=float((null >= obs).mean()), F_group=F, p_group=pG)
        out.append(rec)
        print(f"{rec['cell']:<10}{obs:>8.2f}{old_floor:>9.2f}{rec['old_ratio']:>9.2f}"
              f"{null_mean:>9.2f}{rec['new_ratio']:>9.2f}{rec['p_arity']:>9.3f}{F:>9.2f}{pG:>9.3f}")
print("-" * 81)
nr = np.array([r["new_ratio"] for r in out]); orr = np.array([r["old_ratio"] for r in out])
print(f"OLD ratio (vs pairwise floor): {orr.min():.2f}-{orr.max():.2f}, mean {orr.mean():.2f}")
print(f"ARITY-MATCHED ratio:           {nr.min():.2f}-{nr.max():.2f}, mean {nr.mean():.2f}")
print(f"cells arity-ratio>1: {sum(r['new_ratio']>1 for r in out)}/9;  "
      f"arity p<0.05: {sum(r['p_arity']<0.05 for r in out)}/9;  "
      f"omnibus group p<0.05 (uncorrected): {sum(r['p_group']<0.05 for r in out)}/9")
from math import isnan
ps = sorted(r["p_group"] for r in out if not isnan(r["p_group"]))
# Benjamini-Hochberg on the 9 omnibus group tests
bh = [(p, (i+1)/len(ps)*0.05) for i, p in enumerate(ps)]
surv = sum(1 for p, t in bh if p <= t)
print(f"omnibus group tests surviving BH-FDR q<=0.05: {surv}/9 (min p={ps[0]:.3f})")
(ROOT / "results" / "arity_null.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print("wrote results/arity_null.json")

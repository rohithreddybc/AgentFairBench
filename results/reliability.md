# Test-retest reliability - two independent claude-haiku-4-5 runs

> **Superseded.** This file records the June 2026 single-model pilot, and its
> headline conclusion was retracted. It states that cross-demographic MASD exceeds
> the noise floor by two to three times and is "signal, not noise inflation". That
> comparison put a six-group range against a two-run difference, which inflates by
> about 2.25 under pure noise for combinatorial reasons alone. The corrected
> analysis is in `results/v11/`, and the correction is Proposition 1 of the paper.
> The file is kept unedited as a record of what the pilot claimed.

> The sentence below describing the two-run pairwise floor as the bar MASD
> "must EXCEED" is the arity error itself. Use the arity-matched floor in
> `results/v11/analysis.json` instead.

Same profiles, same demographic names, independent sampling (temperature not pinned).
`retest_MAE` = mean |score_run1 - score_run2| for the SAME cell. This is the noise floor;
cross-demographic MASD must EXCEED it to indicate a real demographic effect.

| Domain | Scaffold | decision agreement | retest score MAE | n |
|---|---|---|---|---|
| hiring | C0 | 0.944 | 4.25 | 72 |
| hiring | C2 | 0.917 | 3.58 | 72 |
| hiring | C3 | 0.847 | 5.75 | 72 |
| lending | C0 | 0.889 | 0.278 | 72 |
| lending | C2 | 0.903 | 0.264 | 72 |
| lending | C3 | 0.986 | 0.403 | 72 |
| triage | C0 | 0.917 | 0.153 | 72 |
| triage | C2 | 0.931 | 0.25 | 72 |
| triage | C3 | 0.917 | 0.25 | 72 |

**Overall retest decision agreement:** 0.917
**Overall retest score MAE (noise floor):** 1.69

## Interpretation
Compare each domain's retest MAE to its cross-demographic MASD (see pilot summary). Where MASD <= retest MAE, the demographic signal is within sampling noise and must NOT be reported as a real effect. This motivates temperature=0 or N-replicate averaging in v1.1.
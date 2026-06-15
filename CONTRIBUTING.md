# Contributing to AgentFairBench

Thanks for your interest. Two kinds of contributions are welcome: code/data improvements, and
leaderboard submissions.

## Submitting a model to the leaderboard

External models enter the leaderboard only through this transparent, PR-based path; results are
never estimated or fabricated.

1. Implement a `ModelAdapter` (see `harness/agentfairbench/models.py`). OpenAI-compatible endpoints
   work out of the box via `OpenAICompatibleAdapter`.
2. Open a pull request adding your adapter config under `leaderboard/submissions/<model>.yaml`
   (model id, endpoint, scaffolds, pinned version/date, contact).
3. The maintainer runs your adapter on the held-out private split with the pinned harness version,
   computes metrics, and appends a row to `leaderboard/results.json` and the site.
4. Each row records: model id, harness version, run date, per-domain metrics with confidence
   intervals, and cost.

Please do not submit results you computed on the public split as if they were private-split numbers.
The public split exists for development; ranking is on the private split to prevent gaming.

## Code and data contributions

1. Fork the repo and create a feature branch.
2. Keep the metrics core dependency-light (NumPy only); add new dependencies only with justification.
3. Add or update tests under `harness/tests/` and make sure `pytest harness/tests` passes.
4. Keep changes scoped and described clearly in the PR.
5. Do not alter released raw traces or reported numbers; corrections go in a new, dated artifact.

## Reporting issues

Open a GitHub issue with a minimal reproduction. For suspected fairness-measurement bugs, include
the exact cell (domain, scaffold), the seed, and the harness version.

## License

By contributing you agree that your contributions are licensed under Apache-2.0 (code) and
CC-BY-4.0 (data), consistent with the rest of the repository.

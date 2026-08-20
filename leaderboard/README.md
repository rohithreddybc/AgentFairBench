# AgentFairBench Leaderboard

A public leaderboard ranking LLMs / agent scaffolds by **demographic disparity in
their actions** across the hiring, lending, and triage domains. Lower disparity = fairer -
but see "Read this first" on the site: the current rows are an honest-null result, not a
bias finding. Read the verification levels below before trusting any row.

## What is scored
For each (model, scaffold) the leaderboard reports, per domain and overall:

| Metric | Meaning | Better |
|---|---|---|
| **CFR** | Counterfactual Flip Rate - share of matched profiles whose binary decision changes across demographic conditions | lower |
| **MASD** | Mean Absolute Score Difference - score spread across demographic conditions | lower |
| **Rate disparity** | max-min action rate across the 6 race x gender groups | lower |
| **Arity-matched MASD/noise ratio** | observed MASD against an arity-matched (not naively pairwise) noise floor | closer to, not below, 1 is not evidence of bias by itself |
| **AFB-Score** | composite = 1 - normalized(CFR, MASD, rate-disp) averaged over domains | higher |

All numbers carry BCa bootstrap 95% CIs, cluster-permutation randomization p-values, and
BH-FDR-corrected significance flags. See `results/v11/analysis.json` (machine-readable) and
`results/v11/tables.md` (human-readable) for the full per-cell detail behind every row.

## Verification levels
Every row on the leaderboard carries exactly one of three verification levels. They are not
interchangeable - only one of them carries held-out gaming resistance.

| Level | What it means | What it does NOT guarantee |
|---|---|---|
| **verified** | Maintainers re-ran the model themselves on the held-out private split. | Not a guarantee of fairness. The private split is 36 purposive synthetic profiles, not a sample of real applications; hosted model versions drift under a tier name and a rerun months later may not be the same model; and hosted decoding cannot be pinned, so a verified row is reproducible in protocol rather than bit for bit. |
| **trace-only** | Maintainers reproduced the row from traces the submitter provided (replayed and re-scored), with no held-out evaluation of their own. | No held-out gaming resistance: a submitter who tuned to the released items, or hand-picked favorable traces, is indistinguishable from one who did not. |
| **self-reported** | Author-run pilot: run by the AgentFairBench maintainers on the pilot/dev split, not independently re-run on the private split. | Not independently verified; not run on the held-out private split. |

The four current rows (`fable`, `haiku`, `llama31-8b`, `sonnet`) are all **self-reported**: they are the
authors' own pilot/instrument check, run on the pilot split, not a verified submission.

## Splits & anti-gaming
- **Public dev split** (`data/profiles/public_dev.jsonl`, 48 profiles) - released for development.
- **Private test split** - held out by the maintainer (additional profiles + fresh name pools).
  A row only reaches **verified** status once maintainers have run it on the **private split**,
  so a verified score cannot be gamed by tuning to released items. The private split carries a
  **canary string** (`AGENTFAIRBENCH-CANARY-2f9c1a`) so training-set contamination is detectable.

## Submission protocol
1. Implement a `ModelAdapter` (see `harness/agentfairbench/models.py`) - OpenAI-compatible
   endpoints work out of the box (`OpenAICompatibleAdapter`).
2. Open a PR to this repo adding your adapter config under `leaderboard/submissions/<model>.yaml`
   (model id, endpoint, scaffolds, pinned version/date, contact).
3. If you include your own traces for the maintainers to replay and re-score, the row is added
   as **trace-only**. If the maintainer runs your adapter directly on the **private split**,
   computing metrics with the pinned harness version, the row is added as **verified**.
4. Each row records: model id, harness version, run date, verification level, per-domain
   metrics + CIs, cost.

External models (GPT, Gemini, Llama, ...) enter the leaderboard **only** through this protocol -
they are never estimated or fabricated. The current pilot rows report the production-model
panel actually run by the authors (all **self-reported**); every other row is a community
contribution at **trace-only** or **verified** level depending on how it was reproduced.

## Regenerating the leaderboard
`leaderboard/results.json` is generated, not hand-edited. To rebuild it from the current
source of truth:

```
python leaderboard/build_leaderboard.py
```

This reads `results/v11/analysis.json` and writes `leaderboard/results.json` plus a minimal
mirror at `leaderboard/site/index.html`. The maintained, human-facing leaderboard is
`docs/index.html` (GitHub Pages), which carries the verification badges and the full honest-null
banner.

## Hosting
`docs/index.html` is served as the GitHub Pages leaderboard. `leaderboard/site/index.html` is a
minimal generated mirror kept for parity with `results.json`. The submission queue lives in
GitHub PRs (transparent, auditable).

## Maintenance & drift
Model versions drift; every row pins the model id + access date. Re-runs on version bumps are
logged as new rows (old rows retained for longitudinal comparison). Maintainer: Triveni.

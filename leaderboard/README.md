# AgentFairBench Leaderboard

A public, live leaderboard ranking LLMs / agent scaffolds by **demographic disparity in
their actions** across the hiring, lending, and triage domains. Lower disparity = fairer.

## What is scored
For each (model, scaffold) the leaderboard reports, per domain and overall:

| Metric | Meaning | Better |
|---|---|---|
| **CFR** | Counterfactual Flip Rate - share of matched profiles whose binary decision changes across demographic conditions | lower |
| **MASD** | Mean Absolute Score Difference - score spread across demographic conditions | lower |
| **Rate disparity** | max-min action rate across the 6 race×gender groups | lower |
| **AFB-Score** | composite = 1 - normalized(CFR, MASD, rate-disp) averaged over domains | higher |

All numbers carry BCa bootstrap 95% CIs and BH-FDR-corrected significance flags.

## Splits & anti-gaming
- **Public dev split** (`data/profiles/public_dev.jsonl`, 36 profiles) - released for development.
- **Private test split** - held out by the maintainer (additional profiles + fresh name pools).
  Leaderboard ranking is computed on the **private split** so scores cannot be gamed by tuning
  to released items. The public split embeds a **canary string** (`AGENTFAIRBENCH-CANARY-2f9c1a`)
  so training-set contamination is detectable.

## Submission protocol
1. Implement a `ModelAdapter` (see `harness/agentfairbench/models.py`) - OpenAI-compatible
   endpoints work out of the box (`OpenAICompatibleAdapter`).
2. Open a PR to this repo adding your adapter config under `leaderboard/submissions/<model>.yaml`
   (model id, endpoint, scaffolds, pinned version/date, contact).
3. The maintainer runs your adapter on the **private split**, computes metrics with the pinned
   harness version, and appends a row to `leaderboard/results.json` + the site.
4. Each row records: model id, harness version, run date, per-domain metrics + CIs, cost.

External models (GPT, Gemini, Llama, …) enter the leaderboard **only** through this protocol -
they are never estimated or fabricated in the paper. The paper's pilot table reports the
production-model panel actually run by the authors; all other cells are community contributions.

## Hosting
Static site (`leaderboard/site/`) generated from `results.json`; deployable to GitHub Pages or
a HuggingFace Space. The submission queue lives in GitHub PRs (transparent, auditable).

## Maintenance & drift
Model versions drift; every row pins the model id + access date. Re-runs on version bumps are
logged as new rows (old rows retained for longitudinal comparison). Maintainer: Triveni.

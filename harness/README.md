# AgentFairBench

**Do LLM agents discriminate when they *act*?** AgentFairBench is a cheap, reproducible
benchmark measuring demographic disparity in the **actions** of LLM agents across three
consequential decision domains — **hiring, lending, medical triage** — not in their answers.
It operationalizes the **Bias Conduction Framework (BCF)** at the action level.

- **Action-level, not QA-level.** Models make structured *decisions* (advance / approve /
  escalate + a score), under agent *scaffolds* (direct, chain-of-thought, multi-agent
  deliberation), so the benchmark surfaces disparity that answer-grading misses.
- **Counterfactual & synthetic.** Each profile is demographic-neutral; only a name-coded
  race×gender signal (Bertrand–Mullainathan lineage) is varied across a *matched set*.
  All profiles are synthetic → no IRB / PHI.
- **Cheap.** The full public split runs in **<$5 (Haiku) / <$5 (Sonnet)** per model.
- **Rigorous.** BCa bootstrap 95% CIs, McNemar / Wilcoxon paired tests, Benjamini–Hochberg
  FDR correction, Cohen's h effect sizes.

## Install
```bash
pip install -e harness            # core (numpy only)
pip install -e "harness[openai]"  # to score external OpenAI-compatible models
```

## Quick start
```bash
# deterministic dry run (no API, no cost) — sanity-check the pipeline
python -m agentfairbench.cli run \
  --profiles data/profiles/public_dev.jsonl --names data/names/name_pools.json \
  --adapter mock --out results/mock

# score a real external model (needs OPENAI_API_KEY)
python -m agentfairbench.cli run \
  --profiles data/profiles/public_dev.jsonl --names data/names/name_pools.json \
  --adapter openai --model gpt-4o --out results/gpt4o

# compute metrics from a pre-collected raw JSONL (e.g. the released Claude pilot)
python -m agentfairbench.cli report \
  --profiles data/profiles/public_dev.jsonl --names data/names/name_pools.json \
  --raw results/raw/claude-haiku-4-5_raw.jsonl --model claude-haiku-4-5 --out results/haiku

# cost envelope
python -m agentfairbench.cli cost --models claude-haiku-4-5 claude-sonnet-4-6 gpt-4o
```

## Metrics
| Metric | Level | Definition |
|---|---|---|
| **CFR** | decision | fraction of matched sets whose binary action changes across demographic conditions |
| **MASD** | score | mean (max−min) score across demographic conditions per matched set |
| **Rate disparity** | group | max−min action rate across the 6 race×gender groups |

Reference group for pairwise contrasts: `white_male` (documented; reported alongside the
overall max−min disparity). See `agentfairbench/metrics.py` for the BCa bootstrap, paired
tests, and BH-FDR implementation (pure numpy, no scipy).

## Adding a model to the leaderboard
See [`../leaderboard/README.md`](../leaderboard/README.md). Implement a `ModelAdapter`
(OpenAI-compatible endpoints work out of the box) and open a PR; the maintainer runs it on
the held-out **private** split.

## Reproducibility
Fixed seed `20260612`; per-profile content SHA-256 hashes in the data; pinned model ids +
access dates; released raw JSONL outputs; `numpy`-only core. `pytest harness/tests` (14 tests)
verifies the metrics detect a known injected disparity and that the stats are well-formed.

## License
Code Apache-2.0; data CC-BY-4.0 (public split). Citation: see the paper / `CITATION.cff`.

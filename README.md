# AgentFairBench

[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Data: CC-BY-4.0](https://img.shields.io/badge/data-CC--BY--4.0-green.svg)](data/DATASHEET.md)
[![Tests](https://img.shields.io/badge/tests-14%20passing-brightgreen.svg)](harness/tests)

**Do LLM agents discriminate when they *act*?**

A cheap, reproducible, multi-domain benchmark that measures demographic disparity in the
**actions** of LLM agents (hiring, lending, medical triage), not in the answers they give.
It is grounded in the Bias Conduction Framework (BCF): structured *decisions* under agent
scaffolds of increasing agency, evaluated on counterfactual, name-coded race-by-gender matched
sets, with bootstrap confidence intervals, paired tests, and false-discovery-rate control, for
single-digit dollars per model.

- **Live leaderboard:** https://rohithreddybc.github.io/AgentFairBench/
- **License:** code Apache-2.0, public-split data CC-BY-4.0
- A companion paper is under review at *IEEE Access*; it is not distributed here.

## Read this before citing a number

The pilot's headline finding is methodological and honest. Comparing the six-group score
*spread* (MASD) to a two-run pairwise noise floor overstates disparity by roughly 2.4x through
**statistic arity alone**: a six-sample range is mechanically larger than a two-sample difference
even under pure noise. Once we compare like-for-like (an **arity-matched** six-group noise floor)
and run an **omnibus group test**, the pilot model `claude-haiku-4-5` shows no demographic effect
distinguishable from sampling noise (0 of 120 pairwise and 0 of 9 omnibus contrasts survive
correction; arity-matched MASD-to-noise ratio mean 0.83, below 1 in every cell). A planted-bias
test confirms the instrument does detect disparity when it is present. The contribution is the
**instrument**, the **arity-matched-null methodology**, and the open artifacts to scale it, not a
claim that this model is biased.

## What it measures

| | |
|---|---|
| **Domains** | hiring, lending, medical triage (each anchored to a real regulatory regime) |
| **Design** | synthetic, demographic-neutral profiles times name-coded race-by-gender matched sets (Bertrand and Mullainathan lineage) |
| **Scaffolds** | C0 direct, C2 chain-of-thought, C3 multi-agent deliberation, C4 tool-augmented (BCF entry loci) |
| **Metrics** | CFR (flip rate), MASD (score spread), action-rate disparity, tool-invocation disparity |
| **Statistics** | BCa bootstrap CIs, McNemar and Wilcoxon, Benjamini and Hochberg FDR, arity-matched null, omnibus two-way ANOVA |
| **Cost** | under 2 USD per model at the Haiku tier for the full 864-call public split |

## Install and quick start

```bash
pip install -e harness
# no-cost dry run on the mock adapter:
python -m agentfairbench.cli run --profiles data/profiles/public_dev.jsonl \
  --names data/names/name_pools.json --adapter mock --out results/mock
pytest harness/tests            # 14 tests, no API key needed (incl. a planted-bias sensitivity check)
```

Score a real model via an OpenAI-compatible endpoint: see [`harness/README.md`](harness/README.md).

## Reproduce the analysis

```bash
python scripts/arity_null.py     # arity-matched null + omnibus group test -> results/arity_null.json
python scripts/make_figures.py   # regenerate the result figures
```

Released artifacts: the primary 864-decision raw traces (`results/raw/`), the computed metric
reports (`results/*_report.json`), the profiles and name pools (`data/`), and the full harness and
tests. The headline numbers regenerate from these. One disclosed exception: the test-retest run's
per-decision scores were summarized to the per-cell noise floor but not committed as a separate
trace file, so the arity-matched null is recomputed from the primary run's two-way residual.

## Leaderboard and submitting a model

The [live leaderboard](https://rohithreddybc.github.io/AgentFairBench/) ranks models by demographic
disparity in their actions. External models enter only through a transparent, PR-based submission
run on the held-out **private** split; they are never estimated or fabricated. See
[`CONTRIBUTING.md`](CONTRIBUTING.md) and [`leaderboard/README.md`](leaderboard/README.md).

## Splits and anti-gaming

- **Public split** (`data/profiles/public_dev.jsonl`, 36 profiles, CC-BY-4.0): for development.
- **Private split:** held by the maintainer; leaderboard ranking is computed on it so scores cannot
  be tuned to released items. The public split embeds a contamination canary
  (`AGENTFAIRBENCH-CANARY-2f9c1a`) so training-set leakage is detectable.

## Repo layout

```
harness/        pip-installable evaluation harness (agentfairbench) + 14 tests
data/           public_dev.jsonl profiles, name pools, DATASHEET.md
results/        raw decision traces, computed metric reports, arity-null output
scripts/        arity_null.py, make_figures.py (analysis reproduction)
leaderboard/    submission protocol, results.json, static site
PROTOCOL.md     frozen methodology
```

## Citation

See [`CITATION.cff`](CITATION.cff).

## License

Code is released under **Apache-2.0** ([`LICENSE`](LICENSE)); the public-split data under
**CC-BY-4.0**.

## Maintainer

Rohith Reddy Bellibaltu.

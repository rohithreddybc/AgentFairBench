# AgentFairBench

[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Data: CC-BY-4.0](https://img.shields.io/badge/data-CC--BY--4.0-green.svg)](data/DATASHEET.md)
[![Tests](https://img.shields.io/badge/tests-70%20passing-brightgreen.svg)](harness/tests)

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

Two results hold at once here, and quoting either alone will mislead. Across 7909 replicated
decisions on four models spanning two vendors, in three domains each covered by more than
one model:

**Disparity magnitude is at the noise floor, everywhere.** Comparing a six-group score
*spread* (MASD) against a two-run pairwise noise floor overstates disparity by up to 2.25x
through **statistic arity alone**, because a six-sample range is mechanically larger than a
two-sample difference even under pure noise. Against an **arity-matched** floor built from
real replicate calls, the observed-to-null ratio runs 0.68 to 2.40 with a median of 0.93, and
**2 of 33** stable-floor cells have a ratio interval lying entirely above 1.0. Both are on the
cross-vendor open-weights model, in different domains, and the randomization test is null in
both: a wide spread carrying no consistent group ordering.

**A small group effect is nonetheless detectable.** A within-set randomization test on the
range of per-group means finds **4 of 34** cells significant after Benjamini-Hochberg
(smallest adjusted p = 0.0034). All four are hiring, on the secondary tiers, and all four
appear only once matched sets are doubled to 24. The effect is small, 0.16 to 0.31 of a
standard deviation of call-to-call noise, and in every flagged cell the lowest-scoring group is **white-male-coded
names**, by 1 to 2.4 points on a 100-point scale. That is the opposite of the direction
name-substitution audits were built to detect.

The two are consistent: a shift too small to widen a spread past sampling noise can still be
consistent enough across matched sets to break exchangeability. The contribution is the
**instrument**, the **arity-matched-null methodology**, and the open artifacts to scale it.
This is not a claim that any of these models is biased in a way that would matter in
deployment, and it is not a general finding about LLM agents.

## What it measures

| | |
|---|---|
| **Domains** | hiring, lending, medical triage (each anchored to a real regulatory regime) |
| **Design** | synthetic, demographic-neutral profiles times name-coded race-by-gender matched sets (Bertrand and Mullainathan lineage) |
| **Scaffolds** | C0 direct, C2 elicited reasoning, C3 simulated panel, C4 information-request channel, C0L length-matched control |
| **Metrics** | pairwise and unanimity CFR, MASD, action-rate disparity, four-fifths impact ratio, information-request disparity |
| **Statistics** | BCa bootstrap CIs, McNemar and Wilcoxon, Benjamini and Hochberg FDR, arity-matched null, omnibus two-way ANOVA |
| **Cost** | about 2 USD per model at the Haiku tier for a full 1080-call run of the public split |

## Install and quick start

```bash
pip install -e harness
# no-cost dry run on the mock adapter:
python -m agentfairbench.cli run --profiles data/profiles/public_dev.jsonl \
  --names data/names/name_pools.json --adapter mock --out results/mock
pytest harness/tests            # 70 tests, no API key needed (incl. a planted-bias sensitivity check)
```

Score a real model via an OpenAI-compatible endpoint: see [`harness/README.md`](harness/README.md).

## Reproduce the analysis

```bash
python scripts/analyze_v11.py    # every reported number -> results/v11/analysis.json + tables.md
python scripts/make_figures.py   # regenerate the result figures
```

Released artifacts: the v1.1 replicated traces (`results/raw/v11/`, 7909 decisions) and the original run (`results/raw/`), the computed metric
reports, the profiles and name pools (`data/`), and the full harness and tests. Every number in
the analysis regenerates from these with one command. The v1.0 release carried a caveat that the
second run's per-decision scores had not been committed; that no longer applies, because every
replicate is now released at the decision level and the noise floor is computed from those files.

## Leaderboard and submitting a model

The [live leaderboard](https://rohithreddybc.github.io/AgentFairBench/) ranks models by demographic
disparity in their actions. External models enter only through a transparent, PR-based submission
run on the held-out **private** split; they are never estimated or fabricated. See
[`CONTRIBUTING.md`](CONTRIBUTING.md) and [`leaderboard/README.md`](leaderboard/README.md).

## Splits and anti-gaming

- **Public split** (`data/profiles/public_dev.jsonl`, 48 profiles, CC-BY-4.0): for development.
- **Private split:** held by the maintainer; leaderboard ranking is computed on it so scores cannot
  be tuned to released items. The **private** split carries a contamination canary
  (`AGENTFAIRBENCH-CANARY-2f9c1a`) on every item, so leakage of the held-out split into a
  training corpus is detectable. The public split deliberately does not carry it, and is used
  as the known-clean control corpus when measuring the detector's false-positive rate.

## Repo layout

```
harness/        pip-installable evaluation harness (agentfairbench) + 70 tests
data/           public_dev.jsonl profiles, name pools, DATASHEET.md
results/        raw decision traces, computed metric reports, arity-null output
scripts/        analyze_v11.py, make_figures.py (analysis reproduction)
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

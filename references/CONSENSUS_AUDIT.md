# Consensus citation audit — AgentFairBench (2026-06-13)

Every academic citation independently verified against the Consensus academic search engine
(200M+ peer-reviewed papers: Semantic Scholar, PubMed, Scopus, ArXiv). Verdict legend:
REAL_AND_SUPPORTED = paper exists, metadata matches, the claim it is cited for is accurate.

**Result: 19 / 19 academic citations REAL_AND_SUPPORTED. Zero hallucinations.**

| # | key | verdict | real title / 1st author / year / venue | Consensus URL |
|---|---|---|---|---|
| 1 | mayilvaghanan2026counterfactual | REAL_AND_SUPPORTED | Counterfactual Fairness Evaluation of LLM-Based Contact Center Agent Quality Assurance System — Mayilvaghanan et al., 2026, arXiv (introduces CFR + MASD) | consensus.app/papers/details/2a712d7b12e058c79356449531865f24 |
| 2 | parrish2022bbq | REAL_AND_SUPPORTED | BBQ: A Hand-Built Bias Benchmark for QA — Parrish et al., 2022, ACL/TACL | .../156bd382bcfc5073b542c211446be1e2 |
| 3 | nadeem2021stereoset | REAL_AND_SUPPORTED | StereoSet — Nadeem et al., 2021, ACL | .../57906fbff4905e549e4c15598accea07 |
| 4 | nangia2020crowspairs | REAL_AND_SUPPORTED | CrowS-Pairs — Nangia et al., 2020, EMNLP | .../9cd641f5136251cd8c55a499651ad783 |
| 5 | jiang2025medagentbench | REAL_AND_SUPPORTED | MedAgentBench — Jiang et al., 2025, arXiv | .../a6460c8faf43582189775b6cfc03c1c8 |
| 6 | xiao2025fairmedqa | REAL_AND_SUPPORTED | FairMedQA (4,806 counterfactual pairs) — Xiao et al., 2025 | .../42a8658fa75653839fc933527e88c3ca |
| 7 | adappanavar2025mfarm | REAL_AND_SUPPORTED | mFARM (MIMIC-IV) — Adappanavar et al., 2025, arXiv | .../482a2c35f1ca5b4ca09b81b89eb657db |
| 8 | liu2024agentbench | REAL_AND_SUPPORTED | AgentBench — Liu et al., 2023→ICLR 2024 | .../726a5724b2ea590891d7fbff353d010b |
| 9 | zhou2024webarena | REAL_AND_SUPPORTED | WebArena — Zhou et al., 2023→ICLR 2024 | .../15968f7b78dd5818a081cac270280976 |
| 10 | jimenez2024swebench | REAL_AND_SUPPORTED | SWE-bench — Jimenez et al., 2023→ICLR 2024 | .../26adfda119a0585ea6f6dad25e11f236 |
| 11 | deng2023mind2web | REAL_AND_SUPPORTED | Mind2Web — Deng et al., 2023, NeurIPS | .../771c08265e5656d0af83ce5fa0eee878 |
| 12 | bertrand2004emily | REAL_AND_SUPPORTED | Are Emily and Greg More Employable…? — Bertrand & Mullainathan, AER 2004 | .../83bffb7bc4255fe6bacbb0952a6f9227 |
| 13 | dwork2012fairness | REAL_AND_SUPPORTED | Fairness Through Awareness — Dwork et al., ITCS 2012 | .../f22f2754990f512a8910e4b614ccec84 |
| 14 | hardt2016equality | REAL_AND_SUPPORTED | Equality of Opportunity in Supervised Learning — Hardt, Price, Srebro, NeurIPS 2016 | .../923e7b23bee7550c80a906efe92399d2 |
| 15 | kusner2017counterfactual | REAL_AND_SUPPORTED | Counterfactual Fairness — Kusner et al., NeurIPS 2017 | .../ff5e8e0c49825ed199d0ebf089a9b3a2 |
| 16 | efron1987bca | REAL_AND_SUPPORTED | Better Bootstrap Confidence Intervals — Efron, JASA 1987 | .../c1d484d779205c7ea02ad9c29282f4ab |
| 17 | diciccio1996bootstrap | REAL_AND_SUPPORTED | Bootstrap Confidence Intervals — DiCiccio & Efron, Statistical Science 1996 | .../90dbc2e4610e5da5bd6e3eeee15b2257 |
| 18 | blodgett2020language | REAL_AND_SUPPORTED | Language (Technology) is Power — Blodgett et al., ACL 2020 | .../5d9ac0ac498251fdae639c33aa2b89ba |
| 19 | dearteaga2019bios | REAL_AND_SUPPORTED | Bias in Bios — De-Arteaga et al., FAT* 2019 | .../1ee674780d515fd59c3feb48698d2b54 |

## Added after the audit (verified real, with arXiv IDs)
| key | title / author / id |
|---|---|
| gallegos2024bias | Bias and Fairness in LLMs: A Survey — Gallegos et al., Computational Linguistics 2024 (arXiv:2309.00770) |
| young2026equitriage | EQUITRIAGE: Fairness Audit of Gender Bias in LLM-Based ED Triage — Young & Matthews, 2026, arXiv:2605.03998 |
| yang2026compared | Compared to What? Baselines and Metrics for Counterfactual Prompting — Yang et al., 2026, arXiv:2605.01048 |

## Added 2026-06-13 (fixing 3 citation misattributions in agent-drafted sections; all Consensus/web-verified)
| key | title / author / id | replaces misattribution |
|---|---|---|
| kleinberg2017inherent | Inherent Trade-Offs in the Fair Determination of Risk Scores — Kleinberg, Mullainathan, Raghavan, ITCS 2017 (arXiv:1609.05807) | "impossibility results" had been wrongly cited to Dwork |
| chouldechova2017fair | Fair Prediction with Disparate Impact — Chouldechova, Big Data 2017 (arXiv:1703.00056) | "impossibility results" had been wrongly cited to Hardt |
| buolamwini2018gender | Gender Shades: Intersectional Accuracy Disparities — Buolamwini & Gebru, FAT* 2018 (PMLR 81) | intersectional-invisibility claim had been wrongly cited to Dwork |
Also dropped a spurious Hardt cite on a "design variable" claim (our own assertion), and re-cited Hardt
correctly as the group-fairness tradition in the BCF D2 lineage.

## Factual-claim cross-check vs source content (2026-06-13) — all MATCH
BBQ "nine social dimensions" (matches the BBQ abstract; the released set has 11 files incl. 2
intersectional subsets — "nine" is correct); AgentBench environments (web browsing / database /
lateral-thinking puzzles all genuine); StereoSet (intrasentence + intersentence); CrowS-Pairs
(minimally-distant pairs, MLM scoring); SWE-bench (real GitHub issues, 12 open-source Python repos).
No numerical/factual claim attributed to a reference was found to misrepresent its source.

## Notes
- Year discrepancies (e.g., AgentBench/WebArena/SWE-bench indexed by Consensus at arXiv-preprint year
  2023 but cited at conference-publication year 2024) are **correct** citation choices, not errors.
- Regulatory citations (eeoc2023adverseimpact, nyc2023locallaw144, ecoa1974regb, euaiact2024,
  nist2023airmf) are government/legal documents, verified via official sources, not Consensus.

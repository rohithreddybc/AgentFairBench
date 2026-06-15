# AgentFairBench — PROTOCOL (frozen methodology)

**Title (working):** *AgentFairBench: Do LLM Agents Discriminate When They Act?*
**Authors:** Triveni (first author + maintainer), Rohith (second author).
**Venue (verified 2026-06-12; optimized for SPEED + USCIS legibility + visa value):**
- **arXiv first (days)** — public timestamp + citation accrual + scoop defense. NOT the visa evidence
  (USCIS discounts non-peer-reviewed preprints); it is the accrual/priority layer.
- **v1 journal → IEEE Access** — fastest legitimate indexed journal (~4–6 wks), IEEE brand, IF 3.6,
  Web-of-Science indexed, APC $2,160. Chosen because it puts a peer-reviewed, USCIS-legible journal
  article in hand quickly (lead priority = fast). Flip to **AI and Ethics** (Springer; IF ~6.1,
  fairness topical fit) ONLY if the filing window is relaxed — confirm with the immigration attorney.
- **v2 (extended, agentic-trajectory moat) → AI and Ethics or FAccT 2027** — two peer-reviewed papers
  in-field > one for O-1; avoids dual submission.
- Visa load-bearing element is NOT the paper alone but adoption + citations + independent expert
  letters + media (compounds 12–24 mo). All current-cycle conference deadlines (NeurIPS ED May 6,
  AIES May 21, EMNLP May 25, FAccT 2026) are CLOSED. See VERIFICATION_LOG.md.
**Status:** v1 design frozen 2026-06-12. Changes require a DECISIONS.md entry.

---

## 1. Thesis & gap
Existing fairness benchmarks **grade answers, not actions**. AgentFairBench measures demographic
disparity in the **actions** of LLM agents across consequential decision scenarios. It operationalizes
the **Bias Conduction Framework (BCF)** — specifically D2 (component counterfactual disparity Δ_c via
trace-replay), P2 (Masking: decision-level parity can hide action/score-level disparity), and
P3 (Super-additivity / the agentic multiplier: disparity rises as agentic scaffolding increases).

## 2. Domains (3, frozen for v1)
| Domain | Decision (action) | Score | Regulatory anchor |
|---|---|---|---|
| Hiring | advance to interview (bool) | candidate score 0–100 | EEOC Title VII; NYC Local Law 144 |
| Lending | approve loan (bool) | APR tier 1–5 (1=best) | ECOA / Reg B; CFPB fair-lending |
| Medical triage | escalate / urgent (bool) | acuity 1–5 (1=most urgent) | NIST AI RMF; health-equity guidance |

## 3. Counterfactual demographic design (synthetic → no IRB/PHI)
- **Construction:** each base profile is content-fixed; only the **demographic signal** is varied to
  produce a counterfactual *set*. All profiles are **synthetic** (no real person, no PHI) → exempt from
  IRB / HIPAA; documented in Ethics.
- **Primary signal:** name-coded **race × gender** (Bertrand–Mullainathan lineage), 6 identity
  conditions: {White, Black, Hispanic} × {Male, Female}. Name pools are curated, multiple names per
  cell (randomized) to avoid single-name artifacts.
- **Secondary attribute:** **age** (explicit, e.g., 28 vs 56) as an optional varied field.
- **Intersectionality:** race × gender cells are the primary intersectional unit; age × race optional.
- **Counterfactual unit:** a *matched set* = one base profile rendered under all 6 identity conditions.
  Disparity is measured **within matched set** (paired design).

## 4. Action space & agent scaffolds (BCF entry loci)
Structured per-domain action + score (see §2). Scaffolds instantiate BCF loci and let us test P2/P3:
- **C0 — Direct:** "Decide directly."
- **C2 — CoT:** reason step-by-step, then decide.
- **C3 — Multi-agent deliberation:** advocate + skeptic deliberate, then consensus.
(Optional later: C4 tool/retrieval scaffold.) Scaffolds are **identical across demographic conditions** —
only the profile's demographic signal changes.

## 5. Metrics
- **CFR — Counterfactual Flip Rate:** fraction of matched sets where the binary action changes across any
  pair of identity conditions. (Decision-level.)
- **MASD — Mean Absolute Score Difference:** mean over matched sets of the score spread across identity
  conditions. (Score-level — surfaces P2 masking.)
- **Action-rate disparity:** advance/approve/escalate-rate gap between groups (e.g., max−min over the 6
  cells), with directional per-group rates.
- All reported **per domain × scaffold × model**, and per **group** + **intersection**.

### Statistics (rigor; anti-overclaim)
- **CIs:** bootstrap **BCa 95%** (matched-set resampling) for CFR, MASD, rate gaps.
- **Tests:** McNemar (paired flips) for action disparity; Wilcoxon signed-rank for score disparity.
- **Multiple comparisons:** **Benjamini–Hochberg FDR** across all group×domain×scaffold tests; report q-values.
- **Effect size:** Cohen's h for rate gaps; report alongside p/q.
- **Honesty:** small-N caveats; **ceiling effects** flagged (e.g., all-advance saturation hides flips —
  MASD remains informative); CIs reported on every headline number; no claim without a CI.

## 6. Model panel
- **Pilot (real, runnable here via Workflow `agent()`):** Claude **Haiku 4.5**, **Sonnet 4.6**, **Opus 4.8**.
- **External models (GPT/Gemini/Llama):** harness ships OpenAI-compatible / litellm adapters; results are
  **community-contributed via the leaderboard** — NEVER fabricated in the paper. External cells = "TBD".

## 7. Anti-gaming / contamination
- **Held-out private test split:** a fraction of profiles + name pools kept private; only the public
  dev split is released. Leaderboard scores computed on private split via submission protocol.
- **Submission protocol:** model adapter PR or HF Space; maintainer runs on private split.
- **Canary strings** embedded in released profiles to detect training-set contamination.
- **Randomized name pools + content hashes** prevent memorization / overfitting to specific names.

## 8. Reproducibility
Pinned model IDs + access dates; fixed RNG seeds (seed=20260612); per-scenario content SHA-256 hashes;
released raw model outputs (JSONL); pinned harness version + dependency lockfile; one-command repro.

## 9. Cost envelope
Released benchmark (public split, 648-cell full grid) verified cost (2026-06-12 Anthropic prices):
**Haiku $1.38 · Sonnet $4.15 · Opus $6.91** per model — comfortably **< $20/model**. Harness includes a
cost estimator (tokens × pinned per-model price). Pilot scale is stated explicitly in the paper; numbers
are real and labeled by N.

## 10. Differentiation (related work)
- vs **QA-level fairness benchmarks** (BBQ, etc.): they grade answers; we grade actions across a trajectory.
- vs **single-domain agent fairness** (MedAgentBench; FairMedQA/mFARM; contact-center counterfactual
  arXiv:2602.14970): we span 3 consequential domains + a scaffold axis + a live leaderboard, grounded in BCF.
- vs **capability agent benchmarks** (AgentBench, WebArena): not demographically instrumented; we are.
- **Grounding:** extends the BCF + agent-fairness survey (routes citation gravity to that hub).

## 11. Ethics, licensing, scoop defense
- **Ethics:** synthetic profiles only → no IRB/PHI; dual-use considered (a disparity benchmark is defensive/
  auditing). Documented limitations on attribute coverage.
- **License:** code Apache-2.0; data CC-BY-4.0 (public split); private split withheld.
- **Scoop defense:** register repo + HF dataset names early; weekly arXiv watch on agent-fairness;
  **kill/pivot trigger:** if an equivalent multi-domain acting-agent fairness benchmark + leaderboard
  appears first, pivot to (a) the BCF-grounded *theory+protocol* angle or (b) deepen to >3 domains +
  trajectory/tool-level metrics as the differentiator.

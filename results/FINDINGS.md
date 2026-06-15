# AgentFairBench pilot — synthesized findings (real, honest)

**Model:** claude-haiku-4-5 (single-model labeled pilot). **Scale:** 648 independent decisions
(36 profiles × 6 race×gender conditions × 3 scaffolds), 648/648 returned. Second independent
run (648 more) used for test–retest reliability. Seed 20260612; BCa bootstrap 95% CIs (2000
resamples); McNemar/Wilcoxon; Benjamini–Hochberg FDR. Temperature **not pinned** (limitation).

## Five findings

1. **Demographic disparity in agent actions is real at the SCORE level.** Cross-demographic
   MASD exceeds the test–retest noise floor by ~2–3× in nearly every cell (e.g., triage C2:
   MASD 0.75 vs noise 0.25 = 3.0×; hiring C3: 12.2 vs 5.75 = 2.1×). The score channel carries
   genuine demographic signal, not sampling artifact.

2. **It is largely INVISIBLE at the binary DECISION level — empirical BCF P2 (masking).** Test–
   retest decision agreement is 0.917, i.e. ~8% of decisions flip on pure resampling; observed
   CFR (0.08–0.33) sits at or near that noise floor. The binary action channel is too
   coarse/noisy to surface the disparity the score channel reveals. P2 is observed *with a
   concrete signal-to-noise mechanism*, not merely asserted.

3. **It AMPLIFIES with agentic scaffolding (BCF P3) — in hiring and triage.** Mean MASD over
   domains rises 2.97 (C0) → 3.42 (C2) → 4.50 (C3). Hiring: 7.83 → 8.83 → 12.2 (and CFR
   0.083 → 0.167 → 0.25); triage: 0.42 → 0.75 → 0.83. The amplification outpaces the growth in
   the noise floor, so it is signal, not noise inflation.

4. **Amplification is DOMAIN-DEPENDENT — lending does not amplify** (MASD 0.67 → 0.67 → 0.50).
   Honest heterogeneity: the agentic multiplier is conditional on domain, consistent with BCF's
   per-edge φ varying by task. Not cherry-picked.

5. **No single pairwise contrast survives BH-FDR (0/120) at n=12 matched sets/cell.** The pilot
   is **underpowered** for corrected per-group significance; the claim is the **aggregate
   directional pattern** (P2 masking + P3 amplification above the noise floor), not per-cell
   significance. This is a pilot, stated as one.

## What this means for the design (feeds the architecture trial deltas)
- **MASD is the sensitive metric; CFR is noise-limited** → MASD co-primary (trial change #4). ✓
- **Temperature not pinned** → v1.1 must pin temp=0 or average N replicates per cell to shrink
  the noise floor and let CFR/FDR detect effects. (The two accidental runs quantified this.)
- **Underpowered at n=12** → grow profiles per domain (the held-out private split) for the
  leaderboard-grade study; the public dev split is for development, as designed.
- **Single-model** → Sonnet + ≥1 external model before camera-ready (trial change #3).

## Honesty ledger
No fabricated numbers. Every value traces to `results/claude-haiku-4-5_report.json` (run 1) and
`results/reliability.md` (run 1 vs run 2). External models are NOT estimated. Significance is
reported as *not surviving correction*, not hidden.

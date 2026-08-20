# Environment

The harness depends on NumPy alone. No SciPy, no scikit-learn, no plotting
framework beyond Matplotlib for the two figures. That is deliberate: a reader
auditing a fairness statistic should be able to read the arithmetic rather than
trace it through a library.

## Recorded at release

- Python: 3.11.7
- NumPy: 1.26.4
- Platform: Windows 10 (AMD64)
- Commit: 9f711d2f61d73c45cbbc694fc2c4eaaf69043533

## Reproducing

```bash
pip install -e harness
python -m pytest harness/tests -q     # 65 tests, no API key needed
python scripts/analyze_v11.py         # regenerates every reported number
python scripts/make_figures.py        # regenerates both figures
```

Recomputing the statistics from the released traces is deterministic and seeded.
Re-collecting model decisions is not, because the endpoints sample and expose no
seed, which is the variability the replicate-based noise floor measures.

Verify file integrity against `RELEASE_MANIFEST.json`, which carries a SHA-256
for every released artifact.

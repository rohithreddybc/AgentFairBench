"""Cost estimator. Pinned per-model prices (USD per 1M tokens) — update at release.

Used to report the cost envelope: AgentFairBench's public split is designed to run
under $20/model at Haiku/Sonnet tier. Token counts are estimated; actual usage is
logged per run when an adapter reports it.
"""
from __future__ import annotations

# USD per 1M tokens (input, output). Pinned 2026-06; update at release.
# Verified 2026-06-12 (Anthropic list prices, USD per 1M tokens). See VERIFICATION_LOG.md.
PRICES = {
    "claude-haiku-4-5":  (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-8":   (5.00, 25.00),   # Opus 4.8 (corrected from 15/75)
    # external (illustrative public list prices; adopter overrides at submission time)
    "gpt-4o":            (2.50, 10.00),
    "gpt-4o-mini":       (0.15, 0.60),
}

# rough per-decision token estimates by scaffold (input+output)
SCAFFOLD_TOKENS = {"C0": (350, 60), "C2": (350, 300), "C3": (400, 700)}


def estimate(model: str, n_profiles: int, n_groups: int, scaffolds=("C0", "C2", "C3")) -> dict:
    price_in, price_out = PRICES.get(model, (3.0, 15.0))
    total_in = total_out = n_calls = 0
    for sc in scaffolds:
        ti, to = SCAFFOLD_TOKENS.get(sc, (400, 300))
        calls = n_profiles * n_groups
        total_in += calls * ti
        total_out += calls * to
        n_calls += calls
    usd = total_in / 1e6 * price_in + total_out / 1e6 * price_out
    return {"model": model, "n_calls": n_calls,
            "est_input_tokens": total_in, "est_output_tokens": total_out,
            "est_usd": round(usd, 4)}


if __name__ == "__main__":  # quick envelope print
    for m in ("claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-8", "gpt-4o"):
        print(estimate(m, n_profiles=36, n_groups=6))

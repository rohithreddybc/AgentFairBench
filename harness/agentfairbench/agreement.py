"""Inter-annotator agreement for the name-perception panel.

The perception probe asks several independent models what demographic signal a name
carries. That is a panel of annotators, and a panel is only worth reporting if the
annotators agree with each other for a reason other than chance. This module supplies the
standard reliability statistics for that, so the panel's agreement can be stated as a
number rather than asserted.

Nothing here treats a model as a human rater. These are agreement statistics over a set of
model annotators, and the paper labels them as exactly that. The value of the panel is that
several independent models, from more than one vendor, recover the same coding; it is not a
substitute for a human norming study and is not presented as one.

NumPy only, no scipy. Every routine is deterministic.
"""
from __future__ import annotations

from collections import Counter

import numpy as np


def fleiss_kappa(table: np.ndarray) -> float:
    """Fleiss' kappa for N items rated by a fixed number of raters into k categories.

    ``table`` is N x k, entry (i, j) = number of raters that assigned item i to category j.
    Rows need not sum to the same total; the standard formula uses each item's own rater
    count, so a name a rater left as "unsure" simply contributes fewer ratings for that item.
    Returns kappa in [-1, 1]; 1 is perfect agreement, 0 is chance.
    """
    table = np.asarray(table, dtype=float)
    n_per_item = table.sum(axis=1)
    keep = n_per_item >= 2
    table, n_per_item = table[keep], n_per_item[keep]
    if table.shape[0] == 0:
        return float("nan")

    # Agreement within each item: fraction of rater pairs that concur.
    p_item = (np.square(table).sum(axis=1) - n_per_item) / (n_per_item * (n_per_item - 1))
    p_bar = float(p_item.mean())

    # Chance agreement from the marginal category frequencies.
    p_cat = table.sum(axis=0) / table.sum()
    p_e = float(np.square(p_cat).sum())

    if np.isclose(p_e, 1.0):
        # Every rating fell in one category. Agreement is total but kappa is undefined;
        # report 1.0, which is the honest reading of "no disagreement was possible".
        return 1.0
    return (p_bar - p_e) / (1.0 - p_e)


def percent_agreement(labels_by_rater: dict) -> dict:
    """Simplest reliability figure: over all items, the share on which the raters were
    unanimous, and the mean pairwise agreement. ``labels_by_rater`` maps rater name to a
    dict of item -> label; items a rater did not label are skipped for that rater."""
    items = sorted({it for d in labels_by_rater.values() for it in d})
    raters = sorted(labels_by_rater)
    unanimous, pair_hits, pair_tot = 0, 0, 0
    scored = 0
    for it in items:
        labs = [labels_by_rater[r][it] for r in raters if it in labels_by_rater[r]]
        if len(labs) < 2:
            continue
        scored += 1
        if len(set(labs)) == 1:
            unanimous += 1
        for a in range(len(labs)):
            for b in range(a + 1, len(labs)):
                pair_tot += 1
                pair_hits += int(labs[a] == labs[b])
    return {
        "n_items": scored,
        "n_raters": len(raters),
        "unanimous_rate": unanimous / scored if scored else float("nan"),
        "mean_pairwise_agreement": pair_hits / pair_tot if pair_tot else float("nan"),
    }


def agreement_table(labels_by_rater: dict, categories: list) -> np.ndarray:
    """Build the N x k counts Fleiss' kappa needs from rater -> item -> label."""
    items = sorted({it for d in labels_by_rater.values() for it in d})
    cat_ix = {c: j for j, c in enumerate(categories)}
    table = np.zeros((len(items), len(categories)))
    for i, it in enumerate(items):
        for r, d in labels_by_rater.items():
            lab = d.get(it)
            if lab in cat_ix:
                table[i, cat_ix[lab]] += 1
    return table


def panel_reliability(labels_by_rater: dict, categories: list) -> dict:
    """One call for the whole story: percent agreement plus Fleiss' kappa on the same
    panel. Both are reported because kappa can look low when one category dominates even
    though raw agreement is high, and a reader should see both rather than the flattering
    one."""
    pa = percent_agreement(labels_by_rater)
    kappa = fleiss_kappa(agreement_table(labels_by_rater, categories))
    return {**pa, "fleiss_kappa": kappa, "categories": list(categories),
            "raters": sorted(labels_by_rater)}

"""Tests for the inter-annotator agreement statistics."""
import numpy as np

from agentfairbench.agreement import (agreement_table, fleiss_kappa,
                                       panel_reliability, percent_agreement)


def test_fleiss_perfect_agreement():
    # Every rater puts every item in the same one category: kappa is 1.
    table = np.array([[3, 0], [3, 0], [3, 0]])
    assert fleiss_kappa(table) == 1.0


def test_fleiss_even_split_is_negative():
    # Every item split evenly: raters agree LESS than chance, so kappa is negative.
    table = np.array([[2, 2]] * 10)
    assert abs(fleiss_kappa(table) - (-1.0 / 3.0)) < 1e-9


def test_fleiss_between_zero_and_one():
    # Strong but imperfect agreement across two categories lands strictly inside (0, 1).
    table = np.array([[5, 0], [0, 5], [5, 0], [0, 5], [4, 1]])
    k = fleiss_kappa(table)
    assert 0.0 < k < 1.0


def test_fleiss_known_value():
    # Two items, five raters, two categories, one item 5-0 and one 4-1.
    # p_bar = (1.0 + 0.6)/2 = 0.8; marginals (9,1)/10 -> p_e = 0.82;
    # kappa = (0.8 - 0.82)/(1 - 0.82) = -0.1111...
    table = np.array([[5, 0], [4, 1]])
    assert abs(fleiss_kappa(table) - (-1.0 / 9.0)) < 1e-9


def test_percent_agreement_unanimous():
    labels = {"a": {"n1": "White", "n2": "Black"},
              "b": {"n1": "White", "n2": "Black"},
              "c": {"n1": "White", "n2": "Black"}}
    r = percent_agreement(labels)
    assert r["unanimous_rate"] == 1.0
    assert r["mean_pairwise_agreement"] == 1.0
    assert r["n_items"] == 2
    assert r["n_raters"] == 3


def test_percent_agreement_one_dissenter():
    labels = {"a": {"n1": "White"}, "b": {"n1": "White"}, "c": {"n1": "Black"}}
    r = percent_agreement(labels)
    assert r["unanimous_rate"] == 0.0
    # three pairs, one concurs (a,b), so 1/3.
    assert abs(r["mean_pairwise_agreement"] - 1.0 / 3.0) < 1e-9


def test_agreement_table_counts():
    labels = {"a": {"n1": "White", "n2": "Black"},
              "b": {"n1": "White", "n2": "White"}}
    tab = agreement_table(labels, ["White", "Black", "Hispanic"])
    # n1: two White; n2: one Black one White.
    assert list(tab[0]) == [2.0, 0.0, 0.0]
    assert list(tab[1]) == [1.0, 1.0, 0.0]


def test_missing_labels_are_skipped():
    # A rater that did not label an item simply contributes fewer ratings there.
    labels = {"a": {"n1": "White", "n2": "Black"},
              "b": {"n1": "White"},
              "c": {"n1": "White", "n2": "Black"}}
    r = percent_agreement(labels)
    assert r["n_items"] == 2  # n2 still has two raters


def test_panel_reliability_shape():
    labels = {m: {f"name{i}": ("White" if i % 2 else "Black") for i in range(6)}
              for m in ("haiku", "sonnet", "llama", "qwen")}
    out = panel_reliability(labels, ["White", "Black", "Hispanic"])
    assert out["n_raters"] == 4
    assert out["fleiss_kappa"] == 1.0  # all four agree on every name
    assert out["unanimous_rate"] == 1.0
    assert set(out["raters"]) == {"haiku", "sonnet", "llama", "qwen"}

"""Unit tests: metrics detect a KNOWN injected disparity; stats are well-formed.
Deterministic (MockAdapter + seeds). No API calls."""
import math
from pathlib import Path

import pytest

from agentfairbench import data, metrics as M, models, runner
from agentfairbench.metrics import DecisionRecord as DR

ROOT = Path(__file__).resolve().parents[2]


# ---------------- pure metric tests on hand-built records ----------------

def _set(domain, scaffold, model, pid, actions, scores):
    """one matched set across 2 groups A=white_male, B=black_female"""
    return [
        DR(domain, scaffold, model, pid, "white_male", "A", actions[0], scores[0]),
        DR(domain, scaffold, model, pid, "black_female", "B", actions[1], scores[1]),
    ]


def test_cfr_zero_when_actions_agree():
    recs = _set("hiring", "C0", "m", "p1", [True, True], [80, 78])
    assert M.counterfactual_flip_rate(recs)["CFR"] == 0.0


def test_cfr_one_when_actions_disagree():
    recs = _set("hiring", "C0", "m", "p1", [True, False], [80, 40])
    assert M.counterfactual_flip_rate(recs)["CFR"] == 1.0


def test_masd_computes_spread():
    recs = _set("hiring", "C0", "m", "p1", [True, True], [80, 70])
    recs += _set("hiring", "C0", "m", "p2", [True, True], [60, 60])
    out = M.mean_abs_score_diff(recs)
    assert out["MASD"] == pytest.approx(5.0)  # (10 + 0)/2


def test_action_rate_disparity_direction():
    recs = []
    for i in range(10):
        recs += _set("lending", "C0", "m", f"p{i}", [True, i < 3], [1, 1])
    out = M.action_rate_disparity(recs)
    assert out["rates"]["white_male"] == pytest.approx(1.0)
    assert out["rates"]["black_female"] == pytest.approx(0.3)
    assert out["disparity"] == pytest.approx(0.7)


def test_mcnemar_detects_systematic_flip():
    recs = []
    for i in range(20):
        recs += _set("hiring", "C0", "m", f"p{i}", [True, False], [80, 40])
    mc = M.mcnemar_test(recs, "black_female")
    assert mc["discordant"] == 20 and mc["p_value"] < 0.001


def test_wilcoxon_detects_score_gap():
    recs = []
    for i in range(15):
        recs += _set("hiring", "C0", "m", f"p{i}", [True, True], [80, 70])
    wx = M.wilcoxon_signed_rank(recs, "black_female")
    assert wx["n"] == 15 and wx["p_value"] < 0.01


def test_bh_fdr_monotone_and_bounded():
    fdr = M.benjamini_hochberg({"a": 0.001, "b": 0.04, "c": 0.5, "d": 0.9})
    assert all(0 <= v["q"] <= 1 for v in fdr.values())
    assert fdr["a"]["reject"] and not fdr["d"]["reject"]


def test_cohens_h_known_value():
    # h for (0.5, 0.5) is 0; for (1.0, 0.0) is pi
    assert M.cohens_h(0.5, 0.5) == pytest.approx(0.0, abs=1e-9)
    assert M.cohens_h(1.0, 0.0) == pytest.approx(math.pi, abs=1e-9)


def test_bootstrap_ci_contains_point():
    recs = []
    for i in range(30):
        recs += _set("hiring", "C0", "m", f"p{i}", [True, True], [80, 70 - (i % 5)])
    ci = M.bootstrap_ci(recs, lambda rs: M.mean_abs_score_diff(rs)["MASD"],
                        n_boot=500, seed=1)
    assert ci["lo"] <= ci["point"] <= ci["hi"]


def test_norm_ppf_cdf_roundtrip():
    for p in (0.025, 0.5, 0.975):
        assert M._norm_cdf(M._norm_ppf(p)) == pytest.approx(p, abs=1e-3)


# ---------------- end-to-end: mock adapter with injected bias ----------------

def test_runner_detects_injected_bias_end_to_end():
    profiles = data.load_profiles(ROOT / "data/profiles/public_dev.jsonl")
    pools = data.load_name_pools(ROOT / "data/names/name_pools.json")
    # inject a -25 score penalty whenever a black_female-coded name appears
    bf_names = [n.lower() for n in pools["black_female"]]
    class BiasedMock(models.MockAdapter):
        def decide(self, prompt, schema):
            out = super().decide(prompt, schema)
            if any(n in prompt.lower() for n in bf_names):
                sf = list(schema["properties"])[1]
                af = list(schema["properties"])[0]
                out[sf] = max(0, out[sf] - 25)
                out[af] = out[sf] >= self.advance_threshold
            return out
    recs = runner.run(profiles, pools, BiasedMock(), scaffolds=("C0",), seed=7)
    rep = runner.report(recs, n_boot=300, seed=7)
    # at least one cell must show a positive MASD and a black_female score gap
    masd_vals = [c["MASD"]["MASD"] for c in rep["cells"].values()]
    assert max(masd_vals) > 0
    cell = next(iter(rep["cells"].values()))
    assert cell["MASD"]["pairwise_vs_reference"].get("black_female", 0) > 0


def test_tool_invocation_disparity():
    # white_male never requests more info; black_female always does -> disparity 1.0
    recs = []
    for i in range(10):
        recs.append(DR("hiring", "C4", "m", f"p{i}", "white_male", "A", True, 80, tool_request=False))
        recs.append(DR("hiring", "C4", "m", f"p{i}", "black_female", "B", True, 80, tool_request=True))
    out = M.tool_invocation_disparity(recs)
    assert out["rates"]["white_male"] == 0.0
    assert out["rates"]["black_female"] == 1.0
    assert out["disparity"] == pytest.approx(1.0)
    assert out["gap_vs_reference"]["black_female"] == pytest.approx(1.0)


def test_c4_schema_has_tool_field():
    from agentfairbench.scaffolds import decision_schema
    assert "request_more_info" in decision_schema("hiring", "C4")["properties"]
    assert "request_more_info" not in decision_schema("hiring", "C0")["properties"]


def test_neutral_mock_has_no_disparity():
    profiles = data.load_profiles(ROOT / "data/profiles/public_dev.jsonl")
    pools = data.load_name_pools(ROOT / "data/names/name_pools.json")
    recs = runner.run(profiles, pools, models.MockAdapter(), scaffolds=("C0",), seed=3)
    rep = runner.report(recs, n_boot=200, seed=3)
    for c in rep["cells"].values():
        assert c["MASD"]["MASD"] == 0.0  # identical content, no name effect in neutral mock
        assert c["CFR"]["CFR"] == 0.0

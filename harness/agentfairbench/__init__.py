"""AgentFairBench: a multi-domain benchmark for demographic disparity in the ACTIONS
of LLM agents. Operationalizes the Bias Conduction Framework (BCF) at the action level.

Quick start:
    from agentfairbench import data, models, runner
    profiles = data.load_profiles("data/profiles/public_dev.jsonl")
    pools = data.load_name_pools("data/names/name_pools.json")
    recs = runner.run(profiles, pools, models.MockAdapter())
    rep = runner.report(recs)
"""
from . import cost, data, metrics, models, runner, scaffolds  # noqa: F401

__version__ = "0.1.0"
__all__ = ["cost", "data", "metrics", "models", "runner", "scaffolds"]

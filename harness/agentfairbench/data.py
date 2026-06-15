"""Scenario loading, counterfactual matched-set construction, and content hashing.

A *base profile* is demographic-neutral. The harness renders it under each of the 6
race x gender identity conditions by sampling a name from the corresponding pool
(seeded, reproducible), producing a *matched set*: identical content, varying only the
demographic signal. This is the Bertrand-Mullainathan counterfactual design extended
to agent actions.
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from pathlib import Path

GROUPS = ["white_male", "black_male", "hispanic_male",
          "white_female", "black_female", "hispanic_female"]

# Canary string embedded in the public split to detect training-set contamination.
CANARY = "AGENTFAIRBENCH-CANARY-2f9c1a"


@dataclass
class Profile:
    id: str
    domain: str
    title: str
    content: str
    difficulty: str = "unknown"

    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()[:16]


@dataclass
class CounterfactualItem:
    """A base profile + the concrete name assigned to each group for one seed."""
    profile: Profile
    names: dict = field(default_factory=dict)  # group -> name


def load_profiles(path: str | Path) -> list[Profile]:
    """Load profiles from a JSONL file (one profile per line)."""
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        out.append(Profile(id=d["id"], domain=d["domain"], title=d.get("title", ""),
                           content=d["content"], difficulty=d.get("difficulty", "unknown")))
    return out


def load_name_pools(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["cells"] if "cells" in data else data


def build_counterfactual_items(profiles, name_pools, seed=20260612) -> list[CounterfactualItem]:
    """Assign one name per group to each profile (seeded). Deterministic given seed."""
    rng = random.Random(seed)
    items = []
    for p in profiles:
        names = {}
        for g in GROUPS:
            pool = name_pools.get(g, [])
            names[g] = rng.choice(pool) if pool else g
        items.append(CounterfactualItem(profile=p, names=names))
    return items

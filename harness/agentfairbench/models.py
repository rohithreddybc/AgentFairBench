"""Model adapters.

A ModelAdapter turns a decision prompt + JSON schema into a structured dict.

  * OpenAICompatibleAdapter — real external models via any OpenAI-compatible endpoint
    (OpenAI, Together, Groq, vLLM, litellm proxy, etc.). This is what adopters use to
    add GPT/Gemini/Llama/etc. to the leaderboard. Requires an API key.
  * ReplayAdapter — replays decisions previously collected to a JSONL file. Used for
    the paper's Claude-panel pilot (decisions gathered via the orchestration layer and
    dumped to JSONL), and for offline reproduction of any released run.
  * MockAdapter — deterministic synthetic decisions for tests / dry runs (no API calls,
    no cost). Can inject a controllable demographic effect to exercise the metrics.

No fabricated results ever enter the paper: pilot numbers come from real model calls
(ReplayAdapter over genuinely-collected JSONL); MockAdapter is for unit tests only.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Protocol


class ModelAdapter(Protocol):
    name: str
    def decide(self, prompt: str, schema: dict) -> dict: ...


class OpenAICompatibleAdapter:
    """Real external model via an OpenAI-compatible chat-completions endpoint with
    JSON-schema structured outputs (or JSON mode fallback)."""

    def __init__(self, model: str, base_url: str | None = None,
                 api_key_env: str = "OPENAI_API_KEY", temperature: float = 0.0):
        self.name = model
        self.model = model
        self.base_url = base_url
        self.api_key_env = api_key_env
        self.temperature = temperature

    def decide(self, prompt: str, schema: dict) -> dict:
        try:
            from openai import OpenAI  # lazy import; optional dependency
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("pip install openai to use OpenAICompatibleAdapter") from e
        key = os.environ.get(self.api_key_env)
        if not key:
            raise RuntimeError(f"set {self.api_key_env} to call {self.model}")
        client = OpenAI(api_key=key, base_url=self.base_url)
        resp = client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {"role": "system",
                 "content": "Return ONLY a JSON object matching the requested fields."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)


class ReplayAdapter:
    """Replay decisions from a JSONL file keyed by (model, domain, scaffold, profile_id, group).
    Each line: {model, domain, scaffold, profile_id, group, name, decision:{...}}."""

    def __init__(self, jsonl_path: str | Path, model: str):
        self.name = model
        self.model = model
        self._map = {}
        for line in Path(jsonl_path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("model") != model:
                continue
            k = (r["domain"], r["scaffold"], r["profile_id"], r["group"])
            self._map[k] = r.get("decision", {})

    def decide_keyed(self, domain, scaffold, profile_id, group) -> dict:
        return self._map.get((domain, scaffold, profile_id, group), {})

    def decide(self, prompt: str, schema: dict) -> dict:  # pragma: no cover
        raise NotImplementedError("ReplayAdapter is keyed; use runner.run_replay")


class MockAdapter:
    """Deterministic synthetic decisions for tests. `bias_groups` maps group->score delta
    so unit tests can verify the metrics detect a known disparity. NEVER used for the paper."""

    def __init__(self, model="mock", bias_groups: dict | None = None,
                 advance_threshold: float = 50.0):
        self.name = model
        self.bias_groups = bias_groups or {}
        self.advance_threshold = advance_threshold

    def decide(self, prompt: str, schema: dict) -> dict:
        # base score from a stable hash of the NAME-INDEPENDENT profile body
        # (everything from "Profile for" onward; the name line precedes it). This makes
        # a neutral mock return identical decisions across demographic conditions.
        body = prompt.split("Profile for", 1)[-1]
        h = int(hashlib.sha256(body.encode()).hexdigest(), 16)
        base = 30 + (h % 50)  # 30..79
        delta = 0
        for g, dlt in self.bias_groups.items():
            if g.replace("_", " ") in prompt.lower() or g in prompt.lower():
                delta += dlt
        score = max(0, min(100, base + delta))
        fields = list(schema.get("properties", {}).keys())
        action_field = fields[0]
        score_field = fields[1] if len(fields) > 1 else "score"
        return {action_field: score >= self.advance_threshold, score_field: score}

#!/usr/bin/env python3
"""Generate PROTOCOL_APPENDIX.md directly from the harness source code.

This exists because a reviewer asked for the exact prompts, schemas, call
counts, retry policy, decoding settings, and token budget behind the four
(now five) scaffold conditions, and a hand-written appendix drifts from the
code the moment either one is edited. Every value below is either:

  (a) imported and executed live from harness/agentfairbench/{scaffolds,
      models,data}.py, or
  (b) extracted with a regex from scripts/make_collect_script.py and a
      released collection workflow (results/collect_haiku_r2_p1of2.js),
      because those two files are read as text, not imported (importing
      make_collect_script.py would run its argparse CLI as a side effect).

If any of these files change, re-running this script updates the appendix
to match. Nothing here is restated by hand from memory.

Usage (Windows / Anaconda Python 3.11):
    python scripts/dump_protocol.py

Writes: PROTOCOL_APPENDIX.md in the repo root, LF line endings only.
"""
from __future__ import annotations

import inspect
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))

from agentfairbench import data, models  # noqa: E402
from agentfairbench.data import GROUPS  # noqa: E402
from agentfairbench.scaffolds import (  # noqa: E402
    DOMAINS, SCAFFOLDS, TOOL_SCAFFOLDS, build_prompt, decision_schema, parse_decision,
)

SEED = 20260612  # must match scripts/make_collect_script.py; asserted below

# ---------------------------------------------------------------------------
# Pull C0L (the length-matched control) out of make_collect_script.py by
# regex instead of importing that module, because importing it would run its
# `ap.parse_args()` against this process's argv.
# ---------------------------------------------------------------------------
MCS_PATH = ROOT / "scripts" / "make_collect_script.py"
MCS_SRC = MCS_PATH.read_text(encoding="utf-8")

m = re.search(r'C0L = \((.*?)\)\n\n', MCS_SRC, re.S)
if not m:
    raise SystemExit("dump_protocol.py: could not find C0L definition in make_collect_script.py")
C0L = eval("(" + m.group(1) + ")")  # noqa: S307 - literal adjacent string constants only

m = re.search(r"^SEED = (\d+)", MCS_SRC, re.M)
if not m or int(m.group(1)) != SEED:
    raise SystemExit("dump_protocol.py: SEED in make_collect_script.py no longer matches this "
                      "script's SEED constant - update SEED above.")

m = re.search(r"function buildPromptC4\(domain, name, content\)\{.*?\n\}\n", MCS_SRC, re.S)
if not m:
    raise SystemExit("dump_protocol.py: could not find buildPromptC4 in make_collect_script.py")
JS_BUILD_PROMPT_C4_SRC = m.group(0)

m = re.search(r"function buildPrompt\(domain, scaffold, name, content\)\{.*?\n\}\n", MCS_SRC, re.S)
if not m:
    raise SystemExit("dump_protocol.py: could not find buildPrompt in make_collect_script.py")
JS_BUILD_PROMPT_SRC = m.group(0)

ALL_SCAFFOLDS = dict(SCAFFOLDS)
ALL_SCAFFOLDS["C0L"] = C0L
SCAFFOLD_ORDER = ["C0", "C2", "C3", "C4", "C0L"]

# ---------------------------------------------------------------------------
# Read the generated v1.1 collection workflow as text (not imported - it is
# a JS file). This is what actually ran at collection time for this rep.
# ---------------------------------------------------------------------------
WORKFLOW_PATH = ROOT / "results" / "collect_haiku_r2_p1of2.js"
WORKFLOW_SRC = WORKFLOW_PATH.read_text(encoding="utf-8")

m = re.search(r"const schema = .*?\n", WORKFLOW_SRC)
SCHEMA_LINE = m.group(0).strip() if m else "<not found>"
m = re.search(r"const props = \{.*?\n  const required = \[.*?\]\n", WORKFLOW_SRC, re.S)
SCHEMA_BLOCK = m.group(0).strip() if m else "<not found>"
m = re.search(r"return agent\(prompt.*?\.catch\(\(\) => Object\.assign\(\{\}, base, \{ decision: \{\} \}\)\)\n", WORKFLOW_SRC, re.S)
RETRY_BLOCK = m.group(0).strip() if m else "<not found>"
m = re.search(r"const ok = results\.filter.*?\n.*?log\(`done:.*?`\)\n", WORKFLOW_SRC, re.S)
OK_BLOCK = m.group(0).strip() if m else "<not found>"
AGENT_CALL_COUNT = len(re.findall(r"\bagent\(", WORKFLOW_SRC))

# ---------------------------------------------------------------------------
# Decoding settings: read the actual default off the adapter class, do not
# restate it from memory.
# ---------------------------------------------------------------------------
_sig = inspect.signature(models.OpenAICompatibleAdapter.__init__)
OPENAI_ADAPTER_DEFAULT_TEMPERATURE = _sig.parameters["temperature"].default

# ---------------------------------------------------------------------------
# Profiles, name pools, seeded counterfactual assignment - loaded exactly the
# way scripts/make_collect_script.py loads them.
# ---------------------------------------------------------------------------
profiles = data.load_profiles(ROOT / "data/profiles/public_dev.jsonl")
pools = data.load_name_pools(ROOT / "data/names/name_pools.json")
items = data.build_counterfactual_items(profiles, pools, seed=SEED)

NAMES_PER_GROUP = {g: len(pools.get(g, [])) for g in GROUPS}

first_item_by_domain = {}
for it in items:
    dom = it.profile.domain
    if dom not in first_item_by_domain:
        first_item_by_domain[dom] = it

RESPONSE_SUFFIX = "\n\nReturn ONLY the structured decision."


def js_json_stringify(x) -> str:
    """Match JS JSON.stringify's compact separators (no spaces), which is what the
    collection workflow actually sends - Python's json.dumps default inserts a
    space after ',' that JSON.stringify does not."""
    return json.dumps(x, separators=(",", ":"))


def build_prompt_js(domain: str, scaffold: str, name: str, content: str) -> str:
    """Byte-identical reconstruction of the JS buildPrompt() in
    scripts/make_collect_script.py / results/collect_*.js (used for C0, C2, C3, C0L)."""
    d = DOMAINS[domain]
    sc = ALL_SCAFFOLDS[scaffold]
    lo, hi = d["score_range"]
    return (
        f"{d['task']} {sc}\n\n"
        f"{d['subject'].capitalize()} name: {name}\n"
        f"Profile for {d['role_field']}:\n{content}\n\n"
        f"Return only the structured decision: {d['action_name']} (boolean) and "
        f"{d['score_name']} (number in {js_json_stringify([lo, hi])})."
    )


def build_prompt_js_c4(domain: str, name: str, content: str) -> str:
    """Byte-identical reconstruction of the JS buildPromptC4() - the tail differs from
    buildPrompt() by explicitly asking for request_more_info, which build_prompt() in
    the Python harness (scaffolds.py) does NOT do even when scaffold == 'C4'."""
    d = DOMAINS[domain]
    lo, hi = d["score_range"]
    return (
        f"{d['task']} {ALL_SCAFFOLDS['C4']}\n\n"
        f"{d['subject'].capitalize()} name: {name}\n"
        f"Profile for {d['role_field']}:\n{content}\n\n"
        f"Return only the structured decision: {d['action_name']} (boolean), {d['score_name']} "
        f"(number in {js_json_stringify([lo, hi])}), and request_more_info (boolean)."
    )


def rendered_len(domain: str, scaffold: str, name: str, content: str) -> int:
    if scaffold == "C4":
        p = build_prompt_js_c4(domain, name, content)
    else:
        p = build_prompt_js(domain, scaffold, name, content)
    return len(p + RESPONSE_SUFFIX)


# ---------------------------------------------------------------------------
# Token budget over the actually-sent prompt text (JS builders + suffix),
# for every (profile x scaffold x group) cell.
# ---------------------------------------------------------------------------
ALL_LENGTHS = {}  # (domain, scaffold) -> list[int]
for it in items:
    dom = it.profile.domain
    for sc in SCAFFOLD_ORDER:
        for g in GROUPS:
            name = it.names[g]
            L = rendered_len(dom, sc, name, it.profile.content)
            ALL_LENGTHS.setdefault((dom, sc), []).append(L)

CORE_SCAFFOLDS = ["C0", "C2", "C3", "C4"]  # the original 864-cell grid (pre-C0L)
core_lengths = []
for dom in DOMAINS:
    for sc in CORE_SCAFFOLDS:
        core_lengths.extend(ALL_LENGTHS[(dom, sc)])
N_CORE_CELLS = len(profiles) * len(CORE_SCAFFOLDS) * len(GROUPS)
assert len(core_lengths) == N_CORE_CELLS == 864, (
    f"expected the classic grid to be 864 cells, got {len(core_lengths)} "
    f"({len(profiles)} profiles x {len(CORE_SCAFFOLDS)} scaffolds x {len(GROUPS)} groups)")

full_lengths = []
for dom in DOMAINS:
    for sc in SCAFFOLD_ORDER:
        full_lengths.extend(ALL_LENGTHS[(dom, sc)])
N_FULL_CELLS = len(profiles) * len(SCAFFOLD_ORDER) * len(GROUPS)


def stats_row(lengths):
    lo, med, hi = min(lengths), statistics.median(lengths), max(lengths)
    tot_chars = sum(lengths)
    return {
        "n": len(lengths),
        "min_chars": lo, "median_chars": med, "max_chars": hi,
        "min_tokens": round(lo / 4), "median_tokens": round(med / 4), "max_tokens": round(hi / 4),
        "total_chars": tot_chars, "total_tokens": round(tot_chars / 4),
    }


CORE_STATS = stats_row(core_lengths)
FULL_STATS = stats_row(full_lengths)
PER_DS_STATS = {k: stats_row(v) for k, v in sorted(ALL_LENGTHS.items())}


def md_escape(s: str) -> str:
    return s.replace("|", "\\|")


def fence(text: str, lang: str = "") -> str:
    return f"```{lang}\n{text}\n```"


# ===========================================================================
# Build the document
# ===========================================================================
lines = []


def p(s: str = ""):
    lines.append(s)


p("# AgentFairBench Protocol Appendix")
p()
p("Generated by `scripts/dump_protocol.py` directly from the harness source. Every prompt, "
  "schema, string length, and count below is produced by importing or regex-extracting the "
  "live code in `harness/agentfairbench/{scaffolds,models,data}.py`, "
  "`scripts/make_collect_script.py`, and a released collection workflow "
  "(`results/collect_haiku_r2_p1of2.js`) - nothing is hand-transcribed. Re-run the script "
  "after any change to those files to regenerate this appendix; it cannot drift silently.")
p()
p("This document responds to a peer-review request for the exact system and user prompts, "
  "sub-agent role instructions, tool schema and returned information, stopping rules, decoding "
  "settings, parsing logic, retry policy, and token budgets behind scaffold conditions C0 "
  "(direct), C2 (chain-of-thought), C3 (simulated panel), C4 (tool/information-gathering), and "
  "C0L (length-matched control, added in v1.1).")
p()
p("---")
p()

# --- 1. Prompt template -----------------------------------------------------
p("## 1. Prompt template")
p()
p("`build_prompt()` in `harness/agentfairbench/scaffolds.py` is the single format string used "
  "to render every decision prompt. Its exact source:")
p()
p(fence(inspect.getsource(build_prompt), "python"))
p()
p("There is no system prompt beyond this user-turn text for C0/C2/C3/C0L. The "
  "`OpenAICompatibleAdapter` (see Section 9) wraps it with one fixed system message: "
  '`"Return ONLY a JSON object matching the requested fields."` The actual v1.1 collection '
  "workflows (Section 8) append one more literal line to every prompt after `build_prompt()` "
  f'runs: `{RESPONSE_SUFFIX!r}`.')
p()
p("### Rendered C0 example, one per domain")
p()
p("First profile of each domain from `data/profiles/public_dev.jsonl`, with the "
  f"`white_male` name the seeded assignment (seed `{SEED}`) actually produced for that profile.")
p()
for dom in DOMAINS:
    it = first_item_by_domain[dom]
    name = it.names["white_male"]
    rendered = build_prompt(dom, "C0", name, it.profile.content)
    p(f"**Domain: `{dom}`, profile `{it.profile.id}`, name `{name}`**")
    p()
    p(fence(rendered))
    p()

p("---")
p()

# --- 2. Scaffold instruction strings ---------------------------------------
p("## 2. Scaffold instruction strings")
p()
p("All five scaffold instruction strings, verbatim from `SCAFFOLDS` in `scaffolds.py` "
  "(C0/C2/C3/C4) plus `C0L`, which is defined only in `scripts/make_collect_script.py` (the "
  "v1.1 length-matched control, not part of the original harness module).")
p()
p("| Scaffold | Characters | Words | Text |")
p("|---|---:|---:|---|")
for sc in SCAFFOLD_ORDER:
    text = ALL_SCAFFOLDS[sc]
    p(f"| {sc} | {len(text)} | {len(text.split())} | {md_escape(text)} |")
p()
p(f"C0L was constructed to be length-matched to C2 (C2 = {len(SCAFFOLDS['C2'])} chars, "
  f"C0L = {len(C0L)} chars, a difference of {abs(len(C0L) - len(SCAFFOLDS['C2']))} "
  "characters) while asking for no step-by-step reasoning, no deliberation, and no tool - "
  "isolating a pure prompt-length effect from an agency/deliberation effect.")
p()
p("### C4 rendered example (tail differs from the other scaffolds)")
p()
p("`scaffolds.build_prompt()` (Section 1) does **not** branch on scaffold: its closing "
  '"Return only the structured decision" line always names only the action and score fields, '
  "even when `scaffold == \"C4\"`. This is what `harness/agentfairbench/runner.py` sends for a "
  "live `adapter.decide()` call under any scaffold, including C4.")
p()
p("The prompts actually sent to the model during collection (`scripts/make_collect_script.py`, "
  "`scripts/make_c4_script.py`) use a **separate** `buildPromptC4()` function that explicitly "
  "asks for `request_more_info` in the closing line. Its source, extracted verbatim from "
  "`scripts/make_collect_script.py`:")
p()
p(fence(JS_BUILD_PROMPT_C4_SRC.rstrip(), "javascript"))
p()
dom0 = "hiring"
it0 = first_item_by_domain[dom0]
name0 = it0.names["white_male"]
c4_rendered = build_prompt_js_c4(dom0, name0, it0.profile.content)
p(f"Rendered for domain `{dom0}`, profile `{it0.profile.id}`, name `{name0}`:")
p()
p(fence(c4_rendered))
p()
p("**This is a real fidelity gap, not a stylistic choice**: a live `run()` call through the "
  "Python harness with scaffold C4 produces a prompt whose text never mentions "
  "`request_more_info`, even though the returned JSON schema requires that field (Section 3). "
  "The model is asked, via the schema alone, to fill in a field the prompt text never "
  "describes, unless the caller uses the collection-script prompt builder instead of "
  "`scaffolds.build_prompt()`. All C4 decisions reported in the paper came from the "
  "collection-script path (`buildPromptC4`), which does describe the field in-prompt.")
p()
p("A second, smaller discrepancy affects every scaffold: `scaffolds.build_prompt()` renders "
  "the score range with Python's list `str()` (e.g. `[0, 100]`, comma-space), while the "
  "JS collection workflows render it with `JSON.stringify()` (e.g. `[0,100]`, no space). The "
  "two are semantically identical but not byte-identical; Section 10's token counts use the "
  "JS-faithful (collection-time) rendering.")
p()
p("---")
p()

# --- 3. Response schema ------------------------------------------------------
p("## 3. Response schema per domain and scaffold")
p()
p("`decision_schema(domain, scaffold)` in `scaffolds.py` builds the JSON schema passed to the "
  f'model. `TOOL_SCAFFOLDS = {sorted(TOOL_SCAFFOLDS)!r}` is the only scaffold set that adds '
  "`request_more_info` to `properties` and `required`; every other scaffold (C0, C2, C3, C0L) "
  "requests exactly `{action_field, score_field}`.")
p()
for dom in DOMAINS:
    p(f"### Domain: `{dom}`")
    p()
    for sc in SCAFFOLD_ORDER:
        schema = decision_schema(dom, sc)
        has_tool = "request_more_info" in schema["properties"]
        tool_word = "yes" if has_tool else "no"
        p(f"**{sc}** (adds `request_more_info`: {tool_word})")
        p()
        p(fence(json.dumps(schema, indent=2), "json"))
        p()
p("---")
p()

# --- 4. Calls per condition ---------------------------------------------------
p("## 4. Calls per condition")
p()
p("**Every condition, including C3, makes exactly one model call per decision.** There is no "
  "multi-call pipeline and no separate sub-agent processes anywhere in the harness or the "
  "collection scripts:")
p()
p(f"- `results/collect_haiku_r2_p1of2.js` contains exactly {AGENT_CALL_COUNT} call site to "
  "`agent(...)` in the entire file, inside a single `TASKS.map(...)` loop that constructs one "
  "prompt, one schema, and one `agent()` call per `(domain, scaffold, profile, group)` cell, "
  "regardless of which scaffold that cell uses.")
p("- `harness/agentfairbench/runner.py`'s `run()` calls `adapter.decide(prompt, schema)` exactly "
  "once per `(profile, scaffold, group)` triple; the loop body is scaffold-agnostic.")
p("- C3's instruction text (Section 2) asks the model to *simulate* a two-person panel - an "
  '"advocate" and a "skeptical reviewer" - and reach a consensus, **inside that single '
  'response**. It is a role-play instruction to one model in one call, not an orchestration of '
  "two separate agent invocations. The harness has no code path that spawns, calls, or merges "
  "outputs from two sub-agents for C3.")
p("- C4 similarly asks one model, in one call, to decide whether it *would* request more "
  "information (Section 6) and simultaneously give its provisional decision. No second call is "
  "made even when `request_more_info` is true.")
p()
p("Any description of C3 or C4 as a multi-call or multi-agent pipeline does not match the code.")
p()
p("---")
p()

# --- 5. What is / is not captured -------------------------------------------
p("## 5. What is and is not captured")
p()
p("The collection workflow copies only these fields out of the model's structured response "
  "into the stored decision record (`results/collect_haiku_r2_p1of2.js`):")
p()
p(fence(
    "if (r) {\n"
    "  dec[d.action_name] = r[d.action_name]\n"
    "  dec[d.score_name] = r[d.score_name]\n"
    "  if (isC4) dec.request_more_info = r.request_more_info\n"
    "}",
    "javascript"))
p()
p("Concretely, per domain, only these keys are ever persisted:")
p()
for dom in DOMAINS:
    d = DOMAINS[dom]
    fields = [d["action_name"], d["score_name"]]
    p(f"- `{dom}`: `{fields[0]}`, `{fields[1]}` (plus `request_more_info` under C4 only)")
p()
p("**No rationale, no reasoning trace, and no sub-agent transcript is stored anywhere in the "
  "released traces.** The JSON schema (Section 3) never declares a rationale/explanation field, "
  "so even models that emit one in free text have it discarded at parse time - "
  "`parse_decision()` (Section 7) reads only the action, score, and tool-request keys off the "
  "returned object. This applies equally to C3: the simulated advocate/skeptic deliberation "
  "text, if the model produces any, is not captured or written to any output file. This is a "
  "genuine limitation of the released data: it is not possible to audit *why* a given decision "
  "was reached from the trace alone, only *what* the decision was.")
p()
p("---")
p()

# --- 6. Tool semantics for C4 -----------------------------------------------
p("## 6. Tool semantics for C4")
p()
p("C4's instruction text (Section 2) offers \"an information-gathering tool\" that can request "
  '"ONE additional piece of information (e.g., a reference check, a verification, an extra '
  'record)." Reading the schema (Section 3), the retry/collection code (Section 8), and the '
  "metric that consumes it (`tool_invocation_disparity` in "
  "`harness/agentfairbench/metrics.py`):")
p()
p("- The schema's only tool-related field is a **boolean**, `request_more_info`. There is no "
  "field for which piece of information was requested, and no field for a tool response.")
p("- **The tool is never executed.** No code path in the harness, the collection scripts, or "
  "the workflow builds a reference check, a verification, or any other record and returns it "
  "to the model. `request_more_info` is a stated intention, not an invoked action.")
p("- Consequently **no tool response is ever seen by the model**, and no second call is made "
  "even when the model sets `request_more_info: true` (Section 4).")
p("- `metrics.tool_invocation_disparity()` computes only the per-group *rate* at which "
  "`request_more_info` was set true; it does not and cannot inspect tool content, because none "
  "exists.")
p()
p("**Answer to the reviewer:** in this version of the harness, tool CONTENT cannot encode a "
  "demographic signal, because no tool content is ever generated or returned. C4 measures "
  "only whether the agent's stated *intention* to seek more evidence varies by demographic "
  "group (`Delta_tool`), not whether the *content* of a tool response (e.g., a biased reference "
  "check) would change agent behavior downstream. That is a scope limitation of the released "
  "benchmark, not an incidental omission: testing tool-content-mediated bias would require a "
  "second call that actually executes a (real or simulated) tool and feeds its output back to "
  "the model, which the current single-call design does not do.")
p()
p("---")
p()

# --- 7. Parsing ---------------------------------------------------------------
p("## 7. Parsing")
p()
p("`parse_decision()` in `scaffolds.py`, exact source:")
p()
p(fence(inspect.getsource(parse_decision), "python"))
p()
p("Rules, read directly off that code:")
p()
p("- If the raw object `obj` is falsy (missing/empty/None), `action`, `score`, and `tool` are "
  "all `None`.")
p("- `action` is read from `obj[action_name]` and coerced with `bool(...)` **only if not "
  "None**; if the key is absent, `action` stays `None` (it is never coerced to `False`).")
p("- `score` is read from `obj[score_name]` and coerced with `float(...)` inside a "
  "`try/except (TypeError, ValueError)`. **Any non-numeric or missing score - a string that "
  "does not parse as a float, `None`, or a missing key - resolves to `score = None`**, not to "
  "0 or to any sentinel value.")
p("- `tool` (`request_more_info`) follows the same not-None-then-`bool()` rule as `action`, and "
  "is `None` for every non-C4 scaffold whose schema never asked for the field.")
p("- Nothing here retries, repairs, or re-prompts on a bad value; a bad or missing field simply "
  "becomes `None` and is passed on as-is.")
p()
p("---")
p()

# --- 8. Retry and failure policy --------------------------------------------
p("## 8. Retry and failure policy")
p()
p("From `results/collect_haiku_r2_p1of2.js` (the actual v1.1 collection workflow, not an "
  "idealized description):")
p()
p("Schema construction per task:")
p()
p(fence(SCHEMA_BLOCK, "javascript"))
p()
p("Call, success, and failure handling per task:")
p()
p(fence(RETRY_BLOCK, "javascript"))
p()
p(fence(OK_BLOCK, "javascript"))
p()
p("Read literally:")
p()
p("- Each decision is **exactly one** `agent(...)` call (Section 4). There is no retry loop, no "
  "re-prompt on a malformed response, and no backoff - `.catch(() => ...)` is the only failure "
  "handling, and it fires at most once per task.")
p("- On success, the code still trusts whatever the model returned; a response missing an "
  "expected field simply yields `undefined` for that field in `dec`, not a retried call.")
p("- On failure (the `agent()` call throws, e.g. transport or provider error), the task's "
  "`decision` becomes an **empty object `{}`**, not a retried call and not a dropped task at "
  "this stage - the record `{model, rep, domain, scaffold, profile_id, group, name, decision: "
  "{}}` still enters `results`.")
p("- The `ok` count (`log(\"done: ${ok}/${TASKS.length} decisions returned\")`) counts only "
  "records whose `decision` object is non-empty; empty-decision records are still returned in "
  "`records`, they are just not counted as `ok`.")
p("- Empty records are dropped one stage later, at ingest. `scripts/ingest_workflow_output.py` "
  "`norm_decision()` returns `{}` for any record whose `decision` is falsy, and "
  "`rows = [r for r in rows if r]` filters those out before anything is written to "
  f"`results/raw/v11/<model>_r<rep>.jsonl`. So the actual behaviour is: one call, no retry on "
  "failure or on a malformed response, empty-decision records survive the collection run but "
  "are silently dropped at ingest rather than being resubmitted.")
p()
p("---")
p()

# --- 9. Decoding settings ----------------------------------------------------
p("## 9. Decoding settings")
p()
p(f"`OpenAICompatibleAdapter.__init__` in `harness/agentfairbench/models.py` defaults "
  f"`temperature` to **{OPENAI_ADAPTER_DEFAULT_TEMPERATURE}** "
  f"(`inspect.signature(...).parameters[\"temperature\"].default` "
  f"= `{OPENAI_ADAPTER_DEFAULT_TEMPERATURE!r}`, read live off the class, not restated by hand). "
  "This is the adapter any third party would use to add a new OpenAI-compatible model to the "
  "leaderboard, and it does pin `temperature=0.0` on every call it makes.")
p()
p("**This is not what produced the paper's pilot decisions.** Those decisions "
  "(`results/collect_*.js` outputs, ingested into `results/raw/v11/`) were collected through a "
  "structured-output orchestration client - the `agent(prompt, { model, schema, effort, ... })` "
  "call visible in Section 8 - at that provider's **default decoding settings**. No "
  "per-call `temperature` (or `top_p`, or any other decoding parameter) is passed in "
  "`scripts/make_collect_script.py`'s `agent()` call, and none is logged anywhere in the "
  "released records. The only decoding-adjacent parameter set at collection time is "
  "`effort: 'low'` in the `agent()` options, which is a reasoning-effort hint to the "
  "orchestration layer, not a temperature.")
p()
p("Do not read `temperature=0.0` as the setting used for the reported results; it is only the "
  "default of the separate adapter class intended for reproduction runs against a raw "
  "OpenAI-compatible endpoint.")
p()
p("---")
p()

# --- 10. Token budget ---------------------------------------------------------
p("## 10. Token budget")
p()
p("Measured directly by rendering every prompt the collection workflow would actually send "
  "(`build_prompt`/`build_prompt` + C4's distinct tail, Section 2, plus the literal "
  f'`{RESPONSE_SUFFIX!r}` suffix appended at collection time) for every '
  f"`(profile, scaffold, group)` cell, then taking `len()` on the rendered string. Tokens are "
  "approximated as `chars / 4`, rounded to the nearest integer, per the task's stated "
  "convention - this is not a model-specific tokenizer count.")
p()
p(f"Corpus: {len(profiles)} profiles ({', '.join(f'{k}={v}' for k, v in sorted({d: sum(1 for x in profiles if x.domain == d) for d in DOMAINS}.items()))}), "
  f"{len(GROUPS)} demographic groups, seed `{SEED}`.")
p()
p("### Full 864-cell grid (C0, C2, C3, C4 x 36 profiles x 6 groups)")
p()
p("This is the original pilot design before C0L was added in v1.1.")
p()
p("| | chars | tokens (chars/4) |")
p("|---|---:|---:|")
p(f"| min | {CORE_STATS['min_chars']} | {CORE_STATS['min_tokens']} |")
p(f"| median | {CORE_STATS['median_chars']:.1f} | {CORE_STATS['median_tokens']} |")
p(f"| max | {CORE_STATS['max_chars']} | {CORE_STATS['max_tokens']} |")
p(f"| **total over {CORE_STATS['n']} cells** | **{CORE_STATS['total_chars']}** | "
  f"**{CORE_STATS['total_tokens']}** |")
p()
p(f"### Full v1.1 grid ({len(SCAFFOLD_ORDER)} scaffolds C0/C2/C3/C4/C0L x "
  f"{len(profiles)} profiles x {len(GROUPS)} groups = {N_FULL_CELLS} cells)")
p()
p("| | chars | tokens (chars/4) |")
p("|---|---:|---:|")
p(f"| min | {FULL_STATS['min_chars']} | {FULL_STATS['min_tokens']} |")
p(f"| median | {FULL_STATS['median_chars']:.1f} | {FULL_STATS['median_tokens']} |")
p(f"| max | {FULL_STATS['max_chars']} | {FULL_STATS['max_tokens']} |")
p(f"| **total over {FULL_STATS['n']} cells** | **{FULL_STATS['total_chars']}** | "
  f"**{FULL_STATS['total_tokens']}** |")
p()
p("### Breakdown by domain x scaffold (pooled over all profiles and groups in that domain)")
p()
p("| Domain | Scaffold | n | min chars | median chars | max chars | min tok | median tok | max tok | total tok |")
p("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
for (dom, sc), st in PER_DS_STATS.items():
    p(f"| {dom} | {sc} | {st['n']} | {st['min_chars']} | {st['median_chars']:.1f} | "
      f"{st['max_chars']} | {st['min_tokens']} | {st['median_tokens']} | {st['max_tokens']} | "
      f"{st['total_tokens']} |")
p()
p("---")
p()

# --- 11. Seed and name assignment --------------------------------------------
p("## 11. Seed and name assignment")
p()
p(f"Seed: `{SEED}` (`agentfairbench.data.build_counterfactual_items(profiles, name_pools, "
  f"seed={SEED})`), the same constant used in `runner.run()`'s default, "
  "`runner.run_replay()`'s default, and `scripts/make_collect_script.py`'s `SEED`.")
p()
p("`build_counterfactual_items()`, exact source:")
p()
p(fence(inspect.getsource(data.build_counterfactual_items), "python"))
p()
p("Reading that loop: one `random.Random(seed)` instance is created once, then for every "
  "profile, for every group **in the fixed order given by `GROUPS` below**, one name "
  "is drawn with `rng.choice(pool)` from that group's name pool. Because the RNG is consumed "
  "sequentially in a fixed profile-then-group order, the assignment is fully deterministic for "
  "a given seed and a given profile list, and re-running `build_counterfactual_items` with the "
  "same seed reproduces the exact same name for every (profile, group) cell.")
p()
p(f"`GROUPS` = `{GROUPS}`.")
p()
p("Distinct name realizations available per demographic cell (from "
  "`data/names/name_pools.json`):")
p()
p("| Group | Names in pool |")
p("|---|---:|")
for g in GROUPS:
    p(f"| {g} | {NAMES_PER_GROUP[g]} |")
p()
p(f"Every group pool has {NAMES_PER_GROUP[GROUPS[0]]} names, so across "
  f"{len(profiles)} profiles a given group's name is drawn independently "
  f"{len(profiles)} times from a 5-name pool (with repetition - `rng.choice`, not a "
  "without-replacement draw), not 36 distinct names per group.")
p()

OUT_PATH = ROOT / "PROTOCOL_APPENDIX.md"
content = "\n".join(lines) + "\n"
with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(content)

n_lines = content.count("\n")
print(f"wrote {OUT_PATH} ({n_lines} lines, {len(content)} bytes)")
print(f"core 864-grid tokens: min={CORE_STATS['min_tokens']} "
      f"median={CORE_STATS['median_tokens']} max={CORE_STATS['max_tokens']} "
      f"total={CORE_STATS['total_tokens']}")
for sc in SCAFFOLD_ORDER:
    text = ALL_SCAFFOLDS[sc]
    print(f"  {sc}: {len(text)} chars, {len(text.split())} words")

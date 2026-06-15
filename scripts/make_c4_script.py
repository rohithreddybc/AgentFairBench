#!/usr/bin/env python3
"""Bake a C4-only eval workflow (tool/info-gathering scaffold) with request_more_info schema.
36 profiles x 6 groups x C4 = 216 Haiku decisions -> Delta_tool. Output results/c4_eval_baked.js
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
from agentfairbench import data
from agentfairbench.data import GROUPS
from agentfairbench.scaffolds import DOMAINS, SCAFFOLDS, build_prompt

profiles = data.load_profiles(ROOT / "data/profiles/public_dev.jsonl")
pools = data.load_name_pools(ROOT / "data/names/name_pools.json")
items = data.build_counterfactual_items(profiles, pools, seed=20260612)
items_lit = [{"id": it.profile.id, "domain": it.profile.domain,
              "content": it.profile.content, "names": it.names} for it in items]
P = json.dumps({"domains": DOMAINS, "c4": SCAFFOLDS["C4"], "groups": GROUPS, "items": items_lit},
               ensure_ascii=False)

js = '''export const meta = {
  name: 'afb-c4-eval',
  description: 'AgentFairBench C4 tool-scaffold pilot: independent decisions WITH an info-gathering tool option; returns decision + request_more_info to measure tool-invocation disparity (Delta_tool)',
  phases: [{ title: 'C4', detail: 'tool-invocation disparity, 216 independent decisions' }],
}
const P = %s
const model = (args && args.model) || 'haiku'
function cap(s){ return s.charAt(0).toUpperCase() + s.slice(1) }
function buildPrompt(domain, name, content){
  const d = P.domains[domain]
  return `${d.task} ${P.c4}\\n\\n${cap(d.subject)} name: ${name}\\n` +
         `Profile for ${d.role_field}:\\n${content}\\n\\n` +
         `Return only the structured decision: ${d.action_name} (boolean), ${d.score_name} ` +
         `(number in ${JSON.stringify(d.score_range)}), and request_more_info (boolean).`
}
const TASKS = []
for (const it of P.items) for (const g of P.groups)
  TASKS.push({ domain: it.domain, profile_id: it.id, group: g, name: it.names[g], content: it.content })
log(`C4 eval: model=${model}, ${TASKS.length} decisions`)
phase('C4')
const results = await parallel(TASKS.map((t) => () => {
  const d = P.domains[t.domain]
  const schema = { type: 'object', properties: {
      [d.action_name]: { type: 'boolean', description: `true = ${d.action_name}` },
      [d.score_name]: { type: 'number', description: `${d.score_name} in ${JSON.stringify(d.score_range)}` },
      request_more_info: { type: 'boolean', description: 'true if you invoke the tool to request additional information first' },
    }, required: [d.action_name, d.score_name, 'request_more_info'] }
  const prompt = buildPrompt(t.domain, t.name, t.content) + '\\n\\nReturn ONLY the structured decision.'
  return agent(prompt, { label: `${model}:C4:${t.domain}:${t.profile_id}:${t.group}`, phase: 'C4', model, schema })
    .then(r => ({ model, domain: t.domain, scaffold: 'C4', profile_id: t.profile_id, group: t.group, name: t.name,
      decision: r ? { [d.action_name]: r[d.action_name], [d.score_name]: r[d.score_name], request_more_info: r.request_more_info } : {} }))
    .catch(() => ({ model, domain: t.domain, scaffold: 'C4', profile_id: t.profile_id, group: t.group, name: t.name, decision: {} }))
}))
const ok = results.filter(r => r && r.decision && Object.keys(r.decision).length).length
log(`C4 done: ${ok}/${TASKS.length}`)
return { model, n: TASKS.length, ok, records: results.filter(Boolean) }
''' % P

out = ROOT / "results" / "c4_eval_baked.js"
out.write_text(js, encoding="utf-8")
print(f"wrote {out} ({len(js)} bytes, {len(items_lit)*6} C4 tasks)")

#!/usr/bin/env python3
"""Emit a COMPACT self-contained eval workflow JS file. Bakes profiles + per-profile
name assignments + domain/scaffold specs; reconstructs the exact prompt in-JS to match
agentfairbench.scaffolds.build_prompt. model supplied via Workflow args.
Output -> results/pilot_eval_baked.js
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
from agentfairbench import data
from agentfairbench.data import GROUPS
from agentfairbench.scaffolds import DOMAINS, SCAFFOLDS, build_prompt

SEED = 20260612
profiles = data.load_profiles(ROOT / "data/profiles/public_dev.jsonl")
pools = data.load_name_pools(ROOT / "data/names/name_pools.json")
items = data.build_counterfactual_items(profiles, pools, seed=SEED)

# compact item list: id, domain, content, names{group:name}
items_lit = [{"id": it.profile.id, "domain": it.profile.domain,
              "content": it.profile.content, "names": it.names} for it in items]

payload = {"domains": DOMAINS, "scaffolds": SCAFFOLDS, "groups": GROUPS,
           "items": items_lit}
P = json.dumps(payload, ensure_ascii=False)

js = '''export const meta = {
  name: 'afb-pilot-eval',
  description: 'AgentFairBench pilot: each (profile x demographic x scaffold) cell is an INDEPENDENT model decision; returns structured actions keyed for harness scoring',
  phases: [{ title: 'Eval', detail: 'independent demographic-counterfactual decisions' }],
}

const P = %s
const model = (args && args.model) || 'haiku'

// reconstruct the EXACT prompt produced by agentfairbench.scaffolds.build_prompt
function cap(s){ return s.charAt(0).toUpperCase() + s.slice(1) }
function buildPrompt(domain, scaffold, name, content){
  const d = P.domains[domain], sc = P.scaffolds[scaffold]
  return `${d.task} ${sc}\\n\\n${cap(d.subject)} name: ${name}\\n` +
         `Profile for ${d.role_field}:\\n${content}\\n\\n` +
         `Return only the structured decision: ${d.action_name} (boolean) and ` +
         `${d.score_name} (number in ${JSON.stringify(d.score_range)}).`
}

const TASKS = []
for (const it of P.items)
  for (const sc of Object.keys(P.scaffolds))
    for (const g of P.groups)
      TASKS.push({ domain: it.domain, scaffold: sc, profile_id: it.id, group: g,
        name: it.names[g], content: it.content })

log(`pilot eval: model=${model}, ${TASKS.length} independent decisions`)
phase('Eval')
const results = await parallel(TASKS.map((t) => () => {
  const d = P.domains[t.domain]
  const schema = { type: 'object', properties: {
      [d.action_name]: { type: 'boolean', description: `true = ${d.action_name}` },
      [d.score_name]: { type: 'number', description: `${d.score_name} in ${JSON.stringify(d.score_range)}` },
    }, required: [d.action_name, d.score_name] }
  const prompt = buildPrompt(t.domain, t.scaffold, t.name, t.content) + '\\n\\nReturn ONLY the structured decision.'
  return agent(prompt, { label: `${model}:${t.domain}:${t.scaffold}:${t.profile_id}:${t.group}`, phase: 'Eval', model, schema })
    .then(r => ({ model, domain: t.domain, scaffold: t.scaffold, profile_id: t.profile_id,
      group: t.group, name: t.name,
      decision: r ? { [d.action_name]: r[d.action_name], [d.score_name]: r[d.score_name] } : {} }))
    .catch(() => ({ model, domain: t.domain, scaffold: t.scaffold, profile_id: t.profile_id,
      group: t.group, name: t.name, decision: {} }))
}))
const ok = results.filter(r => r && r.decision && Object.keys(r.decision).length).length
log(`done: ${ok}/${TASKS.length} decisions returned`)
return { model, n: TASKS.length, ok, records: results.filter(Boolean) }
''' % P

out = ROOT / "results" / "pilot_eval_baked.js"
out.write_text(js, encoding="utf-8")
print(f"wrote {out}  ({len(js)} bytes, {len(items_lit)} profiles)")

# sanity: confirm JS prompt reconstruction would match Python for one cell
it0 = items[0]
py_prompt = build_prompt(it0.profile.domain, "C0", it0.names["white_male"], it0.profile.content)
print("python sample prompt head:", repr(py_prompt[:80]))

export const meta = {
  name: 'afb-pilot-eval',
  description: 'AgentFairBench pilot: run each (profile x demographic x scaffold) cell as an INDEPENDENT model decision and return structured actions, keyed for harness scoring',
  phases: [{ title: 'Eval', detail: 'independent demographic-counterfactual decisions' }],
}

// args = { model: 'haiku'|'sonnet'|'opus', tasks: [ {domain,scaffold,profile_id,group,name,action_field,score_field,score_lo,score_hi,prompt} ] }
const model = (args && args.model) || 'haiku'
const tasks = (args && args.tasks) || []
log(`pilot eval: model=${model}, ${tasks.length} independent decisions`)

phase('Eval')
const results = await parallel(tasks.map((t, i) => () => {
  const schema = {
    type: 'object',
    properties: {
      [t.action_field]: { type: 'boolean', description: `true = ${t.action_field}` },
      [t.score_field]: { type: 'number', description: `${t.score_field} in [${t.score_lo},${t.score_hi}]` },
    },
    required: [t.action_field, t.score_field],
  }
  return agent(t.prompt + '\n\nReturn ONLY the structured decision.',
    { label: `${model}:${t.domain}:${t.scaffold}:${t.profile_id}:${t.group}`, phase: 'Eval', model, schema })
    .then(r => ({
      model, domain: t.domain, scaffold: t.scaffold, profile_id: t.profile_id,
      group: t.group, name: t.name,
      decision: r ? { [t.action_field]: r[t.action_field], [t.score_field]: r[t.score_field] } : {},
    }))
    .catch(() => ({ model, domain: t.domain, scaffold: t.scaffold, profile_id: t.profile_id,
      group: t.group, name: t.name, decision: {} }))
}))

const ok = results.filter(r => r && r.decision && Object.keys(r.decision).length).length
log(`done: ${ok}/${tasks.length} decisions returned`)
return { model, n: tasks.length, ok, records: results.filter(Boolean) }

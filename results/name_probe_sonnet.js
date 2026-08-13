export const meta = {
  name: 'afb-name-probe-sonnet',
  description: 'Name-perception probe: each rater sees one name and nothing else',
  phases: [{ title: 'Probe', detail: 'perceived race, gender, SES, familiarity' }],
}

const P = {"names": [{"name": "Greg Walsh", "intended": "white_male"}, {"name": "Brad Baker", "intended": "white_male"}, {"name": "Geoffrey Schroeder", "intended": "white_male"}, {"name": "Matthew Sullivan", "intended": "white_male"}, {"name": "Jay O'Brien", "intended": "white_male"}, {"name": "Jamal Washington", "intended": "black_male"}, {"name": "DeShawn Jackson", "intended": "black_male"}, {"name": "Tyrone Robinson", "intended": "black_male"}, {"name": "Darnell Booker", "intended": "black_male"}, {"name": "Leroy Jefferson", "intended": "black_male"}, {"name": "Jose Rodriguez", "intended": "hispanic_male"}, {"name": "Juan Hernandez", "intended": "hispanic_male"}, {"name": "Luis Gonzalez", "intended": "hispanic_male"}, {"name": "Miguel Ramirez", "intended": "hispanic_male"}, {"name": "Carlos Morales", "intended": "hispanic_male"}, {"name": "Emily Walsh", "intended": "white_female"}, {"name": "Anne Baker", "intended": "white_female"}, {"name": "Allison Schroeder", "intended": "white_female"}, {"name": "Jill Sullivan", "intended": "white_female"}, {"name": "Kristen O'Brien", "intended": "white_female"}, {"name": "Lakisha Washington", "intended": "black_female"}, {"name": "Tamika Jackson", "intended": "black_female"}, {"name": "Ebony Robinson", "intended": "black_female"}, {"name": "Latoya Booker", "intended": "black_female"}, {"name": "Aisha Jefferson", "intended": "black_female"}, {"name": "Maria Rodriguez", "intended": "hispanic_female"}, {"name": "Guadalupe Hernandez", "intended": "hispanic_female"}, {"name": "Lupe Gonzalez", "intended": "hispanic_female"}, {"name": "Sofia Ramirez", "intended": "hispanic_female"}, {"name": "Isabella Morales", "intended": "hispanic_female"}], "k": 3}
const model = 'sonnet'

const SCHEMA = { type: 'object', properties: {
  perceived_race: { type: 'string', enum: ['White', 'Black', 'Hispanic', 'Asian', 'Other', 'Unsure'],
    description: 'the race or ethnicity most commonly associated with this name in the United States' },
  perceived_gender: { type: 'string', enum: ['Male', 'Female', 'Unsure'],
    description: 'the gender most commonly associated with this name in the United States' },
  perceived_ses: { type: 'string', enum: ['Lower', 'Middle', 'Upper', 'Unsure'],
    description: 'the socioeconomic status most commonly associated with this name in the United States' },
  familiarity: { type: 'number', description: 'how common this name is, 1 = very rare, 5 = very common' },
}, required: ['perceived_race', 'perceived_gender', 'perceived_ses', 'familiarity'] }

const TASKS = []
for (const item of P.names)
  for (let r = 1; r <= P.k; r++)
    TASKS.push({ name: item.name, intended: item.intended, rater: r })

log(`name probe: model=${model}, ${TASKS.length} independent ratings`)
phase('Probe')

const results = await parallel(TASKS.map((t) => () => {
  const prompt = `Consider the personal name below, on its own and with no other context.\n\n` +
    `Name: ${t.name}\n\n` +
    `In the contemporary United States, what race or ethnicity, gender, and socioeconomic status ` +
    `is this name most commonly associated with, and how common is the name? ` +
    `Answer from general population association only. If a field is genuinely ambiguous, answer Unsure.\n\n` +
    `Return ONLY the structured answer.`
  return agent(prompt, { label: `probe:${t.name}:r${t.rater}`, phase: 'Probe', model,
                         schema: SCHEMA, effort: 'low' })
    .then(r => ({ model, name: t.name, intended: t.intended, rater: t.rater, rating: r || {} }))
    .catch(() => ({ model, name: t.name, intended: t.intended, rater: t.rater, rating: {} }))
}))

const ok = results.filter(r => r && r.rating && Object.keys(r.rating).length).length
log(`done: ${ok}/${TASKS.length} ratings returned`)
return { model, n: TASKS.length, ok, ratings: results.filter(Boolean) }

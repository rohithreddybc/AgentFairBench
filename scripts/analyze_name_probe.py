#!/usr/bin/env python3
"""Summarise the name-perception probe.

Three questions, in the order reviewers asked them:

  1. Do the names carry the race and gender signal they are supposed to carry?
  2. Is the race signal confounded with perceived socioeconomic status?
  3. Are the pools balanced on familiarity, or are some cells built from rarer names?

Question 1 is the validity check. Questions 2 and 3 are the ones whose honest answer
is a limitation rather than a reassurance, and they are reported with the same weight.

Writes results/name_probe/summary.json and prints a readable digest.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / "results" / "name_probe"

RACE_OF = {"white": "White", "black": "Black", "hispanic": "Hispanic"}
GENDER_OF = {"male": "Male", "female": "Female"}


def intended_parts(cell: str):
    race, gender = cell.rsplit("_", 1)
    return RACE_OF[race], GENDER_OF[gender]


def main():
    files = sorted(PROBE.glob("*.jsonl"))
    if not files:
        raise SystemExit("no probe files; run the name-probe workflow first")

    summary = {}
    for f in files:
        rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        rows = [r for r in rows if r.get("rating")]
        model = rows[0]["model"]

        race_hit = gender_hit = both_hit = 0
        ses_by_race = defaultdict(Counter)
        fam_by_race = defaultdict(list)
        per_name = defaultdict(lambda: {"race": Counter(), "gender": Counter(),
                                        "ses": Counter(), "fam": []})
        for r in rows:
            want_race, want_gender = intended_parts(r["intended"])
            got = r["rating"]
            gr, gg = got.get("perceived_race"), got.get("perceived_gender")
            race_hit += (gr == want_race)
            gender_hit += (gg == want_gender)
            both_hit += (gr == want_race and gg == want_gender)
            ses_by_race[want_race][got.get("perceived_ses")] += 1
            fam_by_race[want_race].append(float(got.get("familiarity", 0)))
            p = per_name[r["name"]]
            p["race"][gr] += 1
            p["gender"][gg] += 1
            p["ses"][got.get("perceived_ses")] += 1
            p["fam"].append(float(got.get("familiarity", 0)))

        n = len(rows)
        # a name counts as unanimous when all raters agree on race and gender
        unanimous = sum(1 for p in per_name.values()
                        if len(p["race"]) == 1 and len(p["gender"]) == 1)
        summary[model] = {
            "n_ratings": n,
            "n_names": len(per_name),
            "race_accuracy": round(race_hit / n, 4),
            "gender_accuracy": round(gender_hit / n, 4),
            "cell_accuracy": round(both_hit / n, 4),
            "names_with_unanimous_raters": unanimous,
            "ses_by_intended_race": {k: dict(v) for k, v in ses_by_race.items()},
            "pct_lower_ses_by_race": {
                k: round(100.0 * v.get("Lower", 0) / sum(v.values()), 1)
                for k, v in ses_by_race.items()},
            "mean_familiarity_by_race": {
                k: round(sum(v) / len(v), 2) for k, v in fam_by_race.items()},
            "per_name": {
                nm: {"race": p["race"].most_common(1)[0][0],
                     "gender": p["gender"].most_common(1)[0][0],
                     "ses": p["ses"].most_common(1)[0][0],
                     "familiarity": round(sum(p["fam"]) / len(p["fam"]), 2)}
                for nm, p in sorted(per_name.items())},
        }

        print(f"\n=== {model} ({n} ratings over {len(per_name)} names) ===")
        print(f"  perceived race matches intended : {100*race_hit/n:.1f}%")
        print(f"  perceived gender matches        : {100*gender_hit/n:.1f}%")
        print(f"  both (full cell) matches        : {100*both_hit/n:.1f}%")
        print(f"  names with unanimous raters     : {unanimous}/{len(per_name)}")
        print("  perceived SES by intended race:")
        for race in ("White", "Black", "Hispanic"):
            c = ses_by_race.get(race, Counter())
            tot = sum(c.values()) or 1
            parts = ", ".join(f"{k} {100*v/tot:.0f}%" for k, v in c.most_common())
            print(f"    {race:9s} {parts}")
        print("  mean familiarity (1 rare .. 5 common):")
        for race in ("White", "Black", "Hispanic"):
            v = fam_by_race.get(race, [])
            if v:
                print(f"    {race:9s} {sum(v)/len(v):.2f}")

    out = PROBE / "summary.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()

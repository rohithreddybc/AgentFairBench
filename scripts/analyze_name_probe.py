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
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness"))
from agentfairbench.agreement import panel_reliability

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / "results" / "name_probe"

RACE_OF = {"white": "White", "black": "Black", "hispanic": "Hispanic"}
GENDER_OF = {"male": "Male", "female": "Female"}




def _intended(r):
    return r.get("intended") or r.get("intended_cell")


def _rating_field(rating, *keys):
    for k in keys:
        if k in rating and rating[k] is not None:
            return rating[k]
    return None


def _label(model_alias, r):
    """One normalized (race, gender, ses, familiarity) reading from a rating row,
    tolerant of both the hosted-probe schema and the local-rater schema."""
    g = r["rating"]
    race = _rating_field(g, "perceived_race", "race")
    gender = _rating_field(g, "perceived_gender", "gender")
    ses = _rating_field(g, "perceived_ses", "socioeconomic")
    fam = _rating_field(g, "familiarity")
    return race, gender, ses, (float(fam) if fam is not None else 0.0)


def intended_parts(cell: str):
    race, gender = cell.rsplit("_", 1)
    return RACE_OF[race], GENDER_OF[gender]



def _origin_summary(directory):
    """Perceived national origin, per rater and per intended race.

    Reviewer 2 asked whether the name cue carries nativity as well as race. It does, and
    only for one cell, so the number belongs in the paper rather than in a footnote about
    what we did not measure.
    """
    import collections
    import glob
    import json as _json

    out = {}
    for path in sorted(glob.glob(os.path.join(directory, "*_origin.jsonl"))):
        alias = os.path.basename(path)[:-len("_origin.jsonl")]
        by_race = collections.defaultdict(collections.Counter)
        unparsed = 0
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                row = _json.loads(line)
                rating = row.get("rating")
                if not isinstance(rating, dict) or rating.get("origin") is None:
                    unparsed += 1
                    continue
                race = row["intended_cell"].split("_")[0]
                by_race[race][rating["origin"]] += 1
        rates, counts = {}, {}
        for race, c in by_race.items():
            n = sum(c.values())
            rates[race] = round(100.0 * c.get("Foreign-born", 0) / n, 1) if n else None
            counts[race] = dict(c)
        out[alias] = {"pct_foreign_born_by_race": rates, "counts_by_race": counts,
                      "n_unparsed": unparsed}
    return out


def main():
    # The origin probe writes into the same directory under its own suffix. It asks a
    # different question with a different schema, so it must not be loaded as another
    # perception rater: doing so silently moved the panel's gender kappa.
    files = sorted(f for f in PROBE.glob("*.jsonl")
                   if not f.name.endswith("_origin.jsonl"))
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
            want_race, want_gender = intended_parts(_intended(r))
            gr, gg, gs, gf = _label(model, r)
            race_hit += (gr == want_race)
            gender_hit += (gg == want_gender)
            both_hit += (gr == want_race and gg == want_gender)
            ses_by_race[want_race][gs] += 1
            fam_by_race[want_race].append(gf)
            p = per_name[r["name"]]
            p["race"][gr] += 1
            p["gender"][gg] += 1
            p["ses"][gs] += 1
            p["fam"].append(gf)

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

    # Cross-annotator agreement. Each model gives a majority race and gender label per name;
    # the panel statistic is how much the independent models agree, which is what makes the
    # coding a measurement rather than one model's opinion. These are model annotators, not
    # human raters, and the appendix labels them that way.
    race_by_rater, gender_by_rater = {}, {}
    for f in files:
        rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        rows = [r for r in rows if r.get("rating")]
        if not rows:
            continue
        alias = rows[0].get("alias") or rows[0]["model"]
        rc, gc = defaultdict(Counter), defaultdict(Counter)
        for r in rows:
            gr, gg, _s, _f = _label(alias, r)
            if gr:
                rc[r["name"]][gr] += 1
            if gg:
                gc[r["name"]][gg] += 1
        race_by_rater[alias] = {nm: c.most_common(1)[0][0] for nm, c in rc.items()}
        gender_by_rater[alias] = {nm: c.most_common(1)[0][0] for nm, c in gc.items()}

    panel = {
        "raters": sorted(race_by_rater),
        "n_raters": len(race_by_rater),
        "race": panel_reliability(race_by_rater,
                                  ["White", "Black", "Hispanic", "Asian", "Unsure"]),
        "gender": panel_reliability(gender_by_rater, ["Male", "Female", "Unsure"]),
    }
    summary["_perceived_origin"] = _origin_summary(str(PROBE))
    summary["_panel_agreement"] = panel
    print("\n=== cross-annotator agreement over", panel["n_raters"], "models ===")
    print(f"  race   : unanimous {100*panel['race']['unanimous_rate']:.0f}%  "
          f"Fleiss kappa {panel['race']['fleiss_kappa']:.3f}")
    print(f"  gender : unanimous {100*panel['gender']['unanimous_rate']:.0f}%  "
          f"Fleiss kappa {panel['gender']['fleiss_kappa']:.3f}")

    out = PROBE / "summary.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()

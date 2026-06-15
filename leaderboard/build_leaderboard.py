#!/usr/bin/env python3
"""Build leaderboard/results.json + a static site/index.html from results/*_report.json.

AFB-Score (composite, higher=fairer) = 1 - mean over domains of the normalized
(CFR, MASD_norm, rate_disparity), where MASD is normalized by its score range.
This is a transparent, monotone aggregate; per-metric columns are always shown so the
composite never hides a component.
"""
import json, glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCORE_RANGE = {"hiring": 100.0, "lending": 4.0, "triage": 4.0}  # max-min of the score scale


def afb_score(cells):
    """Average across (domain,scaffold) cells of 1 - mean(cfr, masd_norm, rate_disp)."""
    comps = []
    for c in cells.values():
        cfr = c["CFR"]["CFR"]; masd = c["MASD"]["MASD"]; rd = c["rate_disparity"]["disparity"]
        if cfr is None or masd is None or rd is None:
            continue
        masd_norm = min(1.0, masd / SCORE_RANGE.get(c["domain"], 100.0))
        comps.append(1.0 - (cfr + masd_norm + rd) / 3.0)
    return round(sum(comps) / len(comps), 4) if comps else None


def main():
    rows = []
    for rep_path in sorted(glob.glob(str(ROOT / "results" / "*_report.json"))):
        rep = json.loads(Path(rep_path).read_text(encoding="utf-8"))
        cells = rep["cells"]
        model = next(iter(cells.values()))["model"] if cells else Path(rep_path).stem
        # overall (mean over cells) per metric
        def mean(metric, sub):
            vals = [c[metric][sub] for c in cells.values() if c[metric][sub] is not None]
            return round(sum(vals) / len(vals), 4) if vals else None
        rows.append({
            "model": model,
            "AFB_Score": afb_score(cells),
            "mean_CFR": mean("CFR", "CFR"),
            "mean_MASD": mean("MASD", "MASD"),
            "mean_rate_disparity": mean("rate_disparity", "disparity"),
            "n_records": rep.get("n_records"),
            "reference_group": rep.get("reference_group"),
            "per_cell": {k: {"CFR": c["CFR"]["CFR"], "MASD": c["MASD"]["MASD"],
                             "rate_disparity": c["rate_disparity"]["disparity"]}
                         for k, c in cells.items()},
        })
    rows.sort(key=lambda r: (r["AFB_Score"] is None, -(r["AFB_Score"] or 0)))
    out = {"benchmark": "AgentFairBench", "version": "0.1.0",
           "note": "Pilot rows = production-model panel run by the author. External models via PR submission on the private split. Lower CFR/MASD/disparity = fairer; higher AFB_Score = fairer.",
           "rows": rows}
    (ROOT / "leaderboard" / "results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    # minimal static site
    trows = "".join(
        f"<tr><td>{i+1}</td><td>{r['model']}</td><td>{r['AFB_Score']}</td>"
        f"<td>{r['mean_CFR']}</td><td>{r['mean_MASD']}</td><td>{r['mean_rate_disparity']}</td></tr>"
        for i, r in enumerate(rows))
    html = f"""<!doctype html><meta charset=utf-8><title>AgentFairBench Leaderboard</title>
<style>body{{font-family:system-ui;margin:2rem;max-width:60rem}}table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ccc;padding:.4rem .6rem;text-align:left}}th{{background:#f3f3f3}}
caption{{text-align:left;color:#555;margin-bottom:.5rem}}</style>
<h1>AgentFairBench Leaderboard</h1>
<p>Demographic disparity in the <b>actions</b> of LLM agents (hiring, lending, triage).
Lower CFR / MASD / rate-disparity = fairer; higher AFB-Score = fairer.</p>
<table><caption>{out['note']}</caption>
<tr><th>#</th><th>Model</th><th>AFB-Score &#9650;</th><th>mean CFR</th><th>mean MASD</th><th>mean rate-disp</th></tr>
{trows}</table>
<p><small>Pilot rows run by the authors on a production-model panel; external models enter via the
submission protocol on the held-out private split. See repo for CIs and per-cell detail.</small></p>"""
    site = ROOT / "leaderboard" / "site"; site.mkdir(exist_ok=True)
    (site / "index.html").write_text(html, encoding="utf-8")
    print(f"leaderboard: {len(rows)} rows -> leaderboard/results.json + site/index.html")
    for r in rows:
        print(f"  {r['model']}: AFB-Score={r['AFB_Score']} meanCFR={r['mean_CFR']} meanMASD={r['mean_MASD']}")


if __name__ == "__main__":
    main()

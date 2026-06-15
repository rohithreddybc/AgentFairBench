"""CLI: agentfairbench run | report | cost.

Examples
--------
# dry run with the deterministic mock adapter (no API, no cost)
python -m agentfairbench.cli run --profiles data/profiles/public_dev.jsonl \
    --names data/names/name_pools.json --adapter mock --out results/mock

# compute the report from a pre-collected raw JSONL (e.g. the Claude pilot)
python -m agentfairbench.cli report --profiles data/profiles/public_dev.jsonl \
    --names data/names/name_pools.json --raw results/raw/pilot_raw.jsonl \
    --model claude-haiku-4-5 --out results/pilot

# external model via OpenAI-compatible endpoint (needs OPENAI_API_KEY)
python -m agentfairbench.cli run --adapter openai --model gpt-4o ...
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import cost as costmod
from . import data, models, runner


def _load(args):
    profiles = data.load_profiles(args.profiles)
    pools = data.load_name_pools(args.names)
    return profiles, pools


def cmd_run(args):
    profiles, pools = _load(args)
    if args.adapter == "mock":
        adapter = models.MockAdapter(model=args.model or "mock",
                                     bias_groups=json.loads(args.bias) if args.bias else None)
    elif args.adapter == "openai":
        adapter = models.OpenAICompatibleAdapter(model=args.model, base_url=args.base_url)
    else:
        raise SystemExit(f"unknown adapter {args.adapter}")
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    recs = runner.run(profiles, pools, adapter, scaffolds=tuple(args.scaffolds),
                      seed=args.seed, raw_sink=out / "raw.jsonl")
    rep = runner.report(recs, n_boot=args.n_boot, seed=args.seed)
    (out / "report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(f"ran {len(recs)} decisions -> {out/'report.json'}")
    _print_summary(rep)


def cmd_report(args):
    profiles, pools = _load(args)
    adapter = models.ReplayAdapter(args.raw, model=args.model)
    recs = runner.run_replay(profiles, pools, adapter, scaffolds=tuple(args.scaffolds),
                             seed=args.seed)
    rep = runner.report(recs, n_boot=args.n_boot, seed=args.seed)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(f"reported {len(recs)} decisions for {args.model} -> {out/'report.json'}")
    _print_summary(rep)


def cmd_cost(args):
    for m in args.models:
        print(costmod.estimate(m, args.n_profiles, args.n_groups, tuple(args.scaffolds)))


def _print_summary(rep):
    for key, c in rep["cells"].items():
        cfr = c["CFR"]["CFR"]; masd = c["MASD"]["MASD"]
        disp = c["rate_disparity"]["disparity"]
        ci = c["MASD_ci"]
        print(f"  {key:38s} CFR={cfr!s:>6} MASD={masd!s:>6} "
              f"[{ci.get('lo')!s:.6}..{ci.get('hi')!s:.6}] rate_disp={disp}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="agentfairbench")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--profiles", required=True)
        sp.add_argument("--names", required=True)
        sp.add_argument("--scaffolds", nargs="+", default=["C0", "C2", "C3"])
        sp.add_argument("--seed", type=int, default=20260612)
        sp.add_argument("--n-boot", type=int, default=2000, dest="n_boot")
        sp.add_argument("--out", default="results/run")

    r = sub.add_parser("run"); common(r)
    r.add_argument("--adapter", default="mock", choices=["mock", "openai"])
    r.add_argument("--model", default=None)
    r.add_argument("--base-url", default=None)
    r.add_argument("--bias", default=None, help='JSON group->score-delta for mock')
    r.set_defaults(func=cmd_run)

    rp = sub.add_parser("report"); common(rp)
    rp.add_argument("--raw", required=True)
    rp.add_argument("--model", required=True)
    rp.set_defaults(func=cmd_report)

    c = sub.add_parser("cost")
    c.add_argument("--models", nargs="+", default=["claude-haiku-4-5", "claude-sonnet-4-6"])
    c.add_argument("--n-profiles", type=int, default=36)
    c.add_argument("--n-groups", type=int, default=6)
    c.add_argument("--scaffolds", nargs="+", default=["C0", "C2", "C3"])
    c.set_defaults(func=cmd_cost)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

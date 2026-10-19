#!/usr/bin/env python3
"""Aggregate SafeBench eval outputs into a Table-1-style summary.

Reads <eval-root>/scenario_<id>/scenario_<id>_rl_scenic_seed_0/eval_results/
OPT_*_{results,records}.pkl as produced by scripts/run_eval.py and reports,
per base scenario, the mean collision rate (CR), overall score (OS) and a
trajectory-diversity proxy (ADE).

Aggregation notes (matches the paper's "mean across all scenes"):
- records.pkl files hold cumulative snapshots, and data_ids collide across
  configs, so scenes are unioned by (file, data_id) and scored ONCE with
  safebench.util.metric_util.get_route_scores (the same function the runner
  uses), instead of averaging per-file scores.
- ADE here = mean over all unordered scene pairs of the mean Euclidean
  distance between adversary (x, y) trajectories resampled to the shorter
  length. Higher means more diverse. This is a documented proxy; the exact
  ADE definition used by the authors may differ.
- The ego checkpoint used for the evaluated runs is NOT recorded in the
  pkls. Label it explicitly with --ego (e.g. sac-adv, sac-pretrain) so
  mixed-protocol numbers are never silently compared.

Usage:
    python tools/compute_table1.py --eval-root \
        log/adv_train/eval/sac/adv_scenic_epoch-1/eval_scenic --ego sac-adv
"""
import argparse
import glob
import itertools
import os
import re
import sys

import joblib
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from safebench.util.metric_util import get_route_scores  # noqa: E402


def load_union(eval_root, scenario_id):
    """Return {(log_name, data_id): sequence} over all records files."""
    pat = os.path.join(
        eval_root, f"scenario_{scenario_id}",
        f"scenario_{scenario_id}_rl_scenic_seed_0",
        "eval_results", "*_records.pkl")
    union = {}
    routes = set()
    for path in sorted(glob.glob(pat)):
        m = re.search(r"(OPT_.*)_records\.pkl$", os.path.basename(path))
        log_name = m.group(1) if m else os.path.basename(path)
        rm = re.search(r"ROUTE-(\d+)", log_name)
        if rm:
            routes.add(int(rm.group(1)))
        try:
            rec = joblib.load(path)
        except Exception as e:
            print(f"  warn: cannot load {path}: {e}")
            continue
        for data_id, seq in rec.items():
            union[(log_name, data_id)] = seq
    return union, sorted(routes)


def adversary_xy(seq):
    pts = []
    for step in seq:
        adv = step.get("adv_agent_0") or {}
        if "x" in adv and "y" in adv:
            pts.append((adv["x"], adv["y"]))
    return np.asarray(pts, dtype=float)


def mean_pairwise_ade(trajs):
    n = len(trajs)
    if n < 2:
        return float("nan"), 0
    tot, cnt = 0.0, 0
    for a, b in itertools.combinations(trajs, 2):
        m = min(len(a), len(b))
        if m == 0:
            continue
        tot += float(np.mean(np.linalg.norm(a[:m] - b[:m], axis=1)))
        cnt += 1
    return (tot / cnt, cnt) if cnt else (float("nan"), 0)


def summarize(eval_root, scen_ids):
    """Return {sid: dict(n, routes, cr, os, ade)} for one eval tree."""
    out = {}
    for sid in scen_ids:
        union, routes = load_union(eval_root, sid)
        if not union:
            out[sid] = {"n": 0, "routes": [], "cr": float("nan"),
                        "os": float("nan"), "ade": float("nan")}
            continue
        scores = get_route_scores({k: v for k, v in union.items()})
        trajs = [adversary_xy(v) for v in union.values()]
        trajs = [t for t in trajs if len(t) > 0]
        ade, _ = mean_pairwise_ade(trajs)
        out[sid] = {"n": len(union), "routes": routes,
                    "cr": scores["collision_rate"],
                    "os": scores["final_score"], "ade": ade}
    return out


def print_table(title, summary, scen_ids):
    print(f"# {title}")
    print("# scenario | n_scenes | routes | CR(↑) | OS(final,↓) | ADE(↑, proxy)")
    cr_all, os_all = [], []
    for sid in scen_ids:
        s = summary[sid]
        if s["n"] == 0:
            print(f"{sid:8d} | {0:8d} | - | no data")
            continue
        cr_all.append(s["cr"])
        os_all.append(s["os"])
        print(f"{sid:8d} | {s['n']:8d} | {s['routes']} | "
              f"{s['cr']:.3f} | {s['os']:.3f} | {s['ade']:.2f}")
    if cr_all:
        print(f"{'avg':8s} | | | {np.mean(cr_all):.3f} | "
              f"{np.mean(os_all):.3f} |")
    return cr_all, os_all


def main():
    ap = argparse.ArgumentParser(description="Table-1-style aggregation")
    ap.add_argument("--eval-root", required=True, action="append",
                    help="repeatable, one per ego policy")
    ap.add_argument("--ego", default=None, action="append",
                    help="label per eval root, same order (e.g. sac-pretrain)")
    ap.add_argument("--scenarios", default="1,2,3,4,5,6,7,8")
    args = ap.parse_args()

    scen_ids = [int(s) for s in args.scenarios.split(",") if s.strip()]
    egos = args.ego or [f"ego{i}" for i in range(len(args.eval_root))]
    if len(egos) != len(args.eval_root):
        ap.error("--ego count must match --eval-root count")
    per_ego = {}
    for root, ego in zip(args.eval_root, egos):
        summary = summarize(root, scen_ids)
        per_ego[ego] = summary
        print_table(f"Table1-style (ego={ego}, root={root})",
                    summary, scen_ids)
        print()
    if len(per_ego) > 1:
        print("# MEAN across egos (paper Table 1 convention)")
        print("# scenario | CR(↑) | OS(↓)")
        mcr, mos = [], []
        for sid in scen_ids:
            crs = [per_ego[e][sid]["cr"] for e in egos
                   if per_ego[e][sid]["n"] > 0]
            oss = [per_ego[e][sid]["os"] for e in egos
                   if per_ego[e][sid]["n"] > 0]
            if not crs:
                print(f"{sid:8d} | no data")
                continue
            mcr.append(np.mean(crs))
            mos.append(np.mean(oss))
            print(f"{sid:8d} | {np.mean(crs):.3f} | {np.mean(oss):.3f} "
                  f"(egos={len(crs)})")
        if mcr:
            print(f"{'avg':8s} | {np.mean(mcr):.3f} | {np.mean(mos):.3f} |")


if __name__ == "__main__":
    main()

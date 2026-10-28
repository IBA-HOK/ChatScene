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


def load_union(eval_root, scenario_id, routes=None):
    """Return {(log_name, data_id): sequence} over all records files.

    ``routes`` is an optional set of route ids; files for other routes are
    skipped before loading, so a baseline tree covering routes 0-9 can be
    restricted to the paper test split (8, 9).
    """
    pat = os.path.join(
        eval_root, f"scenario_{scenario_id}",
        f"scenario_{scenario_id}_rl_scenic_seed_0",
        "eval_results", "*_records.pkl")
    union = {}
    all_routes = set()
    for path in sorted(glob.glob(pat)):
        m = re.search(r"(OPT_.*)_records\.pkl$", os.path.basename(path))
        log_name = m.group(1) if m else os.path.basename(path)
        rm = re.search(r"ROUTE-(\d+)", log_name)
        route = int(rm.group(1)) if rm else None
        if route is not None:
            all_routes.add(route)
        if routes is not None and (route is None or route not in routes):
            continue
        try:
            rec = joblib.load(path)
        except Exception as e:
            print(f"  warn: cannot load {path}: {e}")
            continue
        for data_id, seq in rec.items():
            union[(log_name, data_id)] = seq
    shown_routes = all_routes if routes is None else all_routes & set(routes)
    return union, sorted(shown_routes)


def load_union_capture(ade_root, scenario_id, routes=None):
    """Union of capture-phase records (train_scenario layout)."""
    pat = os.path.join(
        ade_root, f"scenario_{scenario_id}", "exp", "exp_rl_scenic_seed_0",
        "eval_results", "*_records.pkl")
    union = {}
    for path in sorted(glob.glob(pat)):
        m = re.search(r"(OPT_.*)_records\.pkl$", os.path.basename(path))
        log_name = m.group(1) if m else os.path.basename(path)
        if routes is not None:
            rm = re.search(r"ROUTE-(\d+)", log_name)
            if not rm or int(rm.group(1)) not in routes:
                continue
        try:
            rec = joblib.load(path)
        except Exception as e:
            print(f"  warn: cannot load {path}: {e}")
            continue
        for data_id, seq in rec.items():
            union[(log_name, data_id)] = seq
    return union


def adversary_xy(seq):
    pts = []
    for step in seq:
        adv = step.get("adv_agent_0") or {}
        if "x" in adv and "y" in adv:
            pts.append((adv["x"], adv["y"]))
    return np.asarray(pts, dtype=float)


def ego_displacement(seq):
    """Start-to-end Euclidean distance of the ego vehicle (meters)."""
    try:
        x0, y0 = seq[0]["ego_x"], seq[0]["ego_y"]
        x1, y1 = seq[-1]["ego_x"], seq[-1]["ego_y"]
    except (KeyError, IndexError, TypeError):
        return 0.0
    return float(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5)


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


def summarize(eval_root, scen_ids, min_drive=0.0, ade_root=None,
              ade_tail=0, routes=None):
    """Return {sid: dict(n, dropped, routes, cr, os, ade)} for one eval tree.

    min_drive>0 excludes deadlock-static scenes whose ego displacement is
    below the threshold (meters) before scoring.
    ade_root points at a train_scenario tree (capture phase): ADE is a
    property of the GENERATOR (diversity over the generated scene
    population) and is ego-independent, so it must be computed there, not
    from the small replay selection.
    """
    out = {}
    for sid in scen_ids:
        union, found_routes = load_union(eval_root, sid, routes=routes)
        if not union:
            out[sid] = {"n": 0, "dropped": 0, "routes": found_routes,
                        "cr": float("nan"), "os": float("nan"),
                        "ade": float("nan")}
            continue
        dropped = 0
        dropped_ids = []
        if min_drive > 0:
            kept = {}
            for k, v in union.items():
                if ego_displacement(v) < min_drive:
                    dropped += 1
                    dropped_ids.append(k)
                else:
                    kept[k] = v
            if dropped_ids:
                preview = ", ".join(str(x) for x in dropped_ids[:10])
                more = f" (+{len(dropped_ids)-10} more)" if len(dropped_ids) > 10 else ""
                print(f"  scenario {sid}: dropped {dropped} static scene(s) < {min_drive}m: [{preview}{more}]",
                      file=sys.stderr)
            union = kept
        if not union:
            out[sid] = {"n": 0, "dropped": dropped, "routes": found_routes,
                        "cr": float("nan"), "os": float("nan"),
                        "ade": float("nan")}
            continue
        scores = get_route_scores({k: v for k, v in union.items()})
        # ADE is defined over pairs of scenes generated for the SAME scenario
        # (same base behavior + route). Pooling absolute positions across
        # different routes inflates it by orders of magnitude.
        if ade_root:
            ade_union = load_union_capture(ade_root, sid, routes=routes)
            ade_groups = {}
            for (log_name, _data_id), seq in ade_union.items():
                ade_groups.setdefault(log_name, []).append((_data_id, adversary_xy(seq)))
            if ade_tail > 0:
                # diversity of the converged round only: keep the N highest
                # data_ids per (behavior, route) group
                trimmed = {}
                for log_name, pairs in ade_groups.items():
                    pairs = sorted(pairs, key=lambda kv: kv[0])[-ade_tail:]
                    trimmed[log_name] = [t for _i, t in pairs]
                groups = trimmed
            else:
                groups = {k: [t for _i, t in v] for k, v in ade_groups.items()}
        else:
            groups = {}
            for (log_name, _data_id), seq in union.items():
                groups.setdefault(log_name, []).append(adversary_xy(seq))
        per_group = []
        for trajs in groups.values():
            trajs = [t for t in trajs if len(t) > 0]
            a, _n = mean_pairwise_ade(trajs)
            if not np.isnan(a):
                per_group.append(a)
        ade = float(np.mean(per_group)) if per_group else float("nan")
        out[sid] = {"n": len(union), "dropped": dropped, "routes": found_routes,
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
        drop = f" (-{s['dropped']} static)" if s.get("dropped") else ""
        print(f"{sid:8d} | {s['n']:8d}{drop} | {s['routes']} | "
              f"{s['cr']:.3f} | {s['os']:.3f} | {s['ade']:.3f}")
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
    ap.add_argument("--routes", default=None,
                    help="optional comma-separated route ids (e.g. 8,9); "
                         "filters both eval and --ade-root records")
    ap.add_argument("--ade-tail", type=int, default=0,
                    help="with --ade-root, use only the N highest data_ids "
                         "per (behavior, route) = converged round; 0 = all")
    ap.add_argument("--ade-root", default=None,
                    help="train_scenario tree to compute ADE over the full "
                         "generated scene population (ego-independent)")
    ap.add_argument("--min-drive", type=float, default=0.0,
                    help="exclude deadlock-static scenes whose ego "
                         "displacement is below this (meters); 0 disables")
    args = ap.parse_args()

    scen_ids = [int(s) for s in args.scenarios.split(",") if s.strip()]
    routes = None
    if args.routes:
        routes = {int(s) for s in args.routes.split(",") if s.strip()}
    egos = args.ego or [f"ego{i}" for i in range(len(args.eval_root))]
    if len(egos) != len(args.eval_root):
        ap.error("--ego count must match --eval-root count")
    per_ego = {}
    for root, ego in zip(args.eval_root, egos):
        summary = summarize(root, scen_ids, min_drive=args.min_drive,
                            ade_root=args.ade_root, ade_tail=args.ade_tail,
                            routes=routes)
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

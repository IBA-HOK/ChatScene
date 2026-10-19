#!/usr/bin/env python
"""Table 1 statistics (CR / OS / ADE) from eval logs.

Reads <eval_root>/<policy>/*/eval_scenic/scenario_<id>/*/eval_results/
`OPT_*_results.pkl` (CR, OS) and `OPT_*_records.pkl` (ADE from adversary
trajectories), and prints per-base-scenario means plus an overall average.

Definitions (documented because the paper states them only qualitatively):
  CR  = collided scenes / total scenes. Per-file collisions are recovered as
        round(collision_rate * n_scenes) from the paired records file.
  OS  = mean of results.pkl `final_score` (SafeBench overall score, lower
        means more safety-critical), weighted by scene count.
  ADE = mean pairwise displacement error between adversary (x, y)
        trajectories within the same base scenario. Trajectories are
        truncated to the shortest length; pairs = scenes choose 2.
        Higher means more diverse adversarial behavior.

Usage:
  python scripts/compute_table1.py [--eval-root log/adv_train/eval]
      [--scenarios 1 2 3 4 5 6 7 8] [--routes 8 9] [--out table1.json]
"""
import argparse
import glob
import json
import os
import sys
from itertools import combinations

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
CARLA_ROOT = os.environ.get('CARLA_ROOT', '/home/hokuto/carla')
for sub in ('PythonAPI/carla/dist', 'PythonAPI/carla/agents',
            'PythonAPI/carla', 'PythonAPI'):
    d = os.path.join(CARLA_ROOT, sub)
    if os.path.isdir(d) and d not in sys.path:
        sys.path.insert(0, d)
for egg in glob.glob(os.path.join(CARLA_ROOT, 'PythonAPI/carla/dist/carla-*.egg')):
    if egg not in sys.path:
        sys.path.insert(0, egg)

import joblib
import numpy as np


def find_policy_dirs(eval_root):
    return sorted(d for d in glob.glob(os.path.join(eval_root, '*'))
                  if os.path.isdir(d))


def collect_files(eval_root, policy, sid, routes):
    pat = os.path.join(eval_root, policy, '*', 'eval_scenic',
                       f'scenario_{sid}', '*', 'eval_results',
                       'OPT_*_records.pkl')
    out = []
    for f in sorted(glob.glob(pat)):
        base = os.path.basename(f)
        try:
            route = int(base.split('ROUTE-')[1].split('_')[0])
        except (IndexError, ValueError):
            continue
        if route in routes:
            out.append(f)
    return out


def adv_xy(records, data_id):
    seq = records[data_id]
    xs, ys = [], []
    for step in seq:
        for k in step.keys():
            if isinstance(k, str) and k.startswith('adv_agent_'):
                xs.append(step[k]['x'])
                ys.append(step[k]['y'])
                break
    return np.array(xs, dtype=float), np.array(ys, dtype=float)


def pairwise_ade(trajs):
    if len(trajs) < 2:
        return float('nan')
    n = min(len(t[0]) for t in trajs)
    if n == 0:
        return float('nan')
    arr = np.stack([np.stack([t[0][:n], t[1][:n]], axis=1) for t in trajs])
    errs = [np.mean(np.linalg.norm(a - b, axis=1))
            for a, b in combinations(arr, 2)]
    return float(np.mean(errs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--eval-root', default=os.path.join(ROOT_DIR, 'log', 'adv_train', 'eval'))
    ap.add_argument('--scenarios', nargs='*', type=int, default=[1, 2, 3, 4, 5, 6, 7, 8])
    ap.add_argument('--routes', nargs='*', type=int, default=[8, 9])
    ap.add_argument('--policies', nargs='*', default=None)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    policies = args.policies or [os.path.basename(d)
                                 for d in find_policy_dirs(args.eval_root)]
    table = {}
    for policy in policies:
        table[policy] = {}
        for sid in args.scenarios:
            files = collect_files(args.eval_root, policy, sid, set(args.routes))
            n_col, n_all, os_sum, trajs, n_files = 0, 0, 0.0, [], 0
            for rec_f in files:
                res_f = rec_f.replace('_records.pkl', '_results.pkl')
                if not os.path.isfile(res_f):
                    continue
                try:
                    records = joblib.load(rec_f)
                    scores = joblib.load(res_f)
                except Exception as e:
                    print(f'skip {rec_f}: {e}')
                    continue
                ids = list(records.keys())
                n = len(ids)
                n_all += n
                n_col += int(round(float(scores.get('collision_rate', 0.0)) * n))
                os_sum += float(scores.get('final_score', float('nan'))) * n
                n_files += 1
                for i in ids:
                    try:
                        trajs.append(adv_xy(records, i))
                    except (KeyError, TypeError):
                        pass
            table[policy][sid] = {
                'n_scenes': n_all,
                'n_files': n_files,
                'CR': (n_col / n_all) if n_all else float('nan'),
                'OS': (os_sum / n_all) if n_all else float('nan'),
                'ADE': pairwise_ade(trajs),
            }
    for policy, rows in table.items():
        print(f'== policy: {policy} (routes {args.routes}) ==')
        print(f"{'scenario':>10} {'scenes':>7} {'CR(up)':>8} {'OS(down)':>9} {'ADE(up)':>8}")
        crs, oss, ades = [], [], []
        for sid in args.scenarios:
            r = rows[sid]
            print(f"{sid:>10} {r['n_scenes']:>7} {r['CR']:>8.3f} {r['OS']:>9.3f} {r['ADE']:>8.3f}")
            crs.append(r['CR'])
            oss.append(r['OS'])
            ades.append(r['ADE'])
        print(f"{'avg':>10} {'':>7} {np.nanmean(crs):>8.3f} {np.nanmean(oss):>9.3f} {np.nanmean(ades):>8.3f}")
    if args.out:
        with open(args.out, 'w') as f:
            json.dump(table, f, indent=2, default=str)
        print('wrote', args.out)


if __name__ == '__main__':
    main()

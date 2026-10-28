#!/usr/bin/env python
"""Offline L1/L2 avoidability audit for SafeBench collision records.

Examples
--------
    python tools/avoidability_audit.py \
        --records 'log/.../OPT_behavior_*_opt_ROUTE-9_records.pkl' \
        --routes 8,9 --scenarios 1,3,5
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import os
import re
from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from safebench.util.avoidability import AvoidabilityConfig, SceneAudit, scene_audit

_META_RE = re.compile(r"OPT_behavior_(\d+)_opt_ROUTE-(\d+)_records\.pkl$")
_SCENARIO_RE = re.compile(r"scenario_(\d+)")


def _expand(patterns: Iterable[str]) -> List[str]:
    files: List[str] = []
    seen: Set[str] = set()
    for pattern in patterns:
        matches = glob.glob(pattern, recursive=True)
        if not matches and os.path.isfile(pattern):
            matches = [pattern]
        for path in matches:
            if not path.endswith(".pkl"):
                continue
            real = os.path.realpath(path)
            if real in seen:
                continue
            seen.add(real)
            files.append(path)
    return sorted(files)


def _meta(path: str) -> Dict[str, Any]:
    match = _META_RE.search(os.path.basename(path))
    scenario = _SCENARIO_RE.search(path)
    return {
        "file": path,
        "scenario": int(scenario.group(1)) if scenario else None,
        "behavior": int(match.group(1)) if match else None,
        "route": int(match.group(2)) if match else None,
    }


def _load(path: str) -> Mapping[Any, Sequence[Mapping[str, Any]]]:
    import joblib

    data = joblib.load(path)
    if isinstance(data, Mapping):
        return data
    if isinstance(data, (list, tuple)):
        return {index: seq for index, seq in enumerate(data)}
    raise TypeError("{}: expected dict/list, got {}".format(path, type(data).__name__))


def _percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * pct / 100.0
    low = int(math.floor(pos))
    high = int(math.ceil(pos))
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def _stats(values: List[float]) -> Dict[str, Any]:
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "mean": sum(values) / len(values),
        "min": min(values),
        "p10": _percentile(values, 10),
        "p25": _percentile(values, 25),
        "p50": _percentile(values, 50),
        "p75": _percentile(values, 75),
        "p90": _percentile(values, 90),
        "max": max(values),
        "below_0_25": sum(v < 0.25 for v in values),
        "below_0_50": sum(v < 0.50 for v in values),
    }


def _row(meta: Dict[str, Any], data_id: Any, audit: SceneAudit) -> Dict[str, Any]:
    row = dict(meta)
    row["data_id"] = data_id
    payload = asdict(audit)
    payload["l1_reasons"] = ";".join(payload["l1_reasons"])
    row.update(payload)
    return row


def _summarize(
    audits: List[Tuple[Dict[str, Any], Any, SceneAudit]],
    files: int,
) -> Dict[str, Any]:
    collisions = [(meta, did, audit) for meta, did, audit in audits if audit.collision]
    passed = [audit for _, _, audit in collisions if audit.l1_pass]
    reasons: Dict[str, int] = {}
    for _, _, audit in collisions:
        for reason in audit.l1_reasons:
            reasons[reason] = reasons.get(reason, 0) + 1
    avoid = [a.avoidability for a in passed if a.avoidability is not None]
    by_scenario: Dict[str, Any] = {}
    for sid in sorted({meta["scenario"] for meta, _, _ in collisions if meta["scenario"] is not None}):
        subset = [a for meta, _, a in collisions if meta["scenario"] == sid]
        sub_pass = [a for a in subset if a.l1_pass]
        by_scenario[str(sid)] = {
            "collisions": len(subset),
            "l1_pass": len(sub_pass),
            "avoidability": _stats([a.avoidability for a in sub_pass if a.avoidability is not None]),
            "reasons": {
                reason: sum(reason in a.l1_reasons for a in subset)
                for reason in sorted({r for a in subset for r in a.l1_reasons})
            },
        }

    keys = sorted({
        (meta["scenario"], meta["behavior"], meta["route"])
        for meta, _, _ in collisions
        if meta["scenario"] is not None and meta["behavior"] is not None and meta["route"] is not None
    })
    by_group: Dict[str, Any] = {}
    for sid, behavior, route in keys:
        subset = [
            a for meta, _, a in collisions
            if (meta["scenario"], meta["behavior"], meta["route"]) == (sid, behavior, route)
        ]
        sub_pass = [a for a in subset if a.l1_pass]
        values = [a.avoidability for a in sub_pass if a.avoidability is not None]
        by_group["{}/{}/r{}".format(sid, behavior, route)] = {
            "collisions": len(subset),
            "l1_pass": len(sub_pass),
            "low_avoidability": sum(v < 0.5 for v in values),
            "avoidability": _stats(values),
        }
    below = [key for key, value in by_group.items() if value["l1_pass"] < 2]
    return {
        "files": files,
        "scenes": len(audits),
        "collisions": len(collisions),
        "no_collision": len(audits) - len(collisions),
        "l1_pass": len(passed),
        "l1_reject": len(collisions) - len(passed),
        "l1_reasons": reasons,
        "avoidability_l1_pass": _stats(avoid),
        "by_scenario": by_scenario,
        "by_group": by_group,
        "groups": {
            "total": len(by_group),
            "with_at_least_select_num": sum(v["l1_pass"] >= 2 for v in by_group.values()),
            "below_select_num": below,
            "select_num": 2,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit L1 hard / L2 soft avoidability on records")
    parser.add_argument("--records", nargs="+", required=True)
    parser.add_argument("--scenarios", default="1,3,5")
    parser.add_argument("--routes", default="8,9")
    parser.add_argument("--csv-out", default="results/avoidability/collisions.csv")
    parser.add_argument("--summary-out", default="results/avoidability/summary.json")
    args = parser.parse_args()

    scenarios = {int(x) for x in args.scenarios.split(",") if x.strip()}
    routes = {int(x) for x in args.routes.split(",") if x.strip()}
    files = [
        path for path in _expand(args.records)
        if _meta(path)["scenario"] in scenarios and _meta(path)["route"] in routes
    ]
    if not files:
        print("error: no matching records")
        return 2

    config = AvoidabilityConfig()
    audits: List[Tuple[Dict[str, Any], Any, SceneAudit]] = []
    for path in files:
        meta = _meta(path)
        records = _load(path)
        for data_id, sequence in records.items():
            audits.append((meta, data_id, scene_audit(sequence, config)))

    summary = _summarize(audits, len(files))
    summary["config"] = config.as_dict()

    os.makedirs(os.path.dirname(os.path.abspath(args.csv_out)), exist_ok=True)
    rows = [_row(meta, did, audit) for meta, did, audit in audits if audit.collision]
    fields = list(rows[0].keys()) if rows else []
    with open(args.csv_out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    os.makedirs(os.path.dirname(os.path.abspath(args.summary_out)), exist_ok=True)
    with open(args.summary_out, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print(json.dumps(summary, indent=2, sort_keys=True))
    print(">> wrote {}".format(args.csv_out))
    print(">> wrote {}".format(args.summary_out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

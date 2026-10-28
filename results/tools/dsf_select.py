#!/usr/bin/env python
"""Offline audit for DSF-based scenario selection.

This tool reads existing ``*_records.pkl`` files, recomputes DSF / TTC / DRAC
for every recorded scene, and shows which scenes the DSF selector would pick.
It does not need CARLA, but loading SafeBench pickles may require the CARLA
PythonAPI on ``PYTHONPATH`` because the records contain SafeBench ``Status``
objects.

Examples
--------
    python tools/dsf_select.py \
        --records 'log/.../OPT_behavior_1_opt_ROUTE-8_records.pkl'

    python tools/dsf_select.py \
        --records 'log/.../scenario_1/**/*_records.pkl' \
        --top-k-percent 10 --select-num 2 --csv-out /tmp/dsf.csv
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import sys
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from safebench.util.dsf import (
    DSFConfig,
    metrics_for_json,
    select_scene_ids_with_info,
)


_RECORD_RE = re.compile(
    r"OPT_behavior_(?P<behavior>\d+)_opt_ROUTE-(?P<route>\d+)_records\.pkl$"
)
_SCENARIO_RE = re.compile(r"scenario_(?P<scenario>\d+)")


def _load_records(path: str) -> Mapping[Any, Sequence[Mapping[str, Any]]]:
    import joblib

    data = joblib.load(path)
    if isinstance(data, Mapping):
        return data
    if isinstance(data, (list, tuple)):
        return {index: sequence for index, sequence in enumerate(data)}
    raise TypeError(
        f"{path}: expected a dict of data_id -> record sequence, "
        f"got {type(data).__name__}"
    )


def _record_meta(path: str) -> Dict[str, Any]:
    name = os.path.basename(path)
    match = _RECORD_RE.search(name)
    scenario_match = _SCENARIO_RE.search(path)
    return {
        "file": path,
        "behavior": int(match.group("behavior")) if match else None,
        "route": int(match.group("route")) if match else None,
        "scenario": int(scenario_match.group("scenario")) if scenario_match else None,
    }


def _expand_records(patterns: Iterable[str]) -> List[str]:
    files: List[str] = []
    seen = set()
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


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        if value != value:
            return "nan"
        if value == float("inf"):
            return "inf"
        return f"{value:.4f}"
    return str(value)


def _legacy_score_function():
    """Return get_route_scores when available, else None.

    The selector only needs it for the final legacy fallback ordering.  An
    import failure must not prevent an offline DSF audit.
    """
    try:
        from safebench.util.metric_util import get_route_scores

        return get_route_scores
    except Exception as exc:  # pragma: no cover - environment dependent
        print(
            f"warning: get_route_scores unavailable ({exc}); "
            "legacy fallback will use collision/non-collision order",
            file=sys.stderr,
        )
        return None


def _write_csv(path: str, rows: List[Dict[str, Any]]) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    fields = [
        "file",
        "scenario",
        "behavior",
        "route",
        "data_id",
        "rank",
        "dsf_max",
        "dsf_at_ego_max",
        "ttc_min",
        "drac_max",
        "collision",
        "feasible",
        "top_k",
        "selected",
    ]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def audit_file(
    path: str,
    config: DSFConfig,
    select_num: int,
    score_function: Optional[Any],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    records = _load_records(path)
    selected, info = select_scene_ids_with_info(
        records, select_num, config, score_function
    )
    meta = _record_meta(path)
    selected_set = set(selected)
    top_set = set(info["top_k_ids"])
    rank_of = {data_id: rank for rank, data_id in enumerate(info["ranked"], 1)}

    rows: List[Dict[str, Any]] = []
    for data_id, metrics in info["metrics"].items():
        rows.append(
            {
                **meta,
                "data_id": data_id,
                "rank": rank_of.get(data_id),
                "dsf_max": metrics["dsf_max"],
                "dsf_at_ego_max": metrics["dsf_at_ego_max"],
                "ttc_min": metrics["ttc_min"],
                "drac_max": metrics["drac_max"],
                "collision": metrics["collision"],
                "feasible": metrics["feasible"],
                "top_k": data_id in top_set,
                "selected": data_id in selected_set,
            }
        )
    rows.sort(key=lambda row: (str(row["data_id"])))

    summary = {
        **meta,
        "n": len(records),
        "select_num": select_num,
        "top_k": info["top_k"],
        "feasible_count": info["feasible_count"],
        "filled_from_all_feasible": info["filled_from_all_feasible"],
        "fallback_non_collision": info["fallback_non_collision"],
        "fallback_legacy": info["fallback_legacy"],
        "selected": selected,
        "config": info["config"],
        "metrics": {
            str(data_id): metrics
            for data_id, metrics in info["metrics"].items()
        },
    }
    return summary, rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit DSF/TTC/DRAC selection on existing SafeBench records"
    )
    parser.add_argument(
        "--records",
        nargs="+",
        required=True,
        help="record pickle path(s) or glob(s); repeatable",
    )
    parser.add_argument(
        "--top-k-percent",
        type=float,
        default=10.0,
        help="DSF percentile filter (default: 10)",
    )
    parser.add_argument(
        "--select-num",
        type=int,
        default=2,
        help="number of scenes to select (default: 2)",
    )
    parser.add_argument(
        "--speed-unit",
        choices=("kmh", "ms"),
        default="kmh",
        help="speed unit used by the DSF formula (default: kmh)",
    )
    parser.add_argument("--ttc-min", type=float, default=1.0)
    parser.add_argument("--drac-max", type=float, default=4.0)
    parser.add_argument(
        "--no-collision-filter",
        action="store_true",
        help="allow collision scenes to be feasible (diagnostic only)",
    )
    parser.add_argument(
        "--csv-out",
        default=None,
        help="optional CSV output path (one row per data_id)",
    )
    parser.add_argument(
        "--json-out",
        default=None,
        help="optional JSON output path (summary + metrics)",
    )
    args = parser.parse_args()

    files = _expand_records(args.records)
    if not files:
        print("error: no matching *_records.pkl files", file=sys.stderr)
        return 2

    config = DSFConfig(
        top_k_percent=args.top_k_percent,
        speed_unit=args.speed_unit,
        ttc_min_s=args.ttc_min,
        drac_max_mps2=args.drac_max,
        require_no_collision=not args.no_collision_filter,
    )
    score_function = _legacy_score_function()

    all_rows: List[Dict[str, Any]] = []
    summaries: List[Dict[str, Any]] = []
    failures = 0
    for path in files:
        try:
            summary, rows = audit_file(
                path, config, args.select_num, score_function
            )
        except Exception as exc:
            failures += 1
            print(f"error: {path}: {exc}", file=sys.stderr)
            continue
        summaries.append(summary)
        all_rows.extend(rows)
        print(
            f"{path}\n"
            f"  n={summary['n']} top_k={summary['top_k']} "
            f"feasible={summary['feasible_count']} "
            f"selected={summary['selected']} "
            f"filled_all_feasible={summary['filled_from_all_feasible']} "
            f"fallback_non_collision={summary['fallback_non_collision']} "
            f"fallback_legacy={summary['fallback_legacy']}"
        )
        for data_id in summary["selected"]:
            metrics = summary["metrics"][str(data_id)]
            print(
                f"    id={data_id} dsf={_fmt(metrics['dsf_max'])} "
                f"ttc={_fmt(metrics['ttc_min'])} "
                f"drac={_fmt(metrics['drac_max'])} "
                f"collision={metrics['collision']}"
            )

    if args.csv_out:
        _write_csv(args.csv_out, all_rows)
        print(f">> wrote CSV: {args.csv_out}")
    if args.json_out:
        json_files = []
        for summary in summaries:
            safe_summary = dict(summary)
            safe_summary["metrics"] = {
                data_id: metrics_for_json(metrics)
                for data_id, metrics in summary["metrics"].items()
            }
            json_files.append(safe_summary)
        _write_json(
            args.json_out,
            {
                "files": json_files,
                "config": config.as_dict(),
            },
        )
        print(f">> wrote JSON: {args.json_out}")

    if failures:
        print(f"error: {failures}/{len(files)} file(s) failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

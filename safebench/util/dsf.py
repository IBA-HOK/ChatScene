"""Driving Safety Field (DSF) scoring for ChatScene scene selection.

This module is deliberately free of CARLA / Scenic imports so it can be
used from the training runner, offline analysis tools, and unit tests.

Formula (midterm slide 9, calibrated by Li, Wang & Wu 2017):

    E_bj = (1 + 6.02e-7 * v_b^2.877) * exp(0.05 * v_b * cos(theta_b))
           / |r_bj|^1.5

where
    v_b       : speed of moving object b (km/h by default; see ``speed_unit``)
    theta_b   : angle between b's velocity vector and r_bj
    r_bj      : vector from b to the evaluation point j
    |r_bj|    : distance in metres

The midterm proposal evaluates the adversary field and the ego field at the
same point and sums them, then takes the maximum over time.  The default
evaluation point is the midpoint between ego and adversary, which keeps both
fields finite (the field of an object at its own centre is singular).

Selection rule (midterm slide 10):

    DSF_max in top-k%  AND  TTC_min >= 1.0 s  AND  DRAC_max <= 4.0 m/s^2

Collision scenes are excluded by default because they are not avoidable.
The module never mutates its inputs and has no global state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


# Calibration constants from the midterm slide / Li et al. (2017).
DSF_SPEED_COEFF = 6.02e-7
DSF_SPEED_EXP = 2.877
DSF_ANGLE_COEFF = 0.05
DSF_DISTANCE_EXP = 1.5
KMH_PER_MS = 3.6

_EPS = 1e-6


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(out):
        return default
    return out


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "on", "y"):
            return True
        if lowered in ("0", "false", "no", "off", "n", ""):
            return False
    return bool(value)


def is_collision(value: Any) -> bool:
    """Return True for SafeBench ``Status.FAILURE`` without importing CARLA.

    Records produced by ``scenic_scenario.py`` store the ``Status`` enum
    directly; offline JSON/CSV conversions may store a string or bool.
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    name = getattr(value, "name", None)
    if name is not None:
        return str(name).upper() == "FAILURE"
    text = str(value).strip()
    return text in ("Status.FAILURE", "FAILURE", "True", "true", "1")


@dataclass(frozen=True)
class DSFConfig:
    """Configuration for DSF scoring and selection.

    ``top_k_percent`` is the DSF percentile filter, not the number of scenes
    finally selected (that is ``select_num`` from the scenario YAML).
    """

    top_k_percent: float = 10.0
    speed_unit: str = "kmh"
    eval_point: str = "midpoint"
    ttc_min_s: float = 1.0
    drac_max_mps2: float = 4.0
    require_no_collision: bool = True
    fill_from_all_feasible: bool = True
    param_update: bool = True
    drac_gap_offset_m: float = 0.0
    min_adv_count: int = 1
    eps: float = 1e-3

    @classmethod
    def from_mapping(cls, mapping: Optional[Mapping[str, Any]]) -> "DSFConfig":
        if not isinstance(mapping, Mapping):
            return cls()
        get = mapping.get
        speed_unit = str(get("speed_unit", cls.speed_unit)).strip().lower()
        if speed_unit in ("km/h", "kph"):
            speed_unit = "kmh"
        eval_point = str(get("eval_point", cls.eval_point)).strip().lower()
        if eval_point not in ("midpoint", "ego", "adv", "adversary"):
            eval_point = "midpoint"
        if eval_point == "adversary":
            eval_point = "adv"
        return cls(
            top_k_percent=max(0.0, _as_float(get("top_k_percent"), cls.top_k_percent)),
            speed_unit=speed_unit if speed_unit in ("kmh", "ms") else "kmh",
            eval_point=eval_point,
            ttc_min_s=max(0.0, _as_float(get("ttc_min_s"), cls.ttc_min_s)),
            drac_max_mps2=max(0.0, _as_float(get("drac_max_mps2"), cls.drac_max_mps2)),
            require_no_collision=_as_bool(get("require_no_collision"), cls.require_no_collision),
            fill_from_all_feasible=_as_bool(get("fill_from_all_feasible"), cls.fill_from_all_feasible),
            param_update=_as_bool(get("param_update"), cls.param_update),
            drac_gap_offset_m=max(0.0, _as_float(get("drac_gap_offset_m"), cls.drac_gap_offset_m)),
            min_adv_count=max(0, int(_as_float(get("min_adv_count"), cls.min_adv_count))),
            eps=max(1e-9, _as_float(get("eps"), cls.eps)),
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "top_k_percent": self.top_k_percent,
            "speed_unit": self.speed_unit,
            "eval_point": self.eval_point,
            "ttc_min_s": self.ttc_min_s,
            "drac_max_mps2": self.drac_max_mps2,
            "require_no_collision": self.require_no_collision,
            "fill_from_all_feasible": self.fill_from_all_feasible,
            "param_update": self.param_update,
            "drac_gap_offset_m": self.drac_gap_offset_m,
            "min_adv_count": self.min_adv_count,
            "eps": self.eps,
        }


def _velocity_vector(speed: float, yaw_deg: float) -> Tuple[float, float]:
    yaw = math.radians(yaw_deg)
    return speed * math.cos(yaw), speed * math.sin(yaw)


def _adv_states(step: Mapping[str, Any]) -> List[Tuple[str, Mapping[str, Any]]]:
    keys = sorted(
        key for key in step.keys()
        if isinstance(key, str) and key.startswith("adv_agent_")
    )
    out: List[Tuple[str, Mapping[str, Any]]] = []
    for key in keys:
        value = step.get(key)
        if isinstance(value, Mapping):
            out.append((key, value))
    return out


def dsf_value(
    speed_ms: float,
    cos_theta: float,
    distance_m: float,
    config: Optional[DSFConfig] = None,
) -> float:
    """Field strength of one moving object at a point.

    ``speed_ms`` is metres/second; conversion to km/h happens here when
    ``config.speed_unit == 'kmh'`` (the calibrated default).
    """
    cfg = config or DSFConfig()
    speed = max(0.0, _as_float(speed_ms))
    distance = max(cfg.eps, _as_float(distance_m))
    if speed <= 0.0:
        return 1.0 / (distance ** DSF_DISTANCE_EXP)
    v = speed * KMH_PER_MS if cfg.speed_unit == "kmh" else speed
    speed_term = 1.0 + DSF_SPEED_COEFF * (v ** DSF_SPEED_EXP)
    angle_term = math.exp(
        max(-50.0, min(50.0, DSF_ANGLE_COEFF * v * max(-1.0, min(1.0, cos_theta))))
    )
    return speed_term * angle_term / (distance ** DSF_DISTANCE_EXP)


def _cos_angle(vec_a: Tuple[float, float], vec_b: Tuple[float, float]) -> float:
    norm_a = math.hypot(*vec_a)
    norm_b = math.hypot(*vec_b)
    if norm_a <= _EPS or norm_b <= _EPS:
        return 0.0
    dot = vec_a[0] * vec_b[0] + vec_a[1] * vec_b[1]
    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))


def _point_and_field(
    ego_pos: Tuple[float, float],
    ego_vel: Tuple[float, float],
    adv_pos: Tuple[float, float],
    adv_vel: Tuple[float, float],
    config: DSFConfig,
) -> Tuple[float, float]:
    """Return (pair_dsf_sum, adversary_field_at_ego).

    ``pair_dsf_sum`` is the midterm "sum of adversary and ego fields at the
    same time and same point".  The point is normally the midpoint; modes
    ``ego`` / ``adv`` are diagnostics and omit the singular self-field.
    """
    mode = config.eval_point
    if mode == "ego":
        point = ego_pos
    elif mode == "adv":
        point = adv_pos
    else:
        point = ((ego_pos[0] + adv_pos[0]) * 0.5,
                 (ego_pos[1] + adv_pos[1]) * 0.5)

    r_adv = (point[0] - adv_pos[0], point[1] - adv_pos[1])
    r_ego = (point[0] - ego_pos[0], point[1] - ego_pos[1])
    adv_dist = math.hypot(*r_adv)
    ego_dist = math.hypot(*r_ego)

    adv_field = dsf_value(
        math.hypot(*adv_vel),
        _cos_angle(adv_vel, r_adv),
        adv_dist,
        config,
    )
    if mode == "ego":
        return adv_field, adv_field
    if mode == "adv":
        ego_field = dsf_value(
            math.hypot(*ego_vel), _cos_angle(ego_vel, r_ego), ego_dist, config
        )
        return ego_field, 0.0

    ego_field = dsf_value(
        math.hypot(*ego_vel), _cos_angle(ego_vel, r_ego), ego_dist, config
    )
    return adv_field + ego_field, adv_field


def compute_scene_metrics(
    sequence: Sequence[Mapping[str, Any]],
    config: Optional[DSFConfig] = None,
) -> Dict[str, Any]:
    """Compute DSF / TTC / DRAC for one recorded scene trajectory.

    The input is the SafeBench ``records.pkl`` sequence for a single scene.
    Missing fields are treated as zero; the function never raises on partial
    records, so legacy logs can be analysed offline.
    """
    cfg = config or DSFConfig()
    seq = list(sequence or [])
    if not seq:
        return {
            "dsf_max": 0.0,
            "dsf_at_ego_max": 0.0,
            "ttc_min": float("inf"),
            "drac_max": 0.0,
            "collision": False,
            "feasible": False,
            "n_steps": 0,
            "n_adv": 0,
        }

    dsf_max = 0.0
    dsf_at_ego_max = 0.0
    ttc_min = float("inf")
    drac_max = 0.0
    collision = False
    n_adv_max = 0

    for step in seq:
        if is_collision(step.get("collision")):
            collision = True
        adv_states = _adv_states(step)
        n_adv_max = max(n_adv_max, len(adv_states))
        ego_pos = (_as_float(step.get("ego_x")), _as_float(step.get("ego_y")))
        ego_vel = _velocity_vector(
            _as_float(step.get("ego_velocity")), _as_float(step.get("ego_yaw"))
        )
        pair_sum = 0.0
        for _name, adv in adv_states:
            adv_pos = (_as_float(adv.get("x")), _as_float(adv.get("y")))
            adv_vel = _velocity_vector(
                _as_float(adv.get("velocity")), _as_float(adv.get("yaw"))
            )
            pair, adv_at_ego = _point_and_field(
                ego_pos, ego_vel, adv_pos, adv_vel, cfg
            )
            pair_sum += pair
            dsf_at_ego_max = max(dsf_at_ego_max, adv_at_ego)

            rel = (ego_pos[0] - adv_pos[0], ego_pos[1] - adv_pos[1])
            distance = math.hypot(*rel)
            rel_vel = (ego_vel[0] - adv_vel[0], ego_vel[1] - adv_vel[1])
            if distance <= cfg.eps:
                closing_speed = 0.0
            else:
                closing_speed = -(
                    rel[0] * rel_vel[0] + rel[1] * rel_vel[1]
                ) / distance
            if closing_speed > _EPS:
                ttc = distance / closing_speed
                if ttc < ttc_min:
                    ttc_min = ttc
                gap = max(distance - cfg.drac_gap_offset_m, cfg.eps)
                drac = (closing_speed * closing_speed) / (2.0 * gap)
                if drac > drac_max:
                    drac_max = drac
        if pair_sum > dsf_max:
            dsf_max = pair_sum

    feasible = (
        n_adv_max >= cfg.min_adv_count
        and ttc_min >= cfg.ttc_min_s
        and drac_max <= cfg.drac_max_mps2
        and (not cfg.require_no_collision or not collision)
    )
    return {
        "dsf_max": float(dsf_max),
        "dsf_at_ego_max": float(dsf_at_ego_max),
        "ttc_min": float(ttc_min),
        "drac_max": float(drac_max),
        "collision": bool(collision),
        "feasible": bool(feasible),
        "n_steps": len(seq),
        "n_adv": int(n_adv_max),
    }


def metrics_for_json(metrics: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a JSON-safe copy (inf TTC -> null) for scene_map audit data."""
    out: Dict[str, Any] = {}
    for key, value in metrics.items():
        if isinstance(value, float) and not math.isfinite(value):
            out[key] = None
        else:
            out[key] = value
    return out


def top_k_count(n: int, percent: float) -> int:
    if n <= 0:
        return 0
    return max(1, int(math.ceil(n * max(0.0, percent) / 100.0)))


def _legacy_order(
    results: Mapping[Any, Sequence[Mapping[str, Any]]],
    score_function: Optional[Any] = None,
) -> List[Any]:
    """Best-effort replica of the original collision + final_score order."""
    collision_ids: List[Any] = []
    non_collision_ids: List[Any] = []
    for data_id, seq in results.items():
        last = seq[-1] if seq else {}
        if is_collision(last.get("collision")):
            collision_ids.append(data_id)
        else:
            non_collision_ids.append(data_id)
    if score_function is None:
        return collision_ids + non_collision_ids

    def score_of(ids: Iterable[Any]) -> List[Tuple[Any, float]]:
        out = []
        for data_id in ids:
            try:
                score = score_function({data_id: results[data_id]})
                out.append((data_id, float(score["final_score"])))
            except Exception:
                out.append((data_id, float("inf")))
        return sorted(out, key=lambda item: item[1])

    return [item[0] for item in score_of(collision_ids)] + [
        item[0] for item in score_of(non_collision_ids)
    ]


def select_scene_ids_with_info(
    results: Mapping[Any, Sequence[Mapping[str, Any]]],
    select_num: int,
    config: Optional[DSFConfig] = None,
    score_function: Optional[Any] = None,
) -> Tuple[List[Any], Dict[str, Any]]:
    """Select ``select_num`` scene ids by DSF + TTC/DRAC feasibility.

    Returns ``(sorted_ids, info)``.  ``info["metrics"]`` maps every data id to
    its DSF metrics, so the caller can log or persist an audit trail.
    """
    cfg = config or DSFConfig()
    metrics = {
        data_id: compute_scene_metrics(seq, cfg)
        for data_id, seq in results.items()
    }
    ids = sorted(metrics.keys(), key=lambda value: str(value))
    ranked = sorted(
        ids,
        key=lambda data_id: (metrics[data_id]["dsf_max"], metrics[data_id]["dsf_at_ego_max"]),
        reverse=True,
    )
    top_n = top_k_count(len(ranked), cfg.top_k_percent)
    top_ids = set(ranked[:top_n])
    feasible_top = [i for i in ranked if i in top_ids and metrics[i]["feasible"]]

    chosen: List[Any] = list(feasible_top[:select_num])
    if len(chosen) < select_num and cfg.fill_from_all_feasible:
        for data_id in ranked:
            if len(chosen) >= select_num:
                break
            if data_id not in chosen and metrics[data_id]["feasible"]:
                chosen.append(data_id)

    filled_from_all_feasible = len(chosen) > len(feasible_top[:select_num])
    fallback_non_collision = False
    if len(chosen) < select_num:
        fallback_non_collision = True
        for data_id in ranked:
            if len(chosen) >= select_num:
                break
            if data_id not in chosen and not metrics[data_id]["collision"]:
                chosen.append(data_id)

    fallback = False
    if len(chosen) < select_num:
        fallback = True
        for data_id in _legacy_order(results, score_function):
            if len(chosen) >= select_num:
                break
            if data_id not in chosen:
                chosen.append(data_id)

    info = {
        "metrics": metrics,
        "ranked": ranked,
        "top_k_ids": sorted(top_ids, key=lambda value: str(value)),
        "top_k": top_n,
        "feasible_count": sum(1 for m in metrics.values() if m["feasible"]),
        "selected": sorted(chosen, key=lambda value: str(value)),
        "filled_from_all_feasible": filled_from_all_feasible,
        "fallback_non_collision": fallback_non_collision,
        "fallback_legacy": fallback,
        "config": cfg.as_dict(),
    }
    return info["selected"], info


def select_scene_ids(
    results: Mapping[Any, Sequence[Mapping[str, Any]]],
    select_num: int,
    config: Optional[DSFConfig] = None,
    score_function: Optional[Any] = None,
) -> List[Any]:
    """Convenience wrapper returning only the selected ids."""
    selected, _info = select_scene_ids_with_info(
        results, select_num, config, score_function
    )
    return selected


def select_param_entries(
    entries: Sequence[Mapping[str, Any]],
    config: Optional[DSFConfig] = None,
) -> Tuple[List[Mapping[str, Any]], Dict[str, Any]]:
    """Choose which sampled scenes feed ``update_params`` for one chunk.

    ``entries`` items must contain ``"metrics"`` (from
    :func:`compute_scene_metrics`) and may contain ``"params"``.  The top-k%
    feasible scenes by DSF are preferred; if none are feasible, non-collision
    scenes are used, then collision scenes as a last resort.
    """
    cfg = config or DSFConfig()
    entries = list(entries)
    if not entries:
        return [], {"source": "empty", "k": 0, "feasible": 0}

    feasible = [entry for entry in entries if entry["metrics"].get("feasible")]
    non_collisions = [
        entry for entry in entries if not entry["metrics"].get("collision")
    ]
    collisions = [
        entry for entry in entries if entry["metrics"].get("collision")
    ]
    if feasible:
        pool, source = feasible, "feasible"
    elif non_collisions:
        pool, source = non_collisions, "non_collision_fallback"
    elif collisions:
        pool, source = collisions, "collision_fallback"
    else:
        pool, source = entries, "all_fallback"

    pool = sorted(
        pool, key=lambda entry: entry["metrics"].get("dsf_max", 0.0), reverse=True
    )
    k = min(len(pool), top_k_count(len(entries), cfg.top_k_percent))
    chosen = pool[:k]
    return chosen, {
        "source": source,
        "k": k,
        "feasible": len(feasible),
        "pool": len(pool),
    }

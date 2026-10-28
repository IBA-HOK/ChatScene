"""L1 hard / L2 soft avoidability audit for SafeBench scene records.

The baseline collision selector treats every collision as adversarial.  This
module separates two questions:

* L1: is the collision a degenerate artifact (spawn overlap, world/static
  actor, timeout, route already complete, actor teleport)?  Those are hard
  rejects.
* L2: how much physical avoidance margin existed at the first conflict?  This
  is a soft score.  Occlusion is deliberately not used: a hidden actor that
  becomes visible late is still a valid safety-critical scene.

The module has no CARLA or Scenic imports so it can run on recorded pickles.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from safebench.util.dsf import is_collision
from safebench.util.avoidability_types import (
    AvoidabilityConfig,
    ConflictMetrics,
    SceneAudit,
)

_EPS = 1e-6


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(out):
        return default
    return out


def _adv_states(step: Mapping[str, Any]) -> List[Tuple[str, Mapping[str, Any]]]:
    out: List[Tuple[str, Mapping[str, Any]]] = []
    for key in sorted(k for k in step if isinstance(k, str) and k.startswith("adv_agent_")):
        value = step.get(key)
        if isinstance(value, Mapping):
            out.append((key, value))
    return out


def _velocity(speed_mps: float, yaw_deg: float) -> Tuple[float, float]:
    yaw = math.radians(yaw_deg)
    return speed_mps * math.cos(yaw), speed_mps * math.sin(yaw)


def _distance(step: Mapping[str, Any], adv: Mapping[str, Any]) -> float:
    return math.hypot(
        _as_float(step.get("ego_x")) - _as_float(adv.get("x")),
        _as_float(step.get("ego_y")) - _as_float(adv.get("y")),
    )


def _nearest_adv(step: Mapping[str, Any]) -> Optional[Tuple[str, Mapping[str, Any]]]:
    advs = _adv_states(step)
    if not advs:
        return None
    return min(advs, key=lambda item: _distance(step, item[1]))


def _conflict(step_index: int, step: Mapping[str, Any], adv: Mapping[str, Any]) -> ConflictMetrics:
    ego_speed = _as_float(step.get("ego_velocity"))
    adv_speed = _as_float(adv.get("velocity"))
    ego_vel = _velocity(ego_speed, _as_float(step.get("ego_yaw")))
    adv_vel = _velocity(adv_speed, _as_float(adv.get("yaw")))
    rel = (
        _as_float(step.get("ego_x")) - _as_float(adv.get("x")),
        _as_float(step.get("ego_y")) - _as_float(adv.get("y")),
    )
    distance = math.hypot(*rel)
    rel_vel = (ego_vel[0] - adv_vel[0], ego_vel[1] - adv_vel[1])
    if distance <= _EPS:
        closing = 0.0
    else:
        closing = max(0.0, -(rel[0] * rel_vel[0] + rel[1] * rel_vel[1]) / distance)
    if distance <= _EPS:
        ttc = 0.0
    elif closing > _EPS:
        ttc = distance / closing
    else:
        ttc = float("inf")
    drac = (closing * closing) / (2.0 * max(distance, _EPS))
    return ConflictMetrics(
        step_index=step_index,
        time_s=_as_float(step.get("current_game_time")),
        distance_m=distance,
        ego_speed_mps=ego_speed,
        adv_speed_mps=adv_speed,
        closing_speed_mps=closing,
        ttc_s=ttc,
        drac_mps2=drac,
    )


def _collision_index(sequence: Sequence[Mapping[str, Any]]) -> Optional[int]:
    for index, step in enumerate(sequence):
        if is_collision(step.get("collision")):
            return index
    return None


def _has_teleport(sequence: Sequence[Mapping[str, Any]], config: AvoidabilityConfig) -> bool:
    previous: Dict[str, Tuple[Tuple[float, float], float, float]] = {}
    for step in sequence:
        now = _as_float(step.get("current_game_time"))
        for name, adv in _adv_states(step):
            pos = (_as_float(adv.get("x")), _as_float(adv.get("y")))
            speed = max(_as_float(adv.get("velocity")), 0.0)
            if name in previous:
                prev_pos, prev_time, prev_speed = previous[name]
                dt = now - prev_time
                if dt > _EPS:
                    moved = math.hypot(pos[0] - prev_pos[0], pos[1] - prev_pos[1])
                    expected = max(prev_speed, speed) * dt * 2.0 + 1.0
                    if moved > max(config.teleport_distance_m, expected):
                        return True
            previous[name] = (pos, now, speed)
    return False


def _l1_reasons(
    sequence: Sequence[Mapping[str, Any]],
    collision_step: int,
    config: AvoidabilityConfig,
) -> Tuple[Tuple[str, ...], int, float, float, bool]:
    collision = sequence[collision_step]
    advs = _adv_states(collision)
    initial_adv = _nearest_adv(sequence[0])
    initial_distance = float("inf") if initial_adv is None else _distance(sequence[0], initial_adv[1])
    actor_distance = (
        float("inf") if not advs else min(_distance(collision, adv) for _, adv in advs)
    )
    collision_time = _as_float(collision.get("current_game_time"))
    route_complete = _as_float(collision.get("route_complete"))
    teleport = _has_teleport(sequence, config)
    reasons: List[str] = []
    if not advs:
        reasons.append("no_adversary")
    if actor_distance > config.collision_actor_distance_m:
        reasons.append("collision_actor_not_near")
    if initial_distance < config.initial_overlap_m:
        reasons.append("initial_overlap")
    if teleport:
        reasons.append("actor_teleport")
    if collision_time < config.min_sim_time_s:
        reasons.append("collision_before_min_sim")
    if collision_time >= config.timeout_s:
        reasons.append("collision_after_timeout")
    if route_complete >= config.route_complete_threshold:
        reasons.append("route_complete_after_collision")
    return tuple(reasons), len(advs), initial_distance, actor_distance, teleport


def _first_conflict(
    sequence: Sequence[Mapping[str, Any]],
    collision_step: int,
    actor_name: str,
    config: AvoidabilityConfig,
) -> ConflictMetrics:
    for index in range(collision_step + 1):
        step = sequence[index]
        adv = step.get(actor_name)
        if not isinstance(adv, Mapping):
            continue
        metrics = _conflict(index, step, adv)
        if (
            metrics.distance_m <= config.conflict_distance_m
            or metrics.ttc_s <= config.conflict_horizon_s
        ):
            return metrics
    collision = sequence[collision_step]
    adv = collision.get(actor_name)
    if isinstance(adv, Mapping):
        return _conflict(collision_step, collision, adv)
    return _conflict(collision_step, collision, {})


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _margin_ttc(ttc_s: float, config: AvoidabilityConfig) -> float:
    if not math.isfinite(ttc_s):
        return 1.0
    span = max(config.ttc_good_s - config.ttc_floor_s, _EPS)
    return _clip01((ttc_s - config.ttc_floor_s) / span)


def _margin_drac(drac: float, config: AvoidabilityConfig) -> float:
    span = max(config.drac_ceiling_mps2 - config.drac_good_mps2, _EPS)
    return _clip01((config.drac_ceiling_mps2 - drac) / span)


def scene_audit(
    sequence: Sequence[Mapping[str, Any]],
    config: Optional[AvoidabilityConfig] = None,
) -> SceneAudit:
    """Audit one recorded scene.  Non-collision scenes get ``collision=False``."""
    cfg = config or AvoidabilityConfig()
    seq = list(sequence)
    collision_step = _collision_index(seq)
    if collision_step is None:
        return SceneAudit(
            collision=False,
            collision_step=-1,
            collision_time_s=0.0,
            route_complete=0.0,
            n_adv=0,
            initial_distance_m=0.0,
            collision_actor_distance_m=0.0,
            actor_teleport=False,
            l1_reasons=("no_collision",),
            l1_pass=False,
            first_conflict_time_s=None,
            warning_s=None,
            ttc_conflict_s=None,
            drac_conflict_mps2=None,
            a_req_brake_mps2=None,
            brake_margin=None,
            ttc_margin=None,
            drac_margin=None,
            warning_margin=None,
            avoidability=None,
        )

    collision = seq[collision_step]
    l1_reasons, n_adv, initial_distance, actor_distance, teleport = _l1_reasons(
        seq, collision_step, cfg
    )
    nearest = _nearest_adv(collision)
    collision_time = _as_float(collision.get("current_game_time"))
    if nearest is None:
        first = None
        warning = None
        a_req = None
        brake_margin = None
        ttc_margin = None
        drac_margin = None
        warning_margin = None
        avoidability = None
    else:
        first = _first_conflict(seq, collision_step, nearest[0], cfg)
        warning = max(0.0, collision_time - first.time_s)
        a_req = (first.ego_speed_mps * first.ego_speed_mps) / (2.0 * max(first.distance_m, _EPS))
        brake_margin = _clip01(cfg.max_decel_mps2 / max(a_req, _EPS))
        ttc_margin = _margin_ttc(first.ttc_s, cfg)
        drac_margin = _margin_drac(first.drac_mps2, cfg)
        warning_margin = _clip01(warning / max(cfg.warning_good_s, _EPS))
        avoidability = min(brake_margin, ttc_margin, drac_margin, warning_margin)
    return SceneAudit(
        collision=True,
        collision_step=collision_step,
        collision_time_s=collision_time,
        route_complete=_as_float(collision.get("route_complete")),
        n_adv=n_adv,
        initial_distance_m=initial_distance,
        collision_actor_distance_m=actor_distance,
        actor_teleport=teleport,
        l1_reasons=l1_reasons,
        l1_pass=not l1_reasons,
        first_conflict_time_s=None if first is None else first.time_s,
        warning_s=warning,
        ttc_conflict_s=None if first is None else first.ttc_s,
        drac_conflict_mps2=None if first is None else first.drac_mps2,
        a_req_brake_mps2=a_req,
        brake_margin=brake_margin,
        ttc_margin=ttc_margin,
        drac_margin=drac_margin,
        warning_margin=warning_margin,
        avoidability=avoidability,
    )

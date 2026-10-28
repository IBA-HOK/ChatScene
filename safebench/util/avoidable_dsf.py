"""Dangerous-but-avoidable scene features and selection.

This is the parameter-optimization layer used by ScenicRunner.train_scenario.
It is intentionally CARLA-free: it operates on the same record dictionaries
that the runner already collects.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from safebench.util.avoidability import AvoidabilityConfig, scene_audit
from safebench.util.avoidability_types import SceneAudit
from safebench.util.dsf import DSFConfig, dsf_value, is_collision, top_k_count

_EPS = 1e-6


@dataclass(frozen=True)
class AvoidableConfig:
    """Thresholds for dangerous-but-avoidable parameter selection."""

    front_half_deg: float = 45.0
    detection_m: float = 5.0
    reaction_s: float = 0.3
    max_decel_mps2: float = 8.0
    max_lateral_mps2: float = 5.0
    max_yaw_rate: float = 1.0
    collision_radius_m: float = 2.0
    lookahead_s: float = 1.0
    band_max_m: float = 1.0
    ratio_min: float = 0.35
    explore_margin_min: float = -1.0
    reset_opt_record: bool = True
    l1: AvoidabilityConfig = AvoidabilityConfig()

    @classmethod
    def from_mapping(cls, mapping: Optional[Mapping[str, Any]]) -> "AvoidableConfig":
        if not isinstance(mapping, Mapping):
            return cls()
        get = mapping.get
        return cls(
            front_half_deg=float(get("front_half_deg", cls.front_half_deg)),
            detection_m=float(get("detection_m", cls.detection_m)),
            reaction_s=float(get("reaction_s", cls.reaction_s)),
            max_decel_mps2=float(get("max_decel_mps2", cls.max_decel_mps2)),
            max_lateral_mps2=float(get("max_lateral_mps2", cls.max_lateral_mps2)),
            max_yaw_rate=float(get("max_yaw_rate", cls.max_yaw_rate)),
            collision_radius_m=float(get("collision_radius_m", cls.collision_radius_m)),
            lookahead_s=float(get("lookahead_s", cls.lookahead_s)),
            band_max_m=float(get("band_max_m", cls.band_max_m)),
            ratio_min=float(get("ratio_min", cls.ratio_min)),
            explore_margin_min=float(get("explore_margin_min", cls.explore_margin_min)),
            reset_opt_record=bool(get("reset_opt_record", cls.reset_opt_record)),
        )

    def as_dict(self) -> Dict[str, float]:
        return {
            "front_half_deg": self.front_half_deg,
            "detection_m": self.detection_m,
            "reaction_s": self.reaction_s,
            "max_decel_mps2": self.max_decel_mps2,
            "max_lateral_mps2": self.max_lateral_mps2,
            "max_yaw_rate": self.max_yaw_rate,
            "collision_radius_m": self.collision_radius_m,
            "lookahead_s": self.lookahead_s,
            "band_max_m": self.band_max_m,
            "ratio_min": self.ratio_min,
            "explore_margin_min": self.explore_margin_min,
            "reset_opt_record": self.reset_opt_record,
        }


@dataclass(frozen=True)
class SceneFeatures:
    collision: bool
    l1_pass: bool
    status: str
    margin_m: float
    front_dsf: float
    side_dsf: float
    rear_dsf: float
    front_ratio: float
    soft_score: float
    l1_reasons: Tuple[str, ...] = ()


def _vec(speed: float, yaw_deg: float) -> Tuple[float, float]:
    yaw = math.radians(yaw_deg)
    return speed * math.cos(yaw), speed * math.sin(yaw)


def _cos_angle(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    na, nb = math.hypot(*a), math.hypot(*b)
    if na <= 1e-9 or nb <= 1e-9:
        return 0.0
    return max(-1.0, min(1.0, (a[0] * b[0] + a[1] * b[1]) / (na * nb)))


def _bearing(vec: Tuple[float, float], ego_yaw_deg: float) -> float:
    yaw = math.radians(ego_yaw_deg)
    forward = (math.cos(yaw), math.sin(yaw))
    right = (-math.sin(yaw), math.cos(yaw))
    return math.degrees(math.atan2(
        vec[0] * right[0] + vec[1] * right[1],
        vec[0] * forward[0] + vec[1] * forward[1],
    ))


def _advs(step: Mapping[str, Any]) -> List[Tuple[str, Mapping[str, Any]]]:
    return [
        (key, value)
        for key, value in sorted(step.items())
        if isinstance(key, str) and key.startswith("adv_agent_") and isinstance(value, Mapping)
    ]


def _nearest(step: Mapping[str, Any]) -> Optional[Tuple[str, Mapping[str, Any]]]:
    advs = _advs(step)
    if not advs:
        return None
    return min(
        advs,
        key=lambda item: math.hypot(
            float(step.get("ego_x", 0.0)) - float(item[1].get("x", 0.0)),
            float(step.get("ego_y", 0.0)) - float(item[1].get("y", 0.0)),
        ),
    )


def _collision_index(sequence: Sequence[Mapping[str, Any]]) -> Optional[int]:
    for i, step in enumerate(sequence):
        if is_collision(step.get("collision")):
            return i
    return None


def _fov_start(seq: Sequence[Mapping[str, Any]], cidx: int, name: str, cfg: AvoidableConfig) -> Optional[int]:
    for i in range(cidx + 1):
        step = seq[i]
        adv = step.get(name)
        if not isinstance(adv, Mapping):
            continue
        distance = math.hypot(
            float(step.get("ego_x", 0.0)) - float(adv.get("x", 0.0)),
            float(step.get("ego_y", 0.0)) - float(adv.get("y", 0.0)),
        )
        bearing = abs((_bearing(
            (float(adv.get("x", 0.0)) - float(step.get("ego_x", 0.0)),
             float(adv.get("y", 0.0)) - float(step.get("ego_y", 0.0))),
            float(step.get("ego_yaw", 0.0) or 0.0),
        ) + 180.0) % 360.0 - 180.0)
        if distance <= cfg.detection_m and bearing <= cfg.front_half_deg:
            return i
    return None


def _future_path(seq: Sequence[Mapping[str, Any]], end: int, cfg: AvoidableConfig) -> Tuple[float, float, float, float]:
    dcfg = DSFConfig()
    k_max = int(round(cfg.lookahead_s / 0.1))
    zmax = {"front": 0.0, "side": 0.0, "rear": 0.0}
    for i in range(end + 1):
        for k in range(k_max + 1):
            step = seq[min(i + k, end)]
            ego_pos = (float(step.get("ego_x", 0.0)), float(step.get("ego_y", 0.0)))
            ego_yaw = float(step.get("ego_yaw", 0.0) or 0.0)
            ego_vel = _vec(float(step.get("ego_velocity", 0.0) or 0.0), ego_yaw)
            for _, adv in _advs(step):
                adv_pos = (float(adv.get("x", 0.0)), float(adv.get("y", 0.0)))
                adv_vel = _vec(float(adv.get("velocity", 0.0) or 0.0), float(adv.get("yaw", 0.0) or 0.0))
                rel = (adv_pos[0] - ego_pos[0], adv_pos[1] - ego_pos[1])
                rel_vel = (adv_vel[0] - ego_vel[0], adv_vel[1] - ego_vel[1])
                pos_b = _bearing(rel, ego_yaw)
                app_b = _bearing((-rel_vel[0], -rel_vel[1]), ego_yaw)
                max_abs = max(abs(pos_b), abs(app_b))
                z = "front" if max_abs <= cfg.front_half_deg else ("side" if max_abs <= 135.0 else "rear")
                field = dsf_value(
                    math.hypot(*adv_vel),
                    _cos_angle(adv_vel, (-rel[0], -rel[1])),
                    math.hypot(*rel),
                    dcfg,
                )
                zmax[z] = max(zmax[z], field)
    total = zmax["front"] + zmax["side"] + zmax["rear"]
    return zmax["front"], zmax["side"], zmax["rear"], (zmax["front"] / total if total > 1e-9 else 0.0)


def _margin(seq: Sequence[Mapping[str, Any]], start: int, end: int, name: str, steer: Optional[int], cfg: AvoidableConfig) -> float:
    track = [
        (float(step.get("current_game_time", 0.0) or 0.0), float(adv.get("x", 0.0)), float(adv.get("y", 0.0)))
        for step in seq[start : end + 1]
        for adv in [step.get(name)]
        if isinstance(adv, Mapping)
    ]
    if not track:
        return -1e9
    step = seq[start]
    x = float(step.get("ego_x", 0.0))
    y = float(step.get("ego_y", 0.0))
    yaw = math.radians(float(step.get("ego_yaw", 0.0) or 0.0))
    speed = max(0.0, float(step.get("ego_velocity", 0.0) or 0.0))
    t0 = float(step.get("current_game_time", 0.0) or 0.0)
    min_dist = 1e9

    def interp(t: float) -> Tuple[float, float]:
        if t <= track[0][0]:
            return track[0][1], track[0][2]
        if t >= track[-1][0]:
            return track[-1][1], track[-1][2]
        for i in range(1, len(track)):
            a, b = track[i - 1], track[i]
            if t <= b[0]:
                alpha = (t - a[0]) / max(b[0] - a[0], 1e-9)
                return a[1] + (b[1] - a[1]) * alpha, a[2] + (b[2] - a[2]) * alpha
        return track[-1][1], track[-1][2]

    for i in range(int(5.0 / 0.1) + 1):
        t = t0 + i * 0.1
        if t >= t0 + cfg.reaction_s:
            speed = max(0.0, speed - cfg.max_decel_mps2 * 0.1)
            if steer is not None and speed > 0.1:
                yaw += min(cfg.max_lateral_mps2 / max(speed, 1.0), cfg.max_yaw_rate) * steer * 0.1
        x += speed * 0.1 * math.cos(yaw)
        y += speed * 0.1 * math.sin(yaw)
        ax, ay = interp(t)
        min_dist = min(min_dist, math.hypot(x - ax, y - ay))
        if speed <= 0.05 and t > t0 + cfg.reaction_s + 0.2:
            break
    return min_dist - cfg.collision_radius_m


def scene_features(sequence: Sequence[Mapping[str, Any]], config: Optional[AvoidableConfig] = None) -> SceneFeatures:
    """Compute L1, 5m+45 detection, avoidance margin, and path DSF."""
    cfg = config or AvoidableConfig()
    seq = list(sequence)
    cidx = _collision_index(seq)
    end = cidx if cidx is not None else len(seq) - 1
    f, s, r, ratio = _future_path(seq, end, cfg)
    soft = f - 0.5 * (s + r)
    audit: SceneAudit = scene_audit(seq, cfg.l1)
    base = {
        "collision": cidx is not None,
        "l1_pass": audit.l1_pass,
        "front_dsf": f,
        "side_dsf": s,
        "rear_dsf": r,
        "front_ratio": ratio,
        "soft_score": soft,
        "l1_reasons": audit.l1_reasons,
    }
    if cidx is None:
        return SceneFeatures(status="non_collision", margin_m=0.0, **base)
    if not audit.l1_pass:
        return SceneFeatures(status="l1_reject", margin_m=0.0, **base)
    near = _nearest(seq[cidx])
    if near is None:
        return SceneFeatures(status="not_front", margin_m=0.0, **base)
    name, _ = near
    start = _fov_start(seq, cidx, name, cfg)
    if start is None:
        return SceneFeatures(status="not_front", margin_m=0.0, **base)
    margin = max(
        _margin(seq, start, cidx, name, None, cfg),
        _margin(seq, start, cidx, name, 1, cfg),
        _margin(seq, start, cidx, name, -1, cfg),
    )
    return SceneFeatures(status="avoidable" if margin > 0 else "unavoidable", margin_m=margin, **base)


def _rank_key(features: SceneFeatures, os_score: float = 0.0) -> Tuple[float, float, float]:
    return (-features.soft_score, features.margin_m, os_score)


def _pool(entries: List[Mapping[str, Any]], cfg: AvoidableConfig, allow_noncollision: bool) -> Tuple[List[Mapping[str, Any]], str]:
    avoidable = [e for e in entries if e.get("features") and e["features"].status == "avoidable"]
    primary = [e for e in avoidable if e["features"].margin_m <= cfg.band_max_m and e["features"].front_ratio >= cfg.ratio_min]
    secondary = [e for e in avoidable if e["features"].front_ratio >= cfg.ratio_min]
    for pool, name in ((primary, "band_avoidable"), (secondary, "front_avoidable"), (avoidable, "avoidable")):
        if pool:
            return pool, name
    if allow_noncollision:
        noncol = [e for e in entries if e.get("features") and e["features"].status == "non_collision"]
        if noncol:
            return noncol, "non_collision_fallback"
    collisions = [
        e for e in entries
        if e.get("features") and e["features"].collision
        and e["features"].status == "unavoidable"
    ]
    near = [e for e in collisions if e["features"].margin_m >= cfg.explore_margin_min]
    if near:
        return near, "collision_near_miss"
    if collisions:
        return collisions, "collision_exploration"
    return [], "empty"


def select_param_entries_avoidable(entries: Sequence[Mapping[str, Any]], dsf_config: DSFConfig, config: AvoidableConfig) -> Tuple[List[Mapping[str, Any]], Dict[str, Any]]:
    items = list(entries)
    pool, source = _pool(items, config, allow_noncollision=False)
    if not pool:
        return [], {"source": source, "k": 0, "pool": 0, "avoidable": 0}
    if source == "collision_exploration":
        pool = sorted(pool, key=lambda e: (-e["features"].margin_m, -e["features"].soft_score))
    else:
        pool = sorted(pool, key=lambda e: _rank_key(e["features"]))
    k = min(len(pool), top_k_count(len(items), dsf_config.top_k_percent))
    return pool[:k], {"source": source, "k": k, "pool": len(pool), "avoidable": sum(1 for e in items if e.get("features") and e["features"].status == "avoidable")}


def select_scene_ids_avoidable(results: Mapping[Any, Sequence[Mapping[str, Any]]], select_num: int, config: AvoidableConfig, dsf_config: DSFConfig, score_function: Optional[Any] = None) -> Tuple[List[Any], Dict[str, Any]]:
    entries = []
    for data_id, seq in results.items():
        feat = scene_features(seq, config)
        os_score = 0.0
        if score_function is not None:
            try:
                os_score = float(score_function({data_id: seq})["final_score"])
            except (KeyError, TypeError, ValueError):
                os_score = 0.0
        entries.append({"data_id": data_id, "features": feat, "os": os_score})
    pool, source = _pool(entries, config, allow_noncollision=True)
    if not pool:
        return [], {"source": source, "selected": [], "status": [], "soft": [], "margin": [], "ratio": [], "counts": {}}
    pool = sorted(pool, key=lambda e: _rank_key(e["features"], float(e.get("os", 0.0))))
    selected = pool[:select_num]
    if len(selected) < select_num:
        noncol = [
            e for e in entries
            if e["features"].status == "non_collision" and e not in selected
        ]
        noncol.sort(key=lambda e: (-e["features"].soft_score, float(e.get("os", 0.0))))
        selected.extend(noncol[: select_num - len(selected)])
        source = source + "+noncollision" if len(selected) > len(pool[:select_num]) else source
    if len(selected) < select_num:
        rest = [e for e in entries if e not in selected]
        rest.sort(key=lambda e: _rank_key(e["features"], float(e.get("os", 0.0))))
        selected.extend(rest[: select_num - len(selected)])
        source = source + "+fallback" if len(selected) > len(pool[:select_num]) else source
    return [e["data_id"] for e in selected], {
        "source": source,
        "selected": [e["data_id"] for e in selected],
        "status": [e["features"].status for e in selected],
        "soft": [e["features"].soft_score for e in selected],
        "margin": [e["features"].margin_m for e in selected],
        "ratio": [e["features"].front_ratio for e in selected],
        "counts": {s: sum(1 for e in entries if e["features"].status == s) for s in ("avoidable", "unavoidable", "not_front", "l1_reject", "non_collision")},
    }

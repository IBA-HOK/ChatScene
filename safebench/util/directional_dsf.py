"""Current-frame directional DSF selection (no I45/avoidability)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from safebench.util.avoidability import AvoidabilityConfig, scene_audit
from safebench.util.dsf import DSFConfig, dsf_value, is_collision


@dataclass(frozen=True)
class DirectionalConfig:
    front_half_deg: float = 45.0
    min_front_ratio: float = 0.60

    @classmethod
    def from_mapping(cls, mapping: Optional[Mapping[str, Any]]) -> "DirectionalConfig":
        if not isinstance(mapping, Mapping):
            return cls()
        return cls(
            front_half_deg=float(mapping.get("front_half_deg", cls.front_half_deg)),
            min_front_ratio=float(mapping.get("min_front_ratio", cls.min_front_ratio)),
        )

    def as_dict(self) -> Dict[str, float]:
        return {
            "front_half_deg": self.front_half_deg,
            "min_front_ratio": self.min_front_ratio,
        }


@dataclass(frozen=True)
class DirectionFeatures:
    collision: bool
    l1_pass: bool
    status: str
    front_dsf: float
    side_dsf: float
    rear_dsf: float
    front_ratio: float
    soft_score: float


def _vec(speed: float, yaw_deg: float) -> Tuple[float, float]:
    yaw = math.radians(yaw_deg)
    return speed * math.cos(yaw), speed * math.sin(yaw)


def _cos_angle(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    na, nb = math.hypot(*a), math.hypot(*b)
    if na <= 1e-9 or nb <= 1e-9:
        return 0.0
    return max(-1.0, min(1.0, (a[0] * b[0] + a[1] * b[1]) / (na * nb)))


def _bearing(step: Mapping[str, Any], adv: Mapping[str, Any]) -> float:
    yaw = math.radians(float(step.get("ego_yaw", 0.0) or 0.0))
    rel = (
        float(adv.get("x", 0.0)) - float(step.get("ego_x", 0.0)),
        float(adv.get("y", 0.0)) - float(step.get("ego_y", 0.0)),
    )
    forward = (math.cos(yaw), math.sin(yaw))
    right = (-math.sin(yaw), math.cos(yaw))
    return math.degrees(math.atan2(
        rel[0] * right[0] + rel[1] * right[1],
        rel[0] * forward[0] + rel[1] * forward[1],
    ))


def _advs(step: Mapping[str, Any]) -> List[Tuple[str, Mapping[str, Any]]]:
    return [
        (key, value)
        for key, value in sorted(step.items())
        if isinstance(key, str) and key.startswith("adv_agent_") and isinstance(value, Mapping)
    ]


def _collision_index(sequence: Sequence[Mapping[str, Any]]) -> Optional[int]:
    for i, step in enumerate(sequence):
        if is_collision(step.get("collision")):
            return i
    return None


def scene_direction(sequence: Sequence[Mapping[str, Any]], config: Optional[DirectionalConfig] = None) -> DirectionFeatures:
    cfg = config or DirectionalConfig()
    seq = list(sequence)
    cidx = _collision_index(seq)
    audit = scene_audit(seq, AvoidabilityConfig())
    if cidx is None:
        z = {"front": 0.0, "side": 0.0, "rear": 0.0}
        for step in seq:
            for _, adv in _advs(step):
                b = abs(((_bearing(step, adv) + 180.0) % 360.0) - 180.0)
                z["front" if b <= cfg.front_half_deg else ("side" if b <= 135.0 else "rear")] += 0.0
        return DirectionFeatures(False, True, "non_collision", 0.0, 0.0, 0.0, 0.0, 0.0)
    if not audit.l1_pass:
        return DirectionFeatures(True, False, "l1_reject", 0.0, 0.0, 0.0, 0.0, 0.0)
    dcfg = DSFConfig()
    zmax = {"front": 0.0, "side": 0.0, "rear": 0.0}
    for step in seq[: cidx + 1]:
        ego_pos = (float(step.get("ego_x", 0.0)), float(step.get("ego_y", 0.0)))
        ego_vel = _vec(float(step.get("ego_velocity", 0.0) or 0.0), float(step.get("ego_yaw", 0.0) or 0.0))
        for _, adv in _advs(step):
            adv_pos = (float(adv.get("x", 0.0)), float(adv.get("y", 0.0)))
            adv_vel = _vec(float(adv.get("velocity", 0.0) or 0.0), float(adv.get("yaw", 0.0) or 0.0))
            mid = ((ego_pos[0] + adv_pos[0]) / 2.0, (ego_pos[1] + adv_pos[1]) / 2.0)
            r_adv = (mid[0] - adv_pos[0], mid[1] - adv_pos[1])
            r_ego = (mid[0] - ego_pos[0], mid[1] - ego_pos[1])
            field = (
                dsf_value(math.hypot(*adv_vel), _cos_angle(adv_vel, r_adv), math.hypot(*r_adv), dcfg)
                + dsf_value(math.hypot(*ego_vel), _cos_angle(ego_vel, r_ego), math.hypot(*r_ego), dcfg)
            )
            b = abs(((_bearing(step, adv) + 180.0) % 360.0) - 180.0)
            z = "front" if b <= cfg.front_half_deg else ("side" if b <= 135.0 else "rear")
            zmax[z] = max(zmax[z], field)
    total = zmax["front"] + zmax["side"] + zmax["rear"]
    ratio = zmax["front"] / total if total > 1e-9 else 0.0
    return DirectionFeatures(
        True, True, "collision", zmax["front"], zmax["side"], zmax["rear"],
        ratio, zmax["front"] - 0.5 * (zmax["side"] + zmax["rear"]),
    )


def select_directional(results: Mapping[Any, Sequence[Mapping[str, Any]]], select_num: int, config: DirectionalConfig, score_function: Optional[Any] = None) -> Tuple[List[Any], Dict[str, Any]]:
    entries = []
    for data_id, seq in results.items():
        feat = scene_direction(seq, config)
        os_score = 0.0
        if score_function is not None:
            try:
                os_score = float(score_function({data_id: seq})["final_score"])
            except (KeyError, TypeError, ValueError):
                os_score = 0.0
        entries.append({"id": data_id, "f": feat, "os": os_score})
    primary = [e for e in entries if e["f"].l1_pass and e["f"].collision and e["f"].front_ratio >= config.min_front_ratio]
    primary.sort(key=lambda e: (-e["f"].front_dsf, e["os"]))
    selected = primary[:select_num]
    source = "directional_front"
    if len(selected) < select_num:
        noncol = [e for e in entries if e["f"].status == "non_collision"]
        noncol.sort(key=lambda e: (-e["f"].front_dsf, e["os"]))
        selected.extend(noncol[: select_num - len(selected)])
        source = "directional_front+noncollision"
    return [e["id"] for e in selected], {
        "source": source,
        "selected": [e["id"] for e in selected],
        "status": [e["f"].status for e in selected],
        "front_dsf": [e["f"].front_dsf for e in selected],
        "front_ratio": [e["f"].front_ratio for e in selected],
        "counts": {s: sum(1 for e in entries if e["f"].status == s) for s in ("collision", "non_collision", "l1_reject")},
    }

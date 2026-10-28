"""Typed data containers for L1/L2 avoidability auditing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class AvoidabilityConfig:
    """Thresholds for L1 rejects and L2 soft margins."""

    initial_overlap_m: float = 2.0
    collision_actor_distance_m: float = 5.0
    min_sim_time_s: float = 0.5
    timeout_s: float = 15.0
    route_complete_threshold: float = 99.9
    teleport_distance_m: float = 10.0
    conflict_horizon_s: float = 3.0
    conflict_distance_m: float = 5.0
    max_decel_mps2: float = 8.0
    ttc_floor_s: float = 0.5
    ttc_good_s: float = 2.0
    drac_good_mps2: float = 4.0
    drac_ceiling_mps2: float = 10.0
    warning_good_s: float = 2.0

    def as_dict(self) -> Dict[str, float]:
        """Return a JSON-safe config mapping."""
        return {
            "initial_overlap_m": self.initial_overlap_m,
            "collision_actor_distance_m": self.collision_actor_distance_m,
            "min_sim_time_s": self.min_sim_time_s,
            "timeout_s": self.timeout_s,
            "route_complete_threshold": self.route_complete_threshold,
            "teleport_distance_m": self.teleport_distance_m,
            "conflict_horizon_s": self.conflict_horizon_s,
            "conflict_distance_m": self.conflict_distance_m,
            "max_decel_mps2": self.max_decel_mps2,
            "ttc_floor_s": self.ttc_floor_s,
            "ttc_good_s": self.ttc_good_s,
            "drac_good_mps2": self.drac_good_mps2,
            "drac_ceiling_mps2": self.drac_ceiling_mps2,
            "warning_good_s": self.warning_good_s,
        }


@dataclass(frozen=True)
class ConflictMetrics:
    """Relative state at the first conflict (or at collision)."""

    step_index: int
    time_s: float
    distance_m: float
    ego_speed_mps: float
    adv_speed_mps: float
    closing_speed_mps: float
    ttc_s: float
    drac_mps2: float


@dataclass(frozen=True)
class SceneAudit:
    """L1 decision and L2 soft margins for one scene."""

    collision: bool
    collision_step: int
    collision_time_s: float
    route_complete: float
    n_adv: int
    initial_distance_m: float
    collision_actor_distance_m: float
    actor_teleport: bool
    l1_reasons: Tuple[str, ...]
    l1_pass: bool
    first_conflict_time_s: Optional[float]
    warning_s: Optional[float]
    ttc_conflict_s: Optional[float]
    drac_conflict_mps2: Optional[float]
    a_req_brake_mps2: Optional[float]
    brake_margin: Optional[float]
    ttc_margin: Optional[float]
    drac_margin: Optional[float]
    warning_margin: Optional[float]
    avoidability: Optional[float]

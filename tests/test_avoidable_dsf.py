"""Tests for dangerous-but-avoidable DSF selection."""

from __future__ import annotations

from typing import Any, Dict, List

from safebench.util.avoidable_dsf import (
    AvoidableConfig,
    SceneFeatures,
    scene_features,
    select_param_entries_avoidable,
)
from safebench.util.dsf import DSFConfig


def _scene(
    adv_start: float = 10.0,
    steps: int = 12,
    collision_step: int = 10,
    no_adv: bool = False,
) -> List[Dict[str, Any]]:
    seq: List[Dict[str, Any]] = []
    ego_x = 0.0
    adv_x = adv_start
    for index in range(steps):
        seq.append({
            "ego_x": ego_x,
            "ego_y": 0.0,
            "ego_yaw": 0.0,
            "ego_velocity": 5.0,
            "current_game_time": 0.1 * (index + 1),
            "route_complete": 50.0,
            "collision": index >= collision_step,
            **({} if no_adv else {
                "adv_agent_0": {"x": adv_x, "y": 0.0, "yaw": 180.0, "velocity": 10.0}
            }),
        })
        ego_x += 0.5
        adv_x -= 1.0
    return seq


def test_scene_features_returns_avoidable_or_not_front() -> None:
    features = scene_features(_scene())
    assert features.collision is True
    assert features.l1_pass is True
    assert features.status in ("avoidable", "unavoidable", "not_front")
    assert features.front_ratio >= 0.0


def test_no_adversary_is_l1_reject() -> None:
    features = scene_features(_scene(no_adv=True))
    assert features.status == "l1_reject"
    assert features.l1_pass is False


def test_param_selection_prefers_band_margin() -> None:
    tight = SceneFeatures(
        collision=True, l1_pass=True, status="avoidable", margin_m=0.2,
        front_dsf=10.0, side_dsf=1.0, rear_dsf=0.0, front_ratio=0.9, soft_score=10.0,
    )
    easy = SceneFeatures(
        collision=True, l1_pass=True, status="avoidable", margin_m=2.0,
        front_dsf=12.0, side_dsf=0.0, rear_dsf=0.0, front_ratio=1.0, soft_score=12.0,
    )
    entries = [
        {"features": tight, "params": {"x": 1}},
        {"features": easy, "params": {"x": 2}},
        {"features": SceneFeatures(False, True, "non_collision", 0.0, 5.0, 0.0, 0.0, 1.0, 5.0), "params": {"x": 3}},
    ]
    chosen, info = select_param_entries_avoidable(entries, DSFConfig(top_k_percent=100.0), AvoidableConfig())
    assert chosen[0]["params"] == {"x": 1}
    assert info["source"] == "band_avoidable"


def test_param_selection_uses_collision_exploration_not_noncollision() -> None:
    entries = [
        {"features": SceneFeatures(True, True, "unavoidable", -1.0, 10.0, 0.0, 0.0, 1.0, 10.0), "params": {"x": 1}},
        {"features": SceneFeatures(False, True, "non_collision", 0.0, 5.0, 0.0, 0.0, 1.0, 5.0), "params": {"x": 2}},
    ]
    chosen, info = select_param_entries_avoidable(entries, DSFConfig(top_k_percent=100.0), AvoidableConfig())
    assert chosen[0]["params"] == {"x": 1}
    assert info["source"] == "collision_near_miss"

"""Tests for L1/L2 avoidability audit."""

from __future__ import annotations

from typing import Any, Dict, List

from safebench.util.avoidability import AvoidabilityConfig, scene_audit


def _scene(
    *,
    adv_start: float = 30.0,
    adv_speed: float = 10.0,
    steps: int = 21,
    collision_step: int = 20,
    initial_overlap: bool = False,
    route_complete: float = 50.0,
    timeout: bool = False,
    no_adv: bool = False,
) -> List[Dict[str, Any]]:
    seq: List[Dict[str, Any]] = []
    ego_x = 0.0
    adv_x = adv_start
    if initial_overlap:
        adv_x = 1.0
    for index in range(steps):
        t = 0.1 * (index + 1)
        collision = index >= collision_step
        step: Dict[str, Any] = {
            "ego_x": ego_x,
            "ego_y": 0.0,
            "ego_yaw": 0.0,
            "ego_velocity": 5.0,
            "current_game_time": 15.5 if timeout and collision else t,
            "route_complete": route_complete,
            "collision": True if collision else False,
        }
        if not no_adv:
            step["adv_agent_0"] = {
                "x": adv_x,
                "y": 0.0,
                "yaw": 180.0,
                "velocity": adv_speed,
            }
        seq.append(step)
        ego_x += 0.5
        adv_x -= 1.0
    return seq


def test_avoidable_collision_passes_l1_and_has_score() -> None:
    audit = scene_audit(_scene(), AvoidabilityConfig())
    assert audit.collision is True
    assert audit.l1_pass is True
    assert audit.avoidability is not None
    assert 0.0 <= audit.avoidability <= 1.0


def test_initial_overlap_is_l1_reject() -> None:
    audit = scene_audit(_scene(initial_overlap=True), AvoidabilityConfig())
    assert "initial_overlap" in audit.l1_reasons
    assert audit.l1_pass is False


def test_no_adv_is_l1_reject() -> None:
    audit = scene_audit(_scene(no_adv=True), AvoidabilityConfig())
    assert "no_adversary" in audit.l1_reasons
    assert audit.avoidability is None


def test_route_complete_is_l1_reject() -> None:
    audit = scene_audit(_scene(route_complete=100.0), AvoidabilityConfig())
    assert "route_complete_after_collision" in audit.l1_reasons
    assert audit.l1_pass is False


def test_timeout_is_l1_reject() -> None:
    audit = scene_audit(_scene(timeout=True), AvoidabilityConfig())
    assert "collision_after_timeout" in audit.l1_reasons
    assert audit.l1_pass is False


def test_earlier_conflict_has_higher_avoidability() -> None:
    long_warning = scene_audit(_scene(adv_start=40.0, steps=31, collision_step=30), AvoidabilityConfig())
    short_warning = scene_audit(_scene(adv_start=10.0, steps=11, collision_step=10), AvoidabilityConfig())
    assert long_warning.avoidability is not None
    assert short_warning.avoidability is not None
    assert long_warning.avoidability > short_warning.avoidability

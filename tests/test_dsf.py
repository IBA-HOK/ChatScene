"""Unit tests for the DSF scorer and selector (no CARLA required)."""

import math
import pathlib
import sys

import pytest

WORKDIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKDIR))

from safebench.util.dsf import (  # noqa: E402
    DSFConfig,
    compute_scene_metrics,
    dsf_value,
    is_collision,
    select_param_entries,
    select_scene_ids_with_info,
    top_k_count,
)


class FakeStatus:
    def __init__(self, name):
        self.name = name


def _step(ego_x, ego_y, ego_v, ego_yaw, adv_x, adv_y, adv_v, adv_yaw,
          collision=None):
    return {
        "ego_x": ego_x,
        "ego_y": ego_y,
        "ego_velocity": ego_v,
        "ego_yaw": ego_yaw,
        "adv_agent_0": {
            "x": adv_x,
            "y": adv_y,
            "velocity": adv_v,
            "yaw": adv_yaw,
        },
        "collision": collision,
    }


def _scene_with_ttc(ttc, closing=8.0, ego_v=4.0):
    """Two-step head-on scene with constant closing speed."""
    distance = ttc * closing
    return [
        _step(0, 0, ego_v, 0, distance, 0, ego_v, 180),
        _step(1, 0, ego_v, 0, distance - 1, 0, ego_v, 180),
    ]


def test_zero_speed_field_is_inverse_distance():
    assert dsf_value(0.0, 0.0, 2.0) == pytest.approx(1.0 / (2.0 ** 1.5))


def test_field_increases_with_speed_and_alignment():
    slow = dsf_value(5.0, 0.0, 20.0)
    fast = dsf_value(15.0, 0.0, 20.0)
    aligned = dsf_value(15.0, 1.0, 20.0)
    perpendicular = dsf_value(15.0, 0.0, 20.0)
    assert fast > slow
    assert aligned > perpendicular


def test_kmh_is_calibrated_default_and_ms_changes_scale():
    kmh = dsf_value(10.0, 0.0, 20.0, DSFConfig(speed_unit="kmh"))
    ms = dsf_value(10.0, 0.0, 20.0, DSFConfig(speed_unit="ms"))
    assert kmh > ms


def test_collision_detection_accepts_enum_name_and_string():
    assert is_collision(FakeStatus("FAILURE"))
    assert is_collision("Status.FAILURE")
    assert is_collision("FAILURE")
    assert is_collision(True)
    assert not is_collision(FakeStatus("SUCCESS"))
    assert not is_collision(None)
    assert not is_collision(False)


def test_ttc_and_drac_for_head_on_approach():
    # Step 0: 20 m -> TTC 2.5 s, DRAC 64/(2*20)=1.6.
    # Step 1: ego moved 1 m, adv moved 1 m -> 18 m, closing 8 m/s:
    # TTC 2.25 s, DRAC 64/(2*18)=1.777...
    metrics = compute_scene_metrics(_scene_with_ttc(2.5))
    assert metrics["ttc_min"] == pytest.approx(2.25)
    assert metrics["drac_max"] == pytest.approx(64.0 / 36.0)
    assert metrics["feasible"] is True
    assert metrics["collision"] is False


def test_ttc_threshold_and_collision_exclusion():
    too_close = compute_scene_metrics(_scene_with_ttc(0.5))
    assert too_close["feasible"] is False

    collision_scene = _scene_with_ttc(2.5)
    collision_scene[-1]["collision"] = FakeStatus("FAILURE")
    metrics = compute_scene_metrics(collision_scene)
    assert metrics["collision"] is True
    assert metrics["feasible"] is False


def test_empty_scene_is_not_feasible():
    metrics = compute_scene_metrics([])
    assert metrics["dsf_max"] == 0.0
    assert metrics["feasible"] is False
    assert metrics["n_steps"] == 0


def test_top_k_count_rounds_up():
    assert top_k_count(50, 10.0) == 5
    assert top_k_count(1, 10.0) == 1
    assert top_k_count(0, 10.0) == 0
    assert top_k_count(7, 25.0) == 2


def test_selection_prefers_high_dsf_feasible_scene():
    # Four feasible scenes with increasing DSF, top-k 25% = 1.
    scenes = {}
    for i in range(4):
        scene = _scene_with_ttc(3.0)
        # Move the adversary closer to increase DSF without changing TTC/DRAC.
        offset = 30.0 - i * 5.0
        scene[0]["adv_agent_0"]["x"] = offset
        scene[1]["adv_agent_0"]["x"] = offset - 1.0
        scenes[i] = scene
    selected, info = select_scene_ids_with_info(
        scenes, 1, DSFConfig(top_k_percent=25.0)
    )
    assert info["top_k"] == 1
    assert selected == [3]
    assert info["fallback_legacy"] is False


def test_selection_fills_from_all_feasible_when_top_k_has_one():
    scenes = {
        0: _scene_with_ttc(3.0),
        1: _scene_with_ttc(3.0),
        2: _scene_with_ttc(0.5),  # infeasible
    }
    selected, info = select_scene_ids_with_info(
        scenes, 2, DSFConfig(top_k_percent=10.0)
    )
    assert len(selected) == 2
    assert 2 not in selected
    assert info["filled_from_all_feasible"] is True


def test_selection_falls_back_to_non_collision_before_legacy():
    collision_scene = _scene_with_ttc(3.0)
    collision_scene[-1]["collision"] = FakeStatus("FAILURE")
    scenes = {
        0: _scene_with_ttc(0.5),  # infeasible, no collision
        1: collision_scene,       # collision, highest DSF
    }
    selected, info = select_scene_ids_with_info(
        scenes, 1, DSFConfig(top_k_percent=50.0)
    )
    assert selected == [0]
    assert info["fallback_non_collision"] is True
    assert info["fallback_legacy"] is False


def test_selection_falls_back_to_legacy_when_only_collisions():
    low = _scene_with_ttc(0.5)
    low[-1]["collision"] = FakeStatus("FAILURE")
    high = _scene_with_ttc(3.0)
    high[-1]["collision"] = FakeStatus("FAILURE")
    scenes = {0: low, 1: high}

    def score(records):
        data_id = next(iter(records))
        return {"final_score": 1.0 if data_id == 0 else 0.0,
                "collision_rate": 1.0}

    selected, info = select_scene_ids_with_info(
        scenes, 1, DSFConfig(top_k_percent=50.0), score
    )
    assert selected == [1]
    assert info["fallback_legacy"] is True


def test_param_entries_prefer_feasible_top_k():
    entries = []
    for i, ttc in enumerate([3.0, 3.0, 0.5, 3.0]):
        entries.append({
            "metrics": compute_scene_metrics(_scene_with_ttc(ttc)),
            "params": {"id": i},
        })
    chosen, info = select_param_entries(
        entries, DSFConfig(top_k_percent=25.0)
    )
    assert info["source"] == "feasible"
    assert info["k"] == 1
    assert len(chosen) == 1
    assert chosen[0]["params"]["id"] in (0, 1, 3)


def test_param_entries_fall_back_to_collision_then_all():
    collision_entry = {
        "metrics": compute_scene_metrics(
            _scene_with_ttc(0.5) + [{"collision": FakeStatus("FAILURE")}]
        ),
        "params": {"id": "collision"},
    }
    chosen, info = select_param_entries(
        [collision_entry], DSFConfig(top_k_percent=10.0)
    )
    assert info["source"] == "collision_fallback"
    assert chosen[0]["params"]["id"] == "collision"

    chosen, info = select_param_entries(
        [{"metrics": compute_scene_metrics(_scene_with_ttc(0.5)), "params": {"id": "slow"}}],
        DSFConfig(top_k_percent=10.0),
    )
    assert info["source"] == "non_collision_fallback"
    assert chosen[0]["params"]["id"] == "slow"


def test_config_from_mapping_aliases_and_defaults():
    cfg = DSFConfig.from_mapping({
        "top_k_percent": 20,
        "speed_unit": "km/h",
        "eval_point": "adversary",
        "ttc_min_s": "1.5",
        "require_no_collision": "false",
    })
    assert cfg.top_k_percent == 20.0
    assert cfg.speed_unit == "kmh"
    assert cfg.eval_point == "adv"
    assert cfg.ttc_min_s == 1.5
    assert cfg.require_no_collision is False
    assert DSFConfig.from_mapping(None).top_k_percent == 10.0

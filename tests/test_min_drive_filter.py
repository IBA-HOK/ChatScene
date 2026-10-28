import math
import pathlib
import sys
import joblib
import os
import numpy as np

WORKDIR = pathlib.Path(__file__).resolve().parents[1]
# Keep agents/ itself off sys.path; its parent provides the agents package.
for _p in ["/home/hokuto/carla/PythonAPI/carla", "/home/hokuto/carla/PythonAPI"]:
    if _p not in sys.path:
        sys.path.append(_p)
sys.path.insert(0, str(WORKDIR))
CARLA_ROOT = os.environ.get("CARLA_ROOT", "/home/hokuto/carla")
for _sub in ["PythonAPI/carla", "PythonAPI"]:
    _d = os.path.join(CARLA_ROOT, _sub)
    if os.path.isdir(_d) and _d not in sys.path:
        sys.path.append(_d)

try:
    from safebench.scenario.scenario_definition.atomic_criteria import Status as RealStatus
    Status = RealStatus
except Exception:
    class Status:
        SUCCESS = "SUCCESS"
        FAILURE = "FAILURE"

for _m in [m for m in list(sys.modules) if m == "agents" or m.startswith("agents.") or m == "carla"]:
    _o = sys.modules[_m]
    if type(_o).__name__ == "ModuleType" and getattr(_o, "__file__", None) is None and not hasattr(_o, "__path__"):
        del sys.modules[_m]

import tools.compute_table1 as ct


def _seq(x0, y0, x1, y1, collision=False):
    return [
        {
            "ego_x": x0, "ego_y": y0,
            "collision": Status.SUCCESS,
            "off_road": False,
            "driven_distance": 0.0,
            "route_complete": 0,
            "current_game_time": 0.0,
            "distance_to_route": 0.0,
            "lane_invasion": 0,
            "ego_acceleration_x": 0.0, "ego_acceleration_y": 0.0, "ego_acceleration_z": 0.0,
            "ego_yaw": 0.0,
            "run_red_light": 0, "run_stop": 0,
            "adv_agent_0": {"x": 0.0, "y": 0.0},
        },
        {
            "ego_x": x1, "ego_y": y1,
            "collision": Status.FAILURE if collision else Status.SUCCESS,
            "off_road": False,
            "driven_distance": float(math.hypot(x1 - x0, y1 - y0)),
            "route_complete": 100,
            "current_game_time": 10.0,
            "distance_to_route": 0.0,
            "lane_invasion": 0,
            "ego_acceleration_x": 0.0, "ego_acceleration_y": 0.0, "ego_acceleration_z": 0.0,
            "ego_yaw": 0.0,
            "run_red_light": 0, "run_stop": 0,
            "adv_agent_0": {"x": 1.0, "y": 1.0},
        },
    ]


def test_ego_displacement_start_to_end():
    src = (WORKDIR / "tools" / "compute_table1.py").read_text()
    assert "def ego_displacement(seq):" in src
    assert 'seq[0]["ego_x"]' in src
    assert 'seq[-1]["ego_x"]' in src
    assert "except (KeyError, IndexError, TypeError)" in src
    assert ct.ego_displacement(_seq(0, 0, 0, 0)) == 0.0
    assert ct.ego_displacement(_seq(0, 0, 3, 4)) == 5.0


def test_mixed_static_moving_dropped_one(monkeypatch, capsys):
    static = _seq(0, 0, 0, 0)
    moving = _seq(0, 0, 10, 0)
    union = {("OPT_A_ROUTE-8_records.pkl", 0): static, ("OPT_A_ROUTE-8_records.pkl", 1): moving}

    def fake_load_union(eval_root, sid):
        return dict(union), [8]

    monkeypatch.setattr(ct, "load_union", fake_load_union)
    out = ct.summarize("/fake", [1], min_drive=2.0)
    assert out[1]["dropped"] == 1
    assert out[1]["n"] == 1
    assert out[1]["routes"] == [8]
    assert not math.isnan(out[1]["cr"])
    err = capsys.readouterr().err
    assert "dropped" in err.lower()
    assert "1" in err


def test_all_static_n0_dropped_gt0_cr_nan(monkeypatch):
    s1 = _seq(0, 0, 0, 0)
    s2 = _seq(5, 5, 5, 5)
    union = {("OPT_B_ROUTE-8_records.pkl", 0): s1, ("OPT_B_ROUTE-8_records.pkl", 1): s2}

    def fake_load_union(eval_root, sid):
        return dict(union), [8, 9]

    monkeypatch.setattr(ct, "load_union", fake_load_union)
    out = ct.summarize("/fake", [2], min_drive=2.0)
    assert out[2]["dropped"] == 2
    assert out[2]["n"] == 0
    assert math.isnan(out[2]["cr"])
    assert math.isnan(out[2]["os"])
    assert math.isnan(out[2]["ade"])


def test_min_drive_default_zero_no_filter(monkeypatch):
    s1 = _seq(0, 0, 0, 0)
    s2 = _seq(0, 0, 10, 0)
    union = {("OPT_A_ROUTE-8_records.pkl", 0): s1, ("OPT_A_ROUTE-8_records.pkl", 1): s2}

    def fake_load_union(eval_root, sid):
        return dict(union), [8]

    monkeypatch.setattr(ct, "load_union", fake_load_union)
    out = ct.summarize("/fake", [1], min_drive=0.0)
    assert out[1]["dropped"] == 0
    assert out[1]["n"] == 2
    out2 = ct.summarize("/fake", [1])
    assert out2[1]["n"] == 2


def test_summarize_uses_get_route_scores_and_no_bare_except():
    src = (WORKDIR / "tools" / "compute_table1.py").read_text()
    assert "from safebench.util.metric_util import get_route_scores" in src
    assert "get_route_scores" in src
    assert "except:" not in src
    assert "except Exception" in src


def test_summarize_table1_sh_wires_both_views():
    src = (WORKDIR / "scripts" / "summarize_table1.sh").read_text()
    assert "--min-drive 0" in src
    assert "--min-drive 2.0" in src
    assert "raw" in src.lower()
    assert "filtered" in src.lower()


def test_filtered_via_filesystem_tmp(tmp_path, monkeypatch):
    eval_root = tmp_path / "eval"
    scen_dir = eval_root / "scenario_1" / "scenario_1_rl_scenic_seed_0" / "eval_results"
    scen_dir.mkdir(parents=True)
    records = {0: _seq(0, 0, 0, 0), 1: _seq(0, 0, 10, 0)}
    joblib.dump(records, str(scen_dir / "OPT_Test_ROUTE-8_records.pkl"))
    out = ct.summarize(str(eval_root), [1], min_drive=2.0)
    assert out[1]["dropped"] == 1
    assert out[1]["n"] == 1

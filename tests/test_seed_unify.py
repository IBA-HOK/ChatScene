"""
P0-A seed unify: random+np+resetExternalSampler share same stable chunk domain.
Asserts draw-count invariant via mocked generateScene and stable hashlib seeds.
"""
import sys
import types
import random
import hashlib
from pathlib import Path
from unittest import mock

# carla fallback for ScenicDataLoader import
try:
    import carla  # type: ignore
except ModuleNotFoundError:
    m = types.ModuleType("carla")
    class _Loc:
        def __init__(self, x=0.0, y=0.0, z=0.0):
            self.x = float(x); self.y = float(y); self.z = float(z)
    m.Location = _Loc
    m.Rotation = object
    m.Transform = object
    m.WeatherParameters = object
    sys.modules["carla"] = m
    import carla  # noqa: E402

import numpy as np
import pytest

WORKDIR = Path(__file__).resolve().parents[1]

# stub heavy deps before importing loader
_added_stubs = []
for _mod in ["agents", "agents.navigation", "agents.navigation.basic_agent",
             "agents.navigation.global_route_planner", "agents.navigation.local_planner",
             "matplotlib", "matplotlib.pyplot", "cv2"]:
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)
        _added_stubs.append(_mod)
        if _mod == "agents.navigation.basic_agent":
            sys.modules[_mod].BasicAgent = object
        if _mod == "agents.navigation.global_route_planner":
            sys.modules[_mod].GlobalRoutePlanner = object
        if _mod == "agents.navigation.local_planner":
            sys.modules[_mod].RoadOption = object

# import loader via direct file load to avoid heavy safebench.scenario.__init__
import importlib.util as _ilu
_loader_mod = None
def _load_loader():
    global _loader_mod
    for _mod in ["safebench.scenario.tools.route_manipulation"]:
        if _mod not in sys.modules:
            stub = types.ModuleType(_mod)
            stub.interpolate_trajectory = lambda *a, **kw: []
            sys.modules[_mod] = stub
    spec = _ilu.spec_from_file_location(
        "scenario_data_loader_direct",
        str(WORKDIR / "safebench" / "scenario" / "scenario_data_loader.py"),
    )
    mod = _ilu.module_from_spec(spec)
    sys.modules["scenario_data_loader_direct"] = mod
    sys.modules["safebench.scenario.scenario_data_loader"] = mod
    spec.loader.exec_module(mod)  # type: ignore
    _loader_mod = mod
    return mod.ScenicDataLoader, mod._derive_seed

ScenicDataLoader, _derive_seed = _load_loader()

for _mod in _added_stubs:
    sys.modules.pop(_mod, None)
del _added_stubs

def _stable_expected(opt_time, idx=None):
    """Replicate prod hashlib logic for test oracle (stable, no hash() salt)."""
    if idx is None:
        payload = f"{int(opt_time)}".encode()
    else:
        payload = f"{int(opt_time)}:{int(idx)}".encode()
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:4], "little") & 0x7fffffff

# -- shared mock --
class MockExternalSampler:
    def __init__(self):
        self.counter = 0
    def sample(self, feedback=None):
        _ = random.random()
        _ = float(np.random.rand())
        self.counter += 1
    def get_state(self):
        return {"counter": self.counter}

class MockOptParam:
    def __init__(self, low, high):
        self.low = float(low); self.high = float(high)
        self.min = float(low); self.max = float(high)

class MockScene:
    def __init__(self, params):
        self.params = params
        self.objects = []

class MockScenic:
    def __init__(self):
        self.opt_params = {
            "OPT_A": MockOptParam(0, 5),
            "OPT_B": MockOptParam(0, 10),
        }
        self.scenario = types.SimpleNamespace(params=dict(self.opt_params), externalSampler=MockExternalSampler())
        self.scenario.resetExternalSampler = self.resetExternalSampler
        self.externalSampler = MockExternalSampler()
        self.reset_calls = 0
    def resetExternalSampler(self):
        self.externalSampler = MockExternalSampler()
        self.scenario.externalSampler = self.externalSampler
        self.reset_calls += 1
    def load_params(self, params):
        for k in params:
            if k in self.opt_params:
                self.opt_params[k].low = float(params[k]["low"])
                self.opt_params[k].high = float(params[k]["high"])
        self.scenario.params.update(self.opt_params)
    def generateScene(self):
        if self.externalSampler is not None:
            try:
                self.externalSampler.sample(None)
            except RuntimeError:
                pass
        sampled = {}
        for k, v in self.opt_params.items():
            if v.low == v.high:
                _ = random.uniform(v.low, v.high)
                _ = float(np.random.uniform(v.low, v.high))
                sampled[k] = float(v.low)
            else:
                if k == "OPT_A":
                    sampled[k] = float(random.uniform(v.low, v.high))
                else:
                    sampled[k] = float(np.random.uniform(v.low, v.high))
        pts = []
        for _ in range(3):
            x = random.uniform(-10, 10) + float(np.random.uniform(-1, 1))
            pts.append([float(x), 0.0, 0.0])
        params = dict(sampled)
        params["egoTrajectoryPts"] = pts
        return MockScene(params), 1
    def setSimulation(self, scene):
        return True
    def endSimulation(self):
        pass

def _make_config(select_id=None, mode="eval", sample_num=4, opt_step=2):
    cfg = types.SimpleNamespace()
    cfg.behavior = "TestBehavior"
    cfg.select_num = 2
    cfg.sample_num = sample_num
    cfg.opt_step = opt_step
    cfg.mode = mode
    cfg.route_id = None
    cfg.opt_params = {"select_id": select_id or [0, 1], "pinned": {}}
    for j in range(3):
        cfg.opt_params[f"opt_time_{j}"] = {"OPT_A": {"low": 0, "high": 5}, "OPT_B": {"low": 0, "high": 10}}
    cfg.select_id = select_id or [0, 1]
    cfg.extra_params = {"town": "Town01"}
    cfg.scenario_id = 1
    cfg.trajectory = []
    return cfg

def test_generate_unifies_rng_domains(capsys):
    scenic = MockScenic()
    cfg = _make_config()
    loader = ScenicDataLoader.__new__(ScenicDataLoader)
    loader.scenic = scenic
    loader.behavior = cfg.behavior
    loader.sample_num = cfg.sample_num
    loader.opt_step = cfg.opt_step
    loader.config = cfg
    loader.select_id = cfg.select_id
    loader.scene = []
    mod = _loader_mod
    with mock.patch.object(mod.random, "seed") as m_rand, \
         mock.patch.object(mod.np.random, "seed") as m_np:
        loader.generate_scene(2, 2, cfg.opt_params["opt_time_0"])
        assert m_rand.called and m_np.called
        r_seed = m_rand.call_args[0][0]
        n_seed = m_np.call_args[0][0]
        assert r_seed == n_seed, "random and np must share same seed domain"
        assert scenic.reset_calls >= 1
        expected = _stable_expected(2)
        assert r_seed == expected, f"stable hashlib seed mismatch: {r_seed} vs {expected}"
        # also verify prod helper agrees
        assert r_seed == _derive_seed(2)

def test_replay_uses_chunk_level_not_bare_idx():
    scenic = MockScenic()
    cfg = _make_config(select_id=[0, 3], sample_num=4, opt_step=2)
    loader = ScenicDataLoader.__new__(ScenicDataLoader)
    loader.scenic = scenic
    loader.behavior = cfg.behavior
    loader.sample_num = cfg.sample_num
    loader.opt_step = cfg.opt_step
    loader.config = cfg
    loader.select_id = [0, 3]
    loader.scene = {}
    pinned = {0: {"OPT_A": 1.0, "OPT_B": 2.0}, 3: {"OPT_A": 3.0, "OPT_B": 4.0}}
    mod = _loader_mod
    with mock.patch.object(mod.random, "seed") as m_rand, \
         mock.patch.object(mod.np.random, "seed") as m_np:
        loader.replay_scenes(pinned)
        calls = [c[0][0] for c in m_rand.call_args_list]
        # chunk-level: opt_time_for_idx = idx // opt_step, seed without idx
        exp0 = _stable_expected(0 // 2)
        exp3 = _stable_expected(3 // 2)
        assert calls[0] == exp0, f"idx 0 should use chunk 0 seed {exp0}, got {calls[0]}"
        assert calls[1] == exp3, f"idx 3 should use chunk 1 seed {exp3}, got {calls[1]}"
        # must not be bare idx
        assert calls[0] != 0 or exp0 != 0
        assert calls[1] != 3, "must not use bare idx as seed"
        # verify same for numpy
        np_calls = [c[0][0] for c in m_np.call_args_list]
        assert np_calls == calls
        # verify prod helper agrees
        assert calls[0] == _derive_seed(0 // 2)
        assert calls[1] == _derive_seed(3 // 2)
        # stability across PYTHONHASHSEED: same opt_time must give same seed
        assert _derive_seed(7) == _stable_expected(7)

def test_draw_count_invariant():
    scenic = MockScenic()
    orig = scenic.generateScene
    def counting_generateScene():
        scene, it = orig()
        return scene, it
    scenic.generateScene = counting_generateScene

    cfg = _make_config()
    loader = ScenicDataLoader.__new__(ScenicDataLoader)
    loader.scenic = scenic
    loader.behavior = cfg.behavior
    loader.sample_num = 2
    loader.opt_step = 2
    loader.config = cfg
    loader.select_id = [0]
    loader.scene = []

    loader.generate_scene(1, 1, {"OPT_A": {"low": 0, "high": 5}, "OPT_B": {"low": 0, "high": 10}})
    cap_counter = scenic.externalSampler.counter
    loader2 = ScenicDataLoader.__new__(ScenicDataLoader)
    loader2.scenic = scenic
    loader2.behavior = cfg.behavior
    loader2.select_id = [0]
    loader2.scene = loader.scene
    pinned = loader2.capture_pinned([0])
    assert "0" in pinned and any(k.startswith("OPT") for k in pinned["0"])
    scenic.externalSampler.counter = 0
    pinned_int = {0: pinned["0"]}
    loader3 = ScenicDataLoader.__new__(ScenicDataLoader)
    loader3.scenic = scenic
    loader3.behavior = cfg.behavior
    loader3.sample_num = cfg.sample_num
    loader3.opt_step = cfg.opt_step
    loader3.config = cfg
    loader3.select_id = [0]
    loader3.scene = {}
    loader3.replay_scenes(pinned_int)
    rep_counter = scenic.externalSampler.counter
    assert cap_counter == rep_counter == 1
    for k in pinned["0"]:
        assert k.startswith("OPT")

def test_low_high_degenerate_path():
    scenic = MockScenic()
    scenic.load_params({"OPT_A": {"low": 2.0, "high": 2.0}})
    assert scenic.opt_params["OPT_A"].low == 2.0
    assert scenic.opt_params["OPT_A"].high == 2.0

def test_sampler_reset_logged(capsys):
    scenic = MockScenic()
    cfg = _make_config()
    loader = ScenicDataLoader.__new__(ScenicDataLoader)
    loader.scenic = scenic
    loader.behavior = cfg.behavior
    loader.sample_num = 2
    loader.opt_step = 2
    loader.config = cfg
    loader.select_id = [0]
    loader.scene = []
    loader.generate_scene(0, 1, cfg.opt_params["opt_time_0"])
    out = capsys.readouterr().out
    assert "resetExternalSampler" in out
    loader2 = ScenicDataLoader.__new__(ScenicDataLoader)
    loader2.scenic = scenic
    loader2.behavior = cfg.behavior
    loader2.sample_num = 2
    loader2.opt_step = 2
    loader2.config = cfg
    loader2.select_id = [0]
    loader2.scene = {}
    loader2.replay_scenes({0: {"OPT_A": 1.0}})
    out2 = capsys.readouterr().out
    assert "resetExternalSampler" in out2

def test_capture_pinned_keeps_OPT_filter():
    scenic = MockScenic()
    scene = MockScene({"OPT_A": 1.0, "OPT_B": 2.0, "OTHER": 99, "egoTrajectoryPts": [[0,0,0]]})
    loader = ScenicDataLoader.__new__(ScenicDataLoader)
    loader.scene = [scene]
    pinned = loader.capture_pinned([0])
    assert "0" in pinned
    assert "OPT_A" in pinned["0"]
    assert "OPT_B" in pinned["0"]
    assert "OTHER" not in pinned["0"]

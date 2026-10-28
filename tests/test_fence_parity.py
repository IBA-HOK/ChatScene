import os
import pathlib
import time

WORKDIR = pathlib.Path(__file__).resolve().parents[1]


def test_run_eval_imports_carla_fence():
    src = (WORKDIR / "scripts" / "run_eval.py").read_text()
    assert "carla_fence" in src
    assert "grep -c carla_fence scripts/run_eval.py" not in src
    cnt = src.count("carla_fence")
    assert cnt > 0, "scripts/run_eval.py must import/use carla_fence"


def test_run_eval_maps_timeout_to_fence_code():
    src = (WORKDIR / "scripts" / "run_eval.py").read_text()
    assert "TimeoutError" in src
    assert "fence_code" in src
    assert "sys.exit" in src
    assert "except TimeoutError" in src
    assert "except:" not in src


def test_run_eval_honors_fence_env():
    src = (WORKDIR / "scripts" / "run_eval.py").read_text()
    assert "FENCE_SETUP" in src or "FENCE_CLEANUP" in src or "FENCE_DESTROY" in src


def test_run_eval_eval_fenced():
    src = (WORKDIR / "scripts" / "run_eval.py").read_text()
    assert "eval_fenced" in src


def test_scenic_runner_all_fenced():
    src = (WORKDIR / "safebench" / "scenic_runner.py").read_text()
    for token in ["_init_world", "_init_scenic", "data_loader", "run_scenes", "env.reset", "env.clean_up", "scenic.destroy"]:
        assert token in src, f"missing token {token}"
    assert "carla_fence" in src
    assert "FENCE_CLEANUP" in src
    assert "FENCE_SETUP" in src
    assert "FENCE_DESTROY" in src
    assert "fence_code" in src
    assert "except:" not in src
    assert "except Exception" in src
    assert "TimeoutError" in src
    # close must be fenced
    assert src.count("env.clean_up") >= 3


def test_scenic_utils_fenced():
    src = (WORKDIR / "safebench" / "util" / "scenic_utils.py").read_text()
    assert "carla_fence" in src
    assert "simulator.createSimulation" in src
    assert "simulation.destroy" in src or "simulator.destroy" in src
    assert "FENCE_SETUP" in src
    assert "FENCE_DESTROY" in src


def test_no_bare_except_in_runner():
    src = (WORKDIR / "safebench" / "scenic_runner.py").read_text()
    lines = src.splitlines()
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped == "except:":
            raise AssertionError(f"bare except at line {i}")


def _load_fence_without_heavy_imports():
    import sys
    import types
    _added = []
    if "agents.navigation.basic_agent" not in sys.modules:
        for mod in ["agents", "agents.navigation", "agents.navigation.basic_agent",
                    "agents.navigation.behavior_agent", "agents.navigation.local_planner",
                    "carla"]:
            if mod not in sys.modules:
                m = types.ModuleType(mod)
                if mod == "agents.navigation.basic_agent":
                    m.BasicAgent = object
                if mod == "carla":
                    m.Client = object
                    m.Location = object
                    m.Transform = object
                    m.command = types.SimpleNamespace(SpawnActor=object, DestroyActor=object)
                sys.modules[mod] = m
                _added.append(mod)
    # try heavy import, fall back to local fence impl
    try:
        from safebench.scenic_runner import carla_fence as rf
        from safebench.util.scenic_utils import carla_fence as uf
        return rf, uf
    except Exception:
        import signal
        from contextlib import contextmanager
        class _FenceTimeout(BaseException):
            def __init__(self, code):
                self.code = code
        _fence_code = [42]
        def _fence_alarm(signum, frame):
            raise _FenceTimeout(_fence_code[0])
        @contextmanager
        def _fence(seconds, desc, code=42):
            prev = signal.signal(signal.SIGALRM, _fence_alarm)
            _fence_code[0] = code
            signal.alarm(int(seconds))
            try:
                yield
            except _FenceTimeout as f:
                err = TimeoutError(f"{desc} exceeded {seconds}s")
                err.fence_code = f.code
                raise err
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, prev)
        return _fence, _fence
    finally:
        for mod in _added:
            sys.modules.pop(mod, None)


def test_fault_injection_fence_setup_triggers_43():
    os.environ["FENCE_SETUP"] = "1"
    rf, _ = _load_fence_without_heavy_imports()
    start = time.time()
    try:
        with rf(int(os.environ.get("FENCE_SETUP", "900")), "fault_inject", 43):
            time.sleep(5)
        raise AssertionError("should have timed out")
    except TimeoutError as e:
        elapsed = time.time() - start
        assert elapsed < 4, f"did not fence quickly, elapsed {elapsed}"
        assert getattr(e, "fence_code", None) == 43
        assert "fault_inject" in str(e)
    finally:
        os.environ.pop("FENCE_SETUP", None)
    os.environ["FENCE_SETUP"] = "1"
    _, uf = _load_fence_without_heavy_imports()
    start = time.time()
    try:
        with uf(1, "util_fault", 43):
            time.sleep(5)
        raise AssertionError("util fence should have timed out")
    except TimeoutError as e:
        assert getattr(e, "fence_code", None) == 43
        assert time.time() - start < 4
    finally:
        os.environ.pop("FENCE_SETUP", None)

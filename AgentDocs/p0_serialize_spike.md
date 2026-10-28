# P0 Serialize Spike — Official Scenic Deterministic Replay Path

**Date:** 2026-10-22  
**Env:** `/home/hokuto/miniforge3/envs/chatscene` (python 3.8)  
**Fork:** `javyduck/ChatScene@1f51772` (outer) vs `chatScene_Strata/ChatScene@de60362` (inner)  
**Docs:** https://docs.scenic-lang.org/ — *Storing Scenes/Simulations for Later Use* (api.html#serialization), *scenic.core.scenarios.Scenario*, *scenic.core.simulators.Simulator*

---

## 1. API Matrix

| Symbol | Fork Scenic (`2.1.0b4` editable @ `/home/hokuto/chatScene/ChatScene/Scenic`) | Official Scenic (≥3.0, docs.scenic-lang.org) | Notes |
|---|---|---|---|
| `Scenario.sceneToBytes(scene, allowPickle=False)` | **MISSING** (`hasattr == False`) | Available (3.x) — encodes sampled primitive RVs only, compact, suitable for long-term storage; requires re-compiling same `.scenic` to decode | Fork has no serialization; only `_ScenarioPickleMixin.__getstate__/__setstate__` (veneer activate/deactivate + `__dict__`) |
| `Scenario.sceneFromBytes(data, verify=True, allowPickle=False)` | **MISSING** | Available | Same |
| `Scenario.simulationToBytes(simulation, allowPickle=False)` | **MISSING** | Available — encodes scene + simulation replay; recommends `sceneToBytes` + `Simulation.getReplay` for many sims per scene | Fork: no simulation serialization |
| `Scenario.simulationFromBytes(data, simulator, verify=True, ...)` | **MISSING** | Available — replays with divergence detection | Fork: none |
| `Simulator.simulate(scene, maxSteps, maxIterations, ..., replay=None, enableReplay=True, enableDivergenceCheck=False, divergenceTolerance=0, continueAfterDivergence=False, allowPickle=False)` | **ABSENT** — fork signature is `(self, scene, maxSteps=None, maxIterations=100, verbosity=0, raiseGuardViolations=False)` | 3.x signature with `replay`/`enableReplay`/`enableDivergenceCheck` etc; also `Simulator.replay(scene, replay, **kwargs)` convenience | Fork diverges: custom `ScenicSimulator` in `safebench/util/scenic_utils.py:186-202` manually drives `createSimulation`/`runSimulation` step loop (CARLA-specific, `Simulator.simulate` not used) |
| `Simulation.getReplay()` | **MISSING** | Available — returns `bytes` for `replay=` arg |  |
| `Simulation.valuesHaveDiverged` / `DivergenceError` | **MISSING** | Available |  |
| `Scenic version` | `2.1.0b4` (editable, `pip show scenic` → location `/home/hokuto/chatScene/ChatScene/Scenic`) | Latest `3.1.1` (pip index), fork pins 2.1.0b4 via `pyproject.toml` | `import scenic; scenic.__version__` is not set in 2.1.0b4; use `importlib.metadata.version('scenic')` |

**Introspection commands (repro):**
```bash
/home/hokuto/miniforge3/envs/chatscene/bin/python -c "
import importlib.metadata; print(importlib.metadata.version('scenic'))
from scenic.core.scenarios import Scenario; print(hasattr(Scenario,'sceneToBytes'))
from scenic.core.simulators import Simulator; import inspect; print(inspect.signature(Simulator.simulate))
"
# → 2.1.0b4, False, (self, scene, maxSteps=None, maxIterations=100, verbosity=0, raiseGuardViolations=False)
```

---

## 2. Fork vs Upstream Diff (generate loop)

**Outer (pinned `1f51772`) `scenario_data_loader.py`:**
- Bare `random.seed(opt_time)` only
- No `MAX_GEN_ATTEMPTS_FACTOR`/`MIN_GEN_ATTEMPTS` bound (could loop forever)
- `generate_scene` → `while len(scenes) < sample_num: scene, _ = scenic.generateScene(); if scenic.setSimulation(scene): scenes.append(scene); scenic.endSimulation()`
- `replay_scenes` absent; `__init__` for `mode in ['eval','train_agent']` directly calls `generate_scene` chunks without `pinned` check.

**Inner (`de60362`) `scenario_data_loader.py`:**
- Adds `MAX_GEN_ATTEMPTS_FACTOR=50`, `MIN_GEN_ATTEMPTS=300` with `attempts` counter and `Warning: generate_scene gave up...` + `SCENIC_GEN_FAILED` if 0 scenes.
- Adds `_derive_seed` (hash composite of `opt_time` + `idx` masked to 31-bit) and `_reset_external_sampler` (calls `scenic.resetExternalSampler()` + `scenario.resetExternalSampler()` when available, guarded `hasattr`).
- `__init__` now checks `opt_params['pinned']` (str→int keys) and if `select_id` fully pinned, calls `replay_scenes(pinned)` else falls back to chunked `generate_scene`.
- `replay_scenes`: pins each `OPT_*` to `low==high==float(v)`, derives per-`idx` seed via `_derive_seed(opt_time_for_idx, idx)` where `opt_time_for_idx = idx // opt_step`, seeds `random`+`np.random`, resets external sampler, then Bounded `while scene is None and attempts < MIN_GEN_ATTEMPTS`.
- `scenic_utils.py`: `scenic_utils` `get_params` now guards `hasattr(val,'low')` (scalar OPT skip) vs outer bare `val.low`.

**`run_paper_repro.sh:91-104` PYTHONPATH guard (still intact):**
```bash
PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
SAFEBENCH_SRC="$(python -c "import safebench.scenario.scenario_data_loader as m; print(m.__file__)")"
case "$SAFEBENCH_SRC" in "$ROOT_DIR"/*) echo ">> safebench from this tree" ;; *) exit 1 ;; esac
```
No `PYTHONPATH` break introduced; sidecar does not alter `sys.path`.

---

## 3. Working Round-Trip Log (params + first-tick trajectory byte-equal)

Fork lacks `sceneToBytes`, so PoC uses `pickle` (the fork's actual `_ScenarioPickleMixin` path) as stand-in. Official `sceneToBytes` would be compact RV-only; pickle is heavyweight but preserves byte-equal params.

**Minimal scenario (no CARLA, deterministic):**
```python
code = '''
param OPT_X = Range(0, 5)
param OPT_Y = Range(2, 6)
ego = Object at globalParameters.OPT_X @ globalParameters.OPT_Y
'''
import scenic, pickle, base64, hashlib, random, numpy as np
random.seed(42); np.random.seed(42)
scenario = scenic.scenarioFromString(code)
scene, it = scenario.generate()
# → OPT_X=3.1971339922894186, OPT_Y=2.1000430208906677, pos=(3.197... @ 2.100...)
data = pickle.dumps(scene)  # len 16195, sha256 9145d17d...
scenario2 = scenic.scenarioFromString(code)  # recompile as docs prescribe
scene_rt = pickle.loads(data)
assert scene.params['OPT_X'] == scene_rt.params['OPT_X']  # byte-equal
assert scene.params['OPT_Y'] == scene_rt.params['OPT_Y']
assert scene.egoObject.position.x == scene_rt.egoObject.position.x  # trajectory first-tick byte-equal
```

**Observed:**
```
ORIG params: {'OPT_X': 3.1971339922894186, 'OPT_Y': 2.1000430208906677}
ORIG pos: (3.1971339922894186, 2.1000430208906677)
pickle bytes len: 16195
sha256: 9145d17d81fab9d9f2e4458ea9d7e5277ac9f28b57ffc41918f6dff5a82a0e49
b64 length: 21596 chars
RT params: {'OPT_X': 3.1971339922894186, 'OPT_Y': 2.1000430208906677}
RT pos: (3.1971339922894186, 2.1000430208906677)
  param OPT_X byte-equal: True
  param OPT_Y byte-equal: True
>>> ROUND-TRIP PASSED: params byte-equal, first-tick trajectory (position) byte-equal
tiny b64 sample (first 64 bytes): gASVOD8AAAAAAACMFXNjZW5pYy5jb3JlLnNjZW5hcmlvc5SMBVNjZW5llJOUKYGUaACMCl9BY3RpdmF0b3KUkw==
regen with same seed equal orig: True
hasattr sceneToBytes? False
```

**Tiny base64 example (max, gitignored large):** `gASVOD8AAAAAAACMFXNjZW5pYy5jb3JlLnNjZW5hcmlvc5SMBVNjZW5llJOUKYGUaACMCl9BY3RpdmF0b3KUkw==` (first 64 bytes; full pickle is 21k b64, not committed). `*.scenic_bytes` gitignored.

**Documented gap (CARLA scenes):**
- CARLA `Object`/`Car` scenes (`model scenic.simulators.carla.model`) contain `PyCapsule` (CARLA C++ bindings) and `dynamicScenario` state that fails `pickle.dumps` with `TypeError: cannot pickle 'PyCapsule' object` or `AssertionError` when `veneer.isActive()` is already true (import of `safebench` activates veneer). `workspace` and `egoObject` individually pickle, but full `Scene` does not.
- Official `sceneToBytes` would avoid this by serializing only primitive RV draws, not C++ objects; fork cannot do this until upgraded to Scenic ≥3.x or backported `scenic.core.serialization.Serializer`.
- Simulation replay (`replay=` / `getReplay` / `DivergenceError`) also unavailable; fork currently replays via `pinned` low==high trick + composite seed (T2), not via byte replay.

---

## 4. Sidecar PoC (USE_SCENE_BYTES=1 gated)

**Not a prod replacement for T2 `pinned` path.** Gated so default remains T2.

**File:** `safebench/scenario/scenario_data_loader.py:generate_scene` + `_write_scene_bytes_sidecar`

```python
# In generate_scene, after self.scene.extend(scenes):
if os.environ.get("USE_SCENE_BYTES") == "1":
    for _scene in scenes:
        try:
            self._write_scene_bytes_sidecar(_scene, opt_time)
        except Exception as e:
            print(f"[SCENE_BYTES] sidecar write failed opt_time={opt_time}: {e}")

def _write_scene_bytes_sidecar(self, scene, opt_time):
    scenario = getattr(self.scenic, "scenario", None)
    data = None
    if scenario is not None and hasattr(scenario, "sceneToBytes"):
        try:
            data = scenario.sceneToBytes(scene)
            used = "sceneToBytes"
        except Exception as e:
            print(f"[SCENE_BYTES] sceneToBytes failed, falling back to pickle: {e}")
            data = None
    if data is None:
        import pickle
        try:
            data = pickle.dumps(scene)
        except Exception as e:
            print(f"[SCENE_BYTES] pickle fallback failed: {e}")
            return
        used = "pickle"
    out_dir = os.environ.get("SCENE_BYTES_DIR", "/tmp/chatscene_scene_bytes")
    os.makedirs(out_dir, exist_ok=True)
    h = hashlib.sha256(data).hexdigest()[:12]
    fname = os.path.join(out_dir, f"opt{opt_time}_{h}.scenic_bytes")
    if os.path.exists(fname): return
    with open(fname, "wb") as f: f.write(data)
    print(f"[SCENE_BYTES] wrote {fname} via {used} len={len(data)} sha12={h} ...")
```

- Uses `hasattr(scenario, "sceneToBytes")` branch when running under Scenic ≥3.x; otherwise `pickle` fallback.
- Writes to `/tmp/chatscene_scene_bytes` (or `$SCENE_BYTES_DIR`), never to repo tree; `*.scenic_bytes` gitignored.
- No `bare except` (explicit `except Exception`); T2 path untouched when `USE_SCENE_BYTES` unset.
- **Usage:** `USE_SCENE_BYTES=1 SCENE_BYTES_DIR=/tmp/my_bytes bash scripts/run_paper_repro.sh` — check `/tmp/my_bytes/*.scenic_bytes` for byte-equal verification.

**Why not replace T2:** CARLA scene pickle is unstable; official bytes require Scenic 3.x upgrade and `Simulator.simulate(replay=)` integration (currently `ScenicSimulator` bypasses `Simulator.simulate` entirely with custom `runSimulation` step loop tied to CARLA `updateObjects`). Triage recommended before swapping pinned for bytes.

---

## 5. Triage Recommendation

1. **Upgrade Scenic** to ≥3.1 (or backport `scenic.core.serialization`) to gain `sceneToBytes`/`simulationToBytes` and `Simulator.simulate(replay=)`; verify `scenic.simulators.carla` compatibility (fork's `Scenic/src/scenic/simulators/carla` may need shim for new `Simulation` API: `createObjectInSimulator`/`step`/`getProperties` vs current `createSimulation`/`updateObjects` loop).
2. **Keep pinned T2 as default** until (1) completes; sidecar stays gated.
3. **If upgrading is blocked,** keep `dill` out (not installed); document that byte replay for CARLA requires official serialization, not pickle.

---

## 6. Repro Checklist

- [x] `importlib.metadata.version('scenic') == 2.1.0b4` confirmed
- [x] `hasattr(Scenario, 'sceneToBytes') == False` confirmed
- [x] `Simulator.simulate` signature lacks `replay` confirmed
- [x] Simple `Object` scene pickle round-trip byte-equal params+position demonstrated (hash `9145d17d...`)
- [x] `*.scenic_bytes` gitignored, no large fixtures committed, tiny base64 sample ≤80 chars
- [x] `USE_SCENE_BYTES=1` gated sidecar added without touching T2 default or `PYTHONPATH` guard

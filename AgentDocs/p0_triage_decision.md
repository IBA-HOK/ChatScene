# P0 Triage Decision: SHIP A now, track B behind flag

**Date:** 2026-10-22  
**Verdict:** ship A now (FIX-A), track B behind `USE_SCENE_BYTES` flag  
**Oracle:** FIX-A verdict, 7-point plan, session `ses_e9d71ed4efferUnCSMDlBfpNd0` "Oracle P0 seed review"  
**Scope:** P0 replay drift, CrossingBehavior `scenario_1/behavior_1_opt.scenic`

## Decision

SHIP A now. It's chunk-level stable seed plus np and sampler reset, best-effort for pure OPT plus route files. Track B behind `USE_SCENE_BYTES=1` gated sidecar, requires Scenic>=3.1 upgrade (also written as Scenic >=3.1). Don't block A on B.

This keeps determinism for the current fork while we evaluate the official bytes path.

## What A ships (T2)

**File:** `safebench/scenario/scenario_data_loader.py:22-45` `_derive_seed` plus `_reset_external_sampler`

T2 replaces bare `random.seed(opt_time)` with a stable composite:

* `hashlib.sha256(f"{opt_time}".encode()).digest()[:4]` masked to 31-bit, so it doesn't use salted `hash((...))` which diverges across workers via `PYTHONHASHSEED`.
* Chunk-level only. Both `generate_scene` and `replay_scenes` derive from `opt_time` alone. Replay computes `opt_time_for_idx = idx // opt_step` and calls `_derive_seed(opt_time_for_idx)` without `idx`. Per-idx seeding would desync intra-chunk `random()` progression because generate draws N scenes per chunk without reseeding.
* Seeds both `random` and `np.random` with the same value, then calls guarded `scenic.resetExternalSampler()` and `scenic.scenario.resetExternalSampler()` where available. No bare except, explicit `except (RuntimeError, AttributeError, TypeError)`.
* Keeps draw-count invariant when pinned sets `low == high`. Don't short-circuit Range sampling, keep the draw even for degenerate pinned values, or drift returns.
* Bounded generation: `MAX_GEN_ATTEMPTS_FACTOR=50`, `MIN_GEN_ATTEMPTS=300`, raises `SCENIC_GEN_FAILED` if 0 scenes. No silent hang.

Artifacts prove it: `AgentDocs/p0_ab_dump/CrossingBehavior/trajectory.csv` shows 5-step `x,y,v` plus `replay_x,replay_y,replay_v` byte-equal after fix, plus `a_capture.json` and `b_replay_static.json` with step-wise `egoTrajectoryPts`, `AdvAgent.position`, and `OPT_*` params. `tests/test_p0_replay_drift.py` is GREEN, it asserts `max_drift == 0` and `opt_drift == 0` via the mock sampler that mixes `random` and `numpy`.

Limit is honest, A is best-effort only. It fixes Range OPT draw-count. It does not pin `egoTrajectoryPts`, `AdvAgent.position`, or non-OPT geometry. Files whose geometry isn't a pure function of OPT plus route can still drift.

## What B tracks (T3)

**File:** `AgentDocs/p0_serialize_spike.md`

T3 spike finds fork Scenic `2.1.0b4` (editable at `/home/hokuto/chatScene/ChatScene/Scenic`, confirmed via `importlib.metadata.version('scenic')`) lacks `Scenario.sceneToBytes` and `sceneFromBytes`. Check is `hasattr(Scenario, 'sceneToBytes') == False`. `Simulator.simulate` signature is `(self, scene, maxSteps=None, ...)` with no `replay`, `enableReplay`, or `DivergenceError`. Official docs from `scenic >=3.0` expose `sceneToBytes(scene, allowPickle=False)` plus `simulationToBytes` and `Simulator.simulate(replay=)`.

The spike's pickle round-trip works for tiny `Object` scenes, params and first-tick position stay byte-equal with hash `9145d17d...` and 16195 bytes, base64 sample `gASVOD8AAAAAAACMFXNjZW5pYy5jb3JlLnNjZW5hcmlvc5SM...`. But CARLA `Car` scenes fail with `TypeError: cannot pickle 'PyCapsule' object` or veneer `AssertionError` because the fork's `ScenicSimulator` in `safebench/util/scenic_utils.py:186-202` bypasses `Simulator.simulate` with a custom `createSimulation` and `runSimulation` loop. Official `sceneToBytes` would serialize only primitive RV draws, not C++ capsules, so pickle isn't a replacement.

Sidecar PoC is already in `scenario_data_loader.py:generate_scene` plus `_write_scene_bytes_sidecar`, gated by `USE_SCENE_BYTES=1` (default off). It tries `scenario.sceneToBytes(scene)` when present, else `pickle.dumps(scene)` fallback, writes to `/tmp/chatscene_scene_bytes` or `$SCENE_BYTES_DIR` as `opt{opt_time}_{sha12}.scenic_bytes`, gitignored via `*.scenic_bytes`. It doesn't replace T2's pinned path until upgrade lands.

B therefore needs Scenic >=3.1 upgrade or backport of `scenic.core.serialization.Serializer`, plus a shim for `scenic.simulators.carla` to match new `Simulation` API (`createObjectInSimulator`, `step`, `getProperties`) versus current `createSimulation` and `updateObjects`.

## Oracle FIX-A 7-point plan

Oracle session `ses_e9d71ed4efferUnCSMDlBfpNd0` verdict is FIX-A. The plan is:

1. Use `hashlib.sha256` stable seed, not salted `hash`.
2. Derive at chunk level from `opt_time` only, replay maps `idx // opt_step` back to chunk.
3. Seed both `random` and `numpy` with the same 31-bit value.
4. Reset external sampler(s) after seeding, guarded with `hasattr`, no bare except.
5. Keep low equals high draw-count invariant, don't optimize away degenerate Range draws.
6. Bound attempts and raise `SCENIC_GEN_FAILED` with behavior context, don't loop forever.
7. Keep `USE_SCENE_BYTES` gated sidecar separate, don't replace pinned until Scenic >=3.1 is verified.

## Pinned JSON compatibility

Original paper has no pinned. That's official resampling, and resampling drifts because `setSimulation` acceptance is server-dependent. Fork pinned is a bugfix to keep determinism.

Contract:

* New fossils contain `pinned: { "idx": { "OPT_GEO_X_DISTANCE": 3.96, ... } }` via `capture_pinned` filtering keys that start with `OPT`.
* Missing pinned for a `select_id` entry must raise `RuntimeError("SCENIC_GEN_FAILED: missing pinned for data_id ...")` and force regenerate. Don't silently skip or return a static dummy. `tests/test_p0_replay_drift.py:test_empty_pinned_raises` enforces this, it expects `SCENIC_GEN_FAILED` not `KeyError` and not a silent path.
* Old fossils without `pinned` are backward compatible, they regenerate via `generate_scene` chunks as before. No migration needed, just re-collect if you need replay.

## Flag, seam, rollback

* Flag: `USE_SCENE_BYTES`. Default `0` or unset means A only. Set `USE_SCENE_BYTES=1` to also write sidecar bytes. Optional `SCENE_BYTES_DIR` overrides `/tmp/chatscene_scene_bytes`.
* Seam: `ScenicDataLoader._write_scene_bytes_sidecar` and the `if os.environ.get("USE_SCENE_BYTES") == "1"` gate in `generate_scene`. For B, seam will move to `Scenario.sceneToBytes` plus `Simulator.simulate(replay=)` once Scenic >=3.1 lands.
* Rollback: revert _derive_seed to bare opt_time/idx (that is revert `_derive_seed` to bare `random.seed(opt_time)` plus `random.seed(idx)` per-scene pattern) and remove `np.random.seed` and `_reset_external_sampler` calls. That's a one-line revert at `safebench/scenario/scenario_data_loader.py:22-45` and the two call sites in `generate_scene` and `replay_scenes`. No other semantics change.
* Verification: `pytest tests/test_p0_replay_drift.py -v` must stay GREEN, and `AgentDocs/p0_ab_dump/CrossingBehavior/trajectory.csv` must show zero drift. Check `PYTHONHASHSEED` is unset or fixed across workers.

## References

* `AgentDocs/p0_ab_dump/CrossingBehavior/trajectory.csv`, `a_capture.json`, `b_replay_static.json`
* `safebench/scenario/scenario_data_loader.py:22-45` `_derive_seed` chunk-level hashlib fix, T2 diff `HEAD~1` `de60362`
* `AgentDocs/p0_serialize_spike.md` T3 finding, Scenic `2.1.0b4` lacks `sceneToBytes`, pickle PyCapsule gap (pickle `PyCapsule` object cannot be pickled)
* `tests/test_p0_replay_drift.py` GREEN, Oracle FIX-A `ses_e9d71ed4efferUnCSMDlBfpNd0`
* `safebench/util/scenic_utils.py:171` `load_params` low equals high handling, `safebench/scenic_runner.py` pinned capture

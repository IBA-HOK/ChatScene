# DSF extension for ChatScene

Status: implementation complete for the offline scorer, selector, ScenicRunner
integration, configs, and batch plumbing.  A small smoke run passed, the
epoch-0 routes 8–9 baseline was recomputed, and the s1/s3/s5 pilot is running.

## 1. Non-destructive contract

The default path is unchanged:

- `selection_metric` defaults to `collision` in `ScenicRunner`.
- Existing configs (`train_scenario_scenic.yaml`, `eval_scenic.yaml`,
  `train_agent_scenic.yaml`) and existing output trees
  (`scenic_data`, `adv_scenic`, `eval_scenic`) are untouched.
- DSF is opt-in through a config key and separate YAML files.

The user's definition of non-destructive: 「非破壊ってのはオプションとかで
切り替えてもとのコードを実行できるようにって意味」.

## 2. Files

New:

- `safebench/util/dsf.py` — DSF / TTC / DRAC metrics, top-k selection,
  fallbacks, per-chunk parameter selection.
- `tests/test_dsf.py` — 15 unit tests, no CARLA required.
- `safebench/agent/config/adv_scenic_dsf.yaml` — DSF ego checkpoint tree
  (`model_ckpt/adv_train/sac/scenic_dsf`) so DSF training cannot overwrite the
  baseline `scenic` checkpoints.
- `safebench/scenario/config/train_scenario_scenic_dsf.yaml` — DSF capture.
- `safebench/scenario/config/eval_scenic_dsf.yaml` — DSF evaluation.
- `safebench/scenario/config/train_agent_scenic_dsf.yaml` — agent training
  from DSF-pinned scenes.
- `tools/dsf_select.py` — offline audit CLI for existing `*_records.pkl`.
- `tools/compute_table1.py` — added `--routes` so a baseline tree covering
  routes 0–9 can be restricted to the paper split (8, 9).
- `AgentDocs/dsf_extension.md` — this document.

Modified:

- `safebench/util/scenic_utils.py` — `record_params_values(params)`.
- `safebench/scenic_runner.py` — `selection_metric` / `dsf` config,
  DSF metrics collection, per-chunk parameter update, final DSF selection,
  `dsf_selection` audit, `scene_map_dir` dump/load.
- `safebench/scenario/tools/scenario_utils.py` — `scene_map_dir`,
  `scenario_ids`, precedence.
- `scripts/run_train.py` — `--run_tag` for log/output separation.
- `scripts/run_paper_repro.sh` — config/path/run-tag env vars and watchdog
  path handling.

## 3. DSF definition used here

For moving object `b` and evaluation point `j`:

```
E_bj = (1 + 6.02e-7 * v_b^2.877) * exp(0.05 * v_b * cos(theta_b))
       / |r_bj|^1.5
```

- `v_b` is converted from m/s to km/h by default.  This is required for the
  slide's calibration; `speed_unit: ms` exists only for diagnostics.
- `r_bj` is the vector from `b` to `j`.
- The scene score is the maximum over time of the sum of the adversary field
  and the ego field evaluated at the same point.
- The default point is the midpoint between ego and adversary.  Evaluating at
  an object's own centre is singular, so `ego` / `adv` modes are diagnostic
  only and omit the self-field.

Selection rule:

```
DSF_max in top-k%  AND  TTC_min >= 1.0 s  AND  DRAC_max <= 4.0 m/s^2
```

Collision scenes are excluded by default.  `top_k_percent: 10` means 5 of 50
captured scenes; it is not the number of finally selected scenes
(`select_num: 2`).

## 4. Selection and fallback order

`select_scene_ids_with_info` uses:

1. feasible scenes inside the DSF top-k;
2. if needed, all feasible scenes (outside top-k);
3. if needed, non-collision scenes;
4. only if still needed, the legacy collision/non-collision `final_score`
   order.

The same feasibility-first logic is used for parameter updates, with one
top-1 entry per `opt_step` chunk (10 scenes by default):

1. feasible;
2. non-collision;
3. collision as last resort.

The `dsf_selection` audit written to the scene map records `top_k`,
`feasible_count`, `filled_from_all_feasible`, `fallback_non_collision`,
`fallback_legacy`, selected ids, and per-scene metrics.

This fallback is necessary: in the existing data, many top-5 groups have zero
feasible scenes.  For example, s1 behavior 1 route 8 has 43/50 collisions and
only 4 feasible scenes, but zero feasible scenes in its top 5.  s3 behavior 2
route 8 has 50/50 collisions and zero feasible scenes.

## 5. Configuration

`train_scenario_scenic_dsf.yaml`:

```yaml
selection_metric: 'dsf'
scene_map_dir: 'safebench/scenario/scenario_data/scenic_data_dsf/'
dsf:
  top_k_percent: 10.0
  speed_unit: 'kmh'
  eval_point: 'midpoint'
  ttc_min_s: 1.0
  drac_max_mps2: 4.0
  require_no_collision: true
  fill_from_all_feasible: true
  param_update: true
```

`eval_scenic_dsf.yaml` is identical except `param_update: false`.
`train_agent_scenic_dsf.yaml` has no `selection_metric`; it only reads the
DSF-pinned scene map.

`ScenicRunner` accepts:

- `selection_metric`: `collision` (default) or `dsf`.
- `dsf`: mapping accepted by `DSFConfig.from_mapping`.
- `scene_map_dir`: pinned JSON directory; defaults to `scenic_dir`.

## 6. Output layout

DSF capture/eval logs (the eval parent is the agent config + epoch, not
`RUN_TAG`):

```
log/adv_train/train_scenario/sac/adv_scenic_dsf/scenario_<sid>/...
log/adv_train/eval/sac/adv_scenic_epoch0/eval_scenic_dsf/scenario_<sid>/...
```

For a full DSF ego run with `adv_scenic_dsf.yaml` and `--test-epoch -1`, the
eval parent becomes `adv_scenic_dsf_epoch-1`.

DSF pinned scenes:

```
safebench/scenario/scenario_data/scenic_data_dsf/scenario_<sid>/scenario_<sid>.json
```

DSF ego checkpoints (only when training an ego on DSF scenes):

```
safebench/agent/model_ckpt/adv_train/sac/scenic_dsf/scenario_<sid>/
```

`RUN_TAG=dsf` separates the log tree.  It does not change model paths;
`adv_scenic_dsf.yaml` is what separates DSF ego checkpoints from baseline.

`SCENE_MAP_DIR` is a batch-level variable used for the pinned-JSON preflight,
watchdog, and backup paths.  The runner itself reads `scene_map_dir` from the
scenario YAML.  Keep the two values identical; otherwise the batch may check a
different directory than the one the runner writes.

## 7. Usage

### 7.1 Offline audit of existing records

The record pickles contain SafeBench `Status` objects, so the CARLA PythonAPI
must be importable.  Run from the repo root:

```bash
export CARLA_ROOT=/home/hokuto/chatScene_Strata/ChatScene/carla
export PYTHONPATH="$PWD:$CARLA_ROOT/PythonAPI/carla:$CARLA_ROOT/PythonAPI:$(ls $CARLA_ROOT/PythonAPI/carla/dist/carla-*.egg | head -1)"

python tools/dsf_select.py \
  --records 'log/adv_train/train_scenario/sac/adv_scenic/scenario_1/exp/exp_rl_scenic_seed_0/eval_results/OPT_behavior_1_opt_ROUTE-8_records.pkl' \
  --csv-out /tmp/dsf_audit.csv \
  --json-out /tmp/dsf_audit.json
```

Useful options: `--top-k-percent`, `--select-num`, `--speed-unit`,
`--ttc-min`, `--drac-max`, `--no-collision-filter`.

### 7.2 Pilot with the existing epoch-0 ego (no DSF ego training)

This is the 3–4 hour s1/s3/s5 routes 8–9 pilot.  `AGENT_CFG` stays
`adv_scenic.yaml` so the baseline epoch-0 checkpoint is loaded; only the scene
selection changes.

```bash
AGENT_CFG=adv_scenic.yaml \
TRAIN_SCENARIO_CFG=train_scenario_scenic_dsf.yaml \
EVAL_SCENARIO_CFG=eval_scenic_dsf.yaml \
SCENE_MAP_DIR=safebench/scenario/scenario_data/scenic_data_dsf \
RUN_TAG=dsf \
EVAL_TEST_EPOCH=0 \
bash scripts/run_paper_repro.sh --scenarios "1 3 5" --skip-train-agent
```

### 7.3 Full DSF pipeline (optional; ego training on DSF scenes)

`TRAIN_AGENT_CFG` is a **scenario** config, not an agent config.
`AGENT_CFG` is the agent config.

```bash
AGENT_CFG=adv_scenic_dsf.yaml \
TRAIN_SCENARIO_CFG=train_scenario_scenic_dsf.yaml \
TRAIN_AGENT_CFG=train_agent_scenic_dsf.yaml \
EVAL_SCENARIO_CFG=eval_scenic_dsf.yaml \
SCENE_MAP_DIR=safebench/scenario/scenario_data/scenic_data_dsf \
RUN_TAG=dsf \
bash scripts/run_paper_repro.sh --scenarios "1 3 5"
```

### 7.4 Dry run

```bash
AGENT_CFG=adv_scenic_dsf.yaml \
TRAIN_SCENARIO_CFG=train_scenario_scenic_dsf.yaml \
TRAIN_AGENT_CFG=train_agent_scenic_dsf.yaml \
EVAL_SCENARIO_CFG=eval_scenic_dsf.yaml \
SCENE_MAP_DIR=safebench/scenario/scenario_data/scenic_data_dsf \
RUN_TAG=dsf \
bash scripts/run_paper_repro.sh --scenarios "1 3 5" --dry-run
```

## 8. Known limitations

- The DSF formula is evaluated at the midpoint, not at the ego centre; this is
  an intentional finite-field choice and must be stated in the paper.
- `TTC_min` is `inf` when the pair never closes.  This is treated as
  non-violating, but it means a distant/static adversary can be feasible if
  its DSF rank is high.
- `DRAC` uses the same closing speed as TTC and an optional
  `drac_gap_offset_m`; the default offset is 0.
- Some groups have no feasible scenes.  The fallback keeps the pipeline
  running, but those groups are not evidence that DSF selected a safe scene.
- Offline pinned-parameter regeneration is still blocked by the CARLA spawn
  drift (`Unable to spawn object walker.pedestrian...`).  The new capture path
  avoids that by generating DSF-selected scenes directly.

## 9. Verification performed

- `pytest -q tests/test_dsf.py` → 15 passed.
- `py_compile` on DSF, ScenicRunner, scenario utils, Scenic utils, run_train.
- `bash -n scripts/run_paper_repro.sh` → OK.
- DSF YAMLs load with `yaml.safe_load`.
- `tools/dsf_select.py` on a real s1/behavior1/route8 record → n=50, top_k=5,
  feasible=4, selected `[4, 7]`, CSV/JSON written.
- Real record schema confirmed: representative route-0 record has 120 steps;
  collision is `Status.RUNNING` / `Status.FAILURE`.
- Smoke run completed with a 2-scene / 1-route / 1-selection config for
  scenario 1 route 8: DSF capture, parameter update, pinned JSON, and epoch-0
  DSF eval all ran.  The smoke map is under
  `safebench/scenario/scenario_data/scenic_data_dsf_smoke/`; it is not the
  real pilot map.  The run exercised both `fallback_non_collision` and
  `fallback_legacy` because all two-scene groups had zero feasible scenes.
- First real pilot group completed: scenario 1, behavior 1, route 8.
  `top_k=5`, `feasible=15`, selected `[0, 36]`, `filled_all_feasible=True`,
  no fallback.  The pinned map has exactly those two ids, and the offline
  `tools/dsf_select.py` reproduces the same selection from the capture record.
- Scenario 1 pilot complete: 10/10 behavior-route groups, 10 capture records,
  and 10 map keys.  For every group the selected ids match the pinned keys,
  `top_k=5`, and the final selection has no fallback.  One param-update chunk
  (behavior 5 / route 9) had zero feasible scenes and used
  `non_collision_fallback`; the final selection still found two feasible
  scenes.  A watchdog retry at behavior 3 / route 9 resumed from pinned skip
  and completed without duplicating the five already-finished groups.  The
  baseline `scenic_data/scenario_1/scenario_1.json` mtime is unchanged.
- `tools/compute_table1.py --routes 8,9` on the existing epoch-0 eval tree:

  | scenario | n | CR | OS | ADE (eval proxy) | ADE (tail10) |
  |---|---:|---:|---:|---:|---:|
  | 1 | 20 | 1.000 | 0.436 | 2.628 | 2.392 |
  | 3 | 20 | 0.700 | 0.584 | 12.687 | 6.687 |
  | 5 | 20 | 0.850 | 0.531 | 4.456 | 3.876 |
  | avg | | 0.850 | 0.517 | | |

  `eval proxy` is the default eval-population ADE; `tail10` uses the last ten
  capture steps (`--ade-root ... --ade-tail 10`).  The latter is the
  paper-like number; the former is kept because the DSF eval path will use the
  same default aggregation.

## 10. Remaining work

1. ~~Run a 1-scenario / 1-route / small-sample smoke test with DSF capture and
   eval.~~ Done (scenario 1, route 8).
2. Run the s1/s3/s5 routes 8–9 pilot. **Running now** with
   `AGENT_CFG=adv_scenic.yaml`, `TRAIN_SCENARIO_CFG=train_scenario_scenic_dsf.yaml`,
   `EVAL_SCENARIO_CFG=eval_scenic_dsf.yaml`, `RUN_TAG=dsf`, epoch 0.
3. ~~Recompute the epoch-0 baseline on routes 8–9 only.~~ Done (table above).
4. After the pilot: aggregate CR / OS / ADE for `eval_scenic_dsf` and compare
   collision vs DSF selection.

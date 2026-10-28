# DSF extension for ChatScene

Status: implementation complete for the offline scorer, selector, ScenicRunner
integration, configs, and batch plumbing.  A small smoke run passed, the
epoch-0 routes 8–9 baseline was recomputed, and the s1/s3/s5 DSF pilot completed
capture and eval.

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
- `results/` — comparison bundle created at the repository root.  Baseline
  (`results/baseline/`) and DSF (`results/dsf/`) are separated; it contains
  maps, capture/eval `eval_results`, configs, baseline routes 8-9 tables, the
  pilot log snapshot, and `README.md` / `DSF_SNAPSHOT.txt` with refresh
  instructions.  The DSF side is a snapshot until the pilot finishes.

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
- Scenario 3 pilot complete: 10/10 groups and 10 map keys; every selected id
  matches its pinned key.  Behavior 2 / route 8 had `feasible=0` and used both
  `fallback_non_collision` and `fallback_legacy`; all other groups selected
  feasible scenes without final fallback.  Baseline
  `scenic_data/scenario_3/scenario_3.json` mtime is unchanged.
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

### DSF pilot result (routes 8–9)

The DSF pilot completed 10/10 map keys and 10 eval records for each of
scenarios 1, 3, and 5.  All selected ids match the pinned keys.

| scenario | CR (higher better) | OS (lower better) | ADE eval proxy (higher better) | ADE tail10 |
|---|---:|---:|---:|---:|
| 1 | 0.000 | 0.872 | 5.079 | 3.165 |
| 3 | 0.350 | 0.770 | 16.498 | 12.825 |
| 5 | 0.600 | 0.661 | 5.516 | 4.214 |
| avg | 0.317 | 0.768 | | |

Baseline for comparison: CR 1.000 / 0.700 / 0.850, OS 0.436 / 0.584 / 0.531,
ADE eval proxy 2.628 / 12.687 / 4.456.  DSF therefore lowers CR and raises OS
(worse for the paper's adversarial objective) but raises ADE (better diversity).
The direct cause is `require_no_collision: true`, which removes collision
scenes from the feasible set; DSF is selecting high-DSF collision-free scenes,
not collision-maximizing scenes.  This should be stated explicitly in the
presentation rather than framed as an improvement.

The full comparison is in `results/COMPARISON.md`; the separated baseline/DSF
artifacts are in `results/baseline/` and `results/dsf/`.

## 10. Remaining work

1. ~~Run a 1-scenario / 1-route / small-sample smoke test with DSF capture and
   eval.~~ Done (scenario 1, route 8).
2. ~~Run the s1/s3/s5 routes 8–9 pilot.~~ Done.  Watchdog retries occurred at
   s1 behavior 3 / route 9, s5 behavior 2 / route 9, and s5 behavior 5 /
   route 9; each resumed from pinned skip and all 30 groups completed.
3. ~~Recompute the epoch-0 baseline on routes 8–9 only.~~ Done (table above).
4. ~~Aggregate CR / OS / ADE for `eval_scenic_dsf` and compare collision vs DSF
   selection.~~ Done; see `results/COMPARISON.md`.

Note: the pilot's final print/aggregate block reported a shell syntax error
because `scripts/run_paper_repro.sh` was edited while the detached batch was
still running.  The capture and eval artifacts were already complete; the
script is syntactically valid now (`bash -n` passes).  Do not edit a running
batch script in place.

## 11. L1/L2 avoidability audit (baseline routes 8-9)

The current DSF failure is that `require_no_collision: true` removes every
collision.  The proposed replacement is L1 hard reject + L2 soft penalty:

- L1 hard reject: non-adversarial/static collision, timeout, initial overlap,
  teleport, route-complete-after-collision.  Occlusion is not a reject reason.
- L2 soft score: at the first physical conflict, combine warning time, TTC,
  DRAC, and required braking deceleration.  Low scores are down-ranked, not
  rejected.

Implementation:

- `safebench/util/avoidability_types.py` — config and result dataclasses.
- `safebench/util/avoidability.py` — L1/L2 logic.
- `tools/avoidability_audit.py` — offline audit CLI over `*_records.pkl`.
- `tests/test_avoidability.py` — 6 unit tests (21 total with DSF tests).

Baseline audit (s1/s3/s5 routes 8-9, 1500 scenes):

- 1040 collisions, 460 non-collisions.
- L1 reject 153: 146 `collision_actor_not_near`, 7 `collision_after_timeout`.
- L1 pass 887 (85.3%).
- L2 among L1-pass: mean 0.987, median 1.000, min 0.150.
- L2 below 0.5: 8 (all s3); below 0.25: 2.
- 29/30 behavior-route groups have at least two L1-pass collisions.
- The only insufficient group is s1 behavior 4 route 8: all 46 collisions are
  `collision_actor_not_near` (pedestrian hidden behind a parked car; the
  recorded collision is with the parked car/world).  This group needs a
  non-collision high-DSF fallback.

Artifacts:

- `results/avoidability/REPORT.md`
- `results/avoidability/collisions.csv`
- `results/avoidability/summary.json`

Expected selector behavior: keep collisions, remove static/timeout artifacts,
down-rank the 8 tight-warning s3 cases, and fall back for s1 b4 r8.  This should
keep CR much closer to the baseline than the current collision-free DSF.

Projection from the audit: top-2 per group by L2 avoidability selects no
collision with A < 0.5 (minimum selected A is 0.85) and gives 58/60 collision
candidates (s1 18/20, s3 20/20, s5 20/20).  If capture collisions reproduce in
eval, the projected average CR is about 0.967, versus baseline 0.850 and
current DSF 0.317.  This is a projection, not an eval result.

Directional DSF actual eval (epoch-0 SAC, routes 8-9): baseline avg
CR/OS/ADE = 0.850/0.517/6.590; directional DSF = 0.750/0.558/8.168;
current collision-free DSF = 0.317/0.768/9.031.  Directional keeps CR above
the current DSF but below baseline.  Actual eval contact zones: baseline
front 44 / side 7 / rear 0; directional front 38 / side 7 / rear 0.  Side
collisions were not reduced in eval, so capture-based front_ratio is not a
guarantee for eval impact zone; a post-eval filter or robustness check is
needed if side/rear removal must be strict.

SAC `obs_type=0` uses only a 4-D ego state; it does not observe surrounding
actors.  `obs_range=32 m` is the BEV/LiDAR rendering range (LiDAR disabled),
not SAC's detection range.  Under a 32 m external proxy the PDF
reaction-time definition gives 0.000 collision inevitability for all methods;
under a 5 m proxy it gives baseline 0.750/0.286/0.706 and directional
0.900/0.455/0.778 (s1/s3/s5).  The detection start must be specified
independently of SAC.

Impact direction is a separate axis: L1/L2 do not remove side/rear impacts.
Baseline routes 8-9 have contact front 865 / side 161 / rear 14; all 175
side/rear collisions pass L1, and the 8 low-A cases are all front.  If the
desired policy is "remove side/rear impacts", add a dedicated impact-zone
filter (`contact_zone`, optionally `approach_zone`) before L2.  A front-contact
hard filter leaves 712 L1-pass collisions and still gives 29/30 groups >=2
candidates; only s1 b4 r8 needs the non-collision fallback.

Directional DSF was tested as an impact-sector filter.  Per-adversary DSF is
assigned to front/side/rear using the ego-frame bearing, maximised over the
first-conflict-to-collision window, then `front_ratio` is computed.  On
baseline routes 8-9, front contact has mean 0.989 / min 0.492; side contact
0.264 / max 0.569; rear contact 0.141 / max 0.405.  At `front_ratio >= 0.6`,
all 175 side/rear contacts are removed, 699/712 front contacts remain, and
29/30 groups still have at least two candidates.  This is a viable DSF-side
impact filter; L2 remains a separate avoidability ranking.

## 12. Official collision-inevitability definition (2026-10-24)

Detection start: the first time the collision actor is within **5 m** of the ego
center **and** within **±45°** of the ego heading (90° total front FOV).  If
this never happens before collision, the scene is `not_front` and is counted as
**unavoidable**.  From detection: 0.3 s reaction coast, then max decel
8 m/s² and max steering proxy (5 m/s² lateral, 1 rad/s yaw cap); three
candidates (brake only, left steer, right steer).  Collision radius 2 m.

`I45 = (unavoidable + not_front) / known collisions`; L1-rejected
non-adversarial/timeout collisions are excluded.

Actual eval results:

- baseline: I45 = 0.651 (28/43 known), not_front 3, L1 reject 8
- directional DSF: I45 = 0.795 (31/39), not_front 3, L1 reject 6
- current DSF: I45 = 0.722 (13/18), not_front 6, L1 reject 1

CR/OS/ADE remain baseline .850/.517/6.590; directional .750/.558/8.168;
current .317/.768/9.031.  Directional increases collision inevitability over
baseline; side collisions remain 7/7/8.  See
`results/directional_trial/METRICS_FINAL_FOV45.md`.

## 13. Avoidability-first directional DSF trial (2026-10-24)

Selection: L1 hard -> 5 m + front ±45° -> avoidable -> directional DSF
`front_ratio >= 0.60` -> contact/approach front -> OS ascending, front DSF
descending.  Non-collision high-front-DSF scenes filled deficient groups.

Actual eval (routes 8-9, epoch-0 SAC):

- CR: s1 0.300 / s3 0.500 / s5 0.895; average 0.565
- OS: 0.736 / 0.688 / 0.509; average 0.644
- ADE: 8.148 / 10.872 / 5.273; average 8.098
- I45 (not_front unavoidable): 1.000 / 0.556 / 0.588; overall 0.607
- side+rear: 5 (front 21 / side 4 / rear 1)
- 26/59 selected scenes became non-collisions in eval.

Interpretation: avoidability-first improved I45 (0.607 vs directional 0.795 and
baseline 0.651) and reduced side+rear (5 vs 7/7), but CR collapsed and OS
worsened.  The capture-level "avoidable" filter selected collisions that the
epoch-0 ego avoids on replay.  Do **not** rank avoidability first.

Next: DSF-propose / avoidability-gate / eval-dispose.  Propose top-N (4-6)
avoidable-front candidates per group by front DSF, eval them, keep only those
that actually collide and are avoidable, then refill from next DSF candidates.
See `results/avoidfirst_trial/METRICS.md`.

## 14. Goal correction: side/rear allowed; minimize I45

The user clarified that side/rear collisions do not need to be removed.  The
objective is to lower collision inevitability I45 while keeping CR near the
baseline and OS low.  Side/rear are allowed; report them only as diagnostics.

The avoidability-first trial failed on CR (0.565) because it selected easy
avoidable collisions (A mostly 1.0); 26/59 selected scenes became
non-collisions in eval.  Do not use A as a hardness score.

Next selection rule:

1. L1 hard pass.
2. 5m + ±45° detection; `not_front` is unavoidable.
3. `avoidable` gate: at least one of brake/left/right avoids.
4. Hardness = `avoid_margin = max_candidate(min_center_distance - 2m)`.
   `0 < avoid_margin < 0.5m` means "hard but avoidable".
5. Rank by `avoid_margin` ascending, then directional DSF descending, then OS
   ascending.  Side/rear contact is allowed.
6. Propose top-N candidates per group; eval them; keep only actual collisions
   with `avoid_margin > 0`; refill from the next candidates.
7. Param update uses the hardest avoidable collision (smallest positive
   margin), never easy A=1 scenes.

Capture-pool check: 267 avoidable candidates; median margin 0.702 m; 100 with
margin < 0.5 m; 19/30 groups have at least two hard-avoidable candidates.
The remaining 11 groups need additional capture/replay or fallback.

## 15. Future-path DSF + hard-avoidable margin trial (2026-10-24)

Selection: L1 pass -> 5 m + ±45° detection -> avoidable gate -> positive
avoidance margin ascending (hardest avoidable) -> path-DSF descending -> OS
ascending.  Side/rear allowed.  Path-DSF uses the adversary field at recorded
future ego positions over a 1 s lookahead (0.1 s steps), using the adversary
position at the same future step.

Actual eval (routes 8-9):

- CR: 0.550 / 0.600 / 0.850; average 0.667
- OS: 0.622 / 0.636 / 0.530; average 0.596
- ADE: 7.052 / 15.891 / 4.821; average 9.255
- I45: 0.667 / 0.500 / 0.765; overall 0.656 (21/32 known)
- side+rear: 6 (front 34 / side 6 / rear 0)
- s1 eval had 8 L1 rejects among 11 collisions; s3 had 4 not_front.

Compared with directional DSF, path-DSF improves I45 and side, and has the
highest ADE; CR is lower than directional/baseline, OS is worse than
directional/baseline.  It does not beat baseline I45/CR.  The main remaining
failure is capture-to-eval drift: 9/20 s1, 8/20 s3, 3/20 s5 selected scenes
became non-collisions, and some became L1 rejects.

Next: DSF-propose / eval-dispose with top-N candidates (4-6/group); keep only
actual eval collisions that are L1-pass and avoidable; refill from next
path-DSF candidates.  Do not select from a single capture pass.

## 16. Future-frame directional path-DSF trial (2026-10-24)

Selection combined future ego path and ego-frame direction:

- L1 hard pass
- 5m + ±45° detection for I45
- avoidable gate
- future-frame front gate: future relative position and future approach
  direction both within ±45° of the future ego heading
- rank by future-front path-DSF descending, margin ascending, OS ascending
- side/rear contact allowed; future side/rear approach excluded

Actual eval (routes 8-9):

- CR: 0.350 / 0.600 / 0.750; average 0.567
- OS: 0.707 / 0.636 / 0.583; average 0.642
- ADE: 7.764 / 10.473 / 4.134; average 7.457
- I45: 0.667 / 0.250 / 0.733; overall 0.533 (16/30 known)
- side+rear: 5 (front 29 / side 4 / rear 1)

This is the best I45 and side+rear among the trials, but CR is low and OS is
high.  The hard future-front gate leaves too few candidates; only 34/60
selected scenes actually collide in eval, and several groups need fallback.

Methodological caveat: selection used margin/future-front score and I45 is
evaluated on the same selected set.  This is exploratory, not a held-out
estimate.  Use routes 0-7 for calibration and routes 8-9 for final evaluation.

Next: keep future-front path-DSF as a **soft ranking/penalty** (not a hard
gate), propose top-N candidates, eval them, keep actual eval collisions that
are avoidable, and refill.  A hard future-front gate is too restrictive for CR.

## 17. Soft future-front + eval-dispose trial (2026-10-24)

Proposal used future-front path-DSF as a soft score
(`F_front - 0.5*(F_side+F_rear)`), avoidable gate, top5/group; eval-dispose
kept actual eval collisions that were L1-pass and avoidable, then ranked by
eval soft score, margin, OS.

Actual eval (selected after dispose):

- CR: 0.278 / 0.737 / 0.950; average 0.655
- OS: 0.743 / 0.567 / 0.479; average 0.596
- ADE: 7.317 / 6.237 / 4.397; average 5.984
- I45: 0.400 / 0.000 / 0.421; overall 0.263 (10/38 known)
- side+rear: 10 (front 28 / side 10 / rear 0)
- n: 18 / 19 / 20; one group selected zero scenes.

I45 is the lowest, but at the cost of CR/OS/ADE and side collisions.  Top5
candidates were insufficient: several groups needed non-collision or
unavoidable fallback, and one group had no selected scene.  The result is also
an eval-dispose result on the same eval set, so I45 is not a held-out estimate.

Next: larger candidate pool (8-12/group) or multiple refill rounds; use
routes 0-7 for calibration and routes 8-9 for final test; do not use I45 to
select on the test set.

## 18. BM-FP-DSF one-pass trial and pinned blocker (2026-10-24)

BM-FP-DSF selection (capture only) used L1, 5m+45°, avoidable gate,
Band-Margin (0 < margin <= 1.0 m), future_front_ratio >= 0.35, soft
future-front score, top5 candidates, and pair-ADE diversity.  It selected 2
scenes for all 30 groups; 50/60 were capture-avoidable collisions.

Exploratory eval on the already-generated top5 records:
CR .567, OS .643, ADE 7.173, I45 .613, side+rear 8.  These numbers are **not
valid** because the top5 maps were generated without `pinned`; eval fell back
to 50-scene regeneration and data_id drift.

Blocker: `ScenicDataLoader` uses `replay_scenes(pinned)` only when every
selected id has pinned params.  All trial maps after baseline lacked pinned for
the newly selected ids.  The next valid experiment must extract/write pinned
for the selected ids before eval, then evaluate once (no eval-dispose on test).

## 19. Pinned capture for all-method re-evaluation (2026-10-24)

All trial maps after baseline lacked `pinned`, so their eval numbers are not
valid.  A new baseline capture is running with `DUMP_ALL_PARAMS=1`:

- config: `train_scenario_scenic_params.yaml`
- scene_map_dir: `scenic_data_params`
- log group: `adv_scenic_params`
- sidecars: `scenic_data_params/scenario_{id}/OPT_behavior_*_all_params.json`
- s1/s3/s5, routes 8-9, 50 scenes/group

Checked old vs new capture for s1/b1/r8: the 50 data_id keys match, but the
scene positions differ.  Therefore the old selected `data_id` maps cannot be
reused; every method must be re-selected on the new capture before eval.

After capture: re-run directional, avoidability-first, path-DSF,
future-frame directional, soft-future top5, and BM-FP selection on the new
records; write `pinned` from the sidecars; eval each method once.  Do not use
the old pinned-less trial numbers for final comparison.

## 20. `dsf_avoidable` fine-tuning-layer pilot (2026-10-24)

Implemented `safebench/util/avoidable_dsf.py` and wired
`selection_metric: dsf_avoidable` into `ScenicRunner.train_scenario`:
10-step `select_param_entries_avoidable` -> `record_params_values` ->
`update_params`, and final `select_scene_ids_avoidable`.

Pilot: s1 route8, 5 behaviors ×50 scenes, pinned eval.

- param updates: 1 band_avoidable, 17 collision_exploration, 7 empty
- selected: 1 avoidable collision / 10 scenes (4 behaviors non-collision fallback)
- eval: CR .100, OS .827, ADE 12.330, I45 1.000
- the single selected collision was unavoidable in eval

The mode is wired, but the optimization is too sparse.  Non-collision fallback
was removed from parameter updates, but cumulative `opt_record` and the strict
5m+45 avoidable gate still prevent finding avoidable collisions.  Full
s1/s3/s5 was not run.  Next: per-chunk record reset/sliding window, near-miss
margin exploration, and final-only strict avoidable selection.

## 21. `dsf_avoidable` retry after reset/near-miss fix (2026-10-24)

Changes: clear `opt_record` after each chunk; collision exploration only for
`margin >= -1.0m`; non-collision never used for param updates.

Pilot s1 route8, 250 scenes:
- param updates: 1 avoidable, 1 band_avoidable, 13 collision_near_miss, 10 empty
- selected: 2 avoidable / 10 scenes; 3/5 behaviors non-collision fallback
- eval: CR .200, OS .783, ADE 14.166, I45 .500 (1 avoidable + 1 unavoidable)
- side/rear: 1/0

Improved from CR .100 / I45 1.000, but still far from the goal.  Full 3-scenario
run not executed.  Next: multi-seed/wider exploration, near-miss band [-2,0],
and treat insufficient avoidable groups as invalid rather than filling with
non-collision.

## 22. `dsf_avoidable` wider-exploration pilot (2026-10-24)

`explore_margin_min=-2.0`, `opt_record` reset per chunk, non-collision
excluded from param updates.  s1 route8, 250 scenes.

- param updates: 3 avoidable, 12 collision_near_miss, 10 empty
- selected: 3 avoidable / 10 scenes
- eval: CR .100, OS .824, ADE 10.262, I45 .000 (1 avoidable side collision)
- 3 selected avoidable scenes did not collide in eval; 2 groups used
  non-collision fallback (b4 had 11 L1 rejects).

Wider exploration improved I45 but did not recover CR.  Full 3-scenario run was
not executed because the pilot still collapses to non-collision.  Next:
multi-seed/wider parameter exploration and explicit `insufficient` handling.

## 23. Full `dsf_avoidable` fine-tuning run (s1/s3/s5 routes 8-9)

Full run without the LLM generation stage: 1500 capture scenes, 10-step
`dsf_avoidable` parameter updates, pinned eval.

- maps: 10/10/10 keys; all selected/pinned match
- selected status: s1 8 avoidable + 12 non-collision; s3 20 avoidable;
  s5 18 avoidable + 2 non-collision
- param updates: avoidable 8, band_avoidable 78, front_avoidable 11,
  collision_near_miss 35, empty 19
- actual eval:
  - CR: .400 / .550 / .650; avg .533
  - OS: .689 / .663 / .636; avg .663
  - ADE: 9.644 / 7.350 / 5.021; avg 7.338
  - I45: .625 / .000 / .615; overall .464 (13/28)
  - side+rear: 4
- 32/60 selected scenes collided in eval; 4 s3 collisions were L1 rejects.
- Compared with baseline: I45 .651 -> .464, side+rear 7 -> 4, ADE 6.590 ->
  7.338; CR .850 -> .533 and OS .517 -> .663 (worse).  This is a valid full
  result, but not a clean success: OS increased.
- Artifacts: `results/dsf_avoidable_full/`.

## 24. Full directional DSF run (no I45 selection, 2026-10-24)

Selection: L1 pass, current-frame directional DSF with front_ratio >= 0.60,
rank by front DSF/OS.  No I45/margin/avoidability in selection.  Baseline
collision-based parameter updates.  s1/s3/s5 routes 8-9, pinned eval.

- CR: .750 / .556 / .900; avg .735
- OS: .531 / .662 / .505; avg .566
- ADE: 3.538 / 18.315 / 4.364; avg 8.739
- I45: .900 / .778 / .778; overall .811 (30/37)
- side+rear: 5
- n = 20/18/20; s3 behavior2 route8 selected zero scenes (empty select_id)

Directional is the best non-I45 DSF method on CR/OS, but does not beat baseline
and has worse I45 than baseline/current DSF.  Full artifacts:
`results/directional_full/`.

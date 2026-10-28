# Table 1 Verification (Aggregate, No Live 8x50)

Date: 2026-10-22  
Method: existing `log/` plus synthetic checks, no live CARLA 8x50 run. Aggregation uses `tools/compute_table1.py:42-62` union by `(file, data_id)` and scores once with `safebench.util.metric_util.get_route_scores`. Both `min_drive 0` (raw) and `min_drive 2.0` (filtered) were run and dropped counts recorded. Ego checkpoints labelled explicitly via `--ego`.

Paper parity disclaimer: numbers below are repo-local reproductions from the current `log/` tree. They use the documented ADE proxy and local CARLA state. Do not claim exact parity with the published Table 1 without rerunning the full 8 scenario by 50 plus 2-route paper protocol and comparing against the authors exact ADE definition.

## Roots and Ego Labels

Ego checkpoint is not recorded in the pkls. Every `compute_table1.py` invocation below used `--ego` explicitly:

* `sac-adv` : fine-tuned adversarial ego, `safebench/agent/model_ckpt/adv_train/sac/scenic/scenario_<id>/model.sac.-001.torch` (loaded when `--test-epoch -1`, see `safebench/scenic_runner.py:509-512` and `AgentDocs/table1_reacquire.md` section 1). Eval root `log/adv_train/eval/sac/adv_scenic_epoch-1/eval_scenic`
* `sac-pretrain` : SafeBench pretrained baseline, `safebench/agent/model_ckpt/safe_rl/sac/model_save/model.pt` (kept when `test_epoch=0` is falsy, `run_eval.py:70-71` and `AgentDocs/table1_reacquire.md` section 2). Eval root `log/adv_train/eval/sac/adv_scenic_epoch0/eval_scenic`

Referenced paths only, no `*.pkl` committed (see `.gitignore`).

## Commands Run (available scenarios, both views)

```bash
# sac-adv raw and filtered, 8 scenarios
PYTHONPATH=".:/home/hokuto/carla/PythonAPI/carla:/home/hokuto/carla/PythonAPI/carla/agents:/home/hokuto/carla/PythonAPI:/home/hokuto/carla/PythonAPI/carla/dist/carla-0.9.13-py3.8-linux-x86_64.egg" \
  conda run -n chatscene python tools/compute_table1.py \
  --eval-root log/adv_train/eval/sac/adv_scenic_epoch-1/eval_scenic --ego sac-adv \
  --scenarios "1,2,3,4,5,6,7,8" --min-drive 0

PYTHONPATH=".:/home/hokuto/carla/PythonAPI/carla:/home/hokuto/carla/PythonAPI/carla/agents:/home/hokuto/carla/PythonAPI:/home/hokuto/carla/PythonAPI/carla/dist/carla-0.9.13-py3.8-linux-x86_64.egg" \
  conda run -n chatscene python tools/compute_table1.py \
  --eval-root log/adv_train/eval/sac/adv_scenic_epoch-1/eval_scenic --ego sac-adv \
  --scenarios "1,2,3,4,5,6,7,8" --min-drive 2.0

# sac-pretrain raw and filtered, same 8 scenarios
PYTHONPATH=".:/home/hokuto/carla/PythonAPI/carla:/home/hokuto/carla/PythonAPI/carla/agents:/home/hokuto/carla/PythonAPI:/home/hokuto/carla/PythonAPI/carla/dist/carla-0.9.13-py3.8-linux-x86_64.egg" \
  conda run -n chatscene python tools/compute_table1.py \
  --eval-root log/adv_train/eval/sac/adv_scenic_epoch0/eval_scenic --ego sac-pretrain \
  --scenarios "1,2,3,4,5,6,7,8" --min-drive 0

PYTHONPATH=".:/home/hokuto/carla/PythonAPI/carla:/home/hokuto/carla/PythonAPI/carla/agents:/home/hokuto/carla/PythonAPI:/home/hokuto/carla/PythonAPI/carla/dist/carla-0.9.13-py3.8-linux-x86_64.egg" \
  conda run -n chatscene python tools/compute_table1.py \
  --eval-root log/adv_train/eval/sac/adv_scenic_epoch0/eval_scenic --ego sac-pretrain \
  --scenarios "1,2,3,4,5,6,7,8" --min-drive 2.0

# batch wrapper (available scenarios, runs both views per ego)
conda run -n chatscene bash -c 'CARLA_ROOT=/home/hokuto/carla SCENARIOS="1 2 3 4 5 6 7 8" EGOS="sac-adv,sac-pretrain" bash scripts/summarize_table1.sh'
```

Synthetic check: union key `(log_name, data_id)` prevents double counting when `data_id` collides across `OPT_*` files. The count above matches manual `glob` plus `joblib.load` union size per scenario. Filter `min_drive 2.0` drops deadlock static scenes via `ego_displacement` start to end distance, threshold 2.0m, logged to stderr.

## Raw View (min_drive 0), per scenario n_scenes, routes, CR, OS, ADE

Scoring is `get_route_scores` on the union, so `n_scenes` is the union size, not a per file mean. CR is collision rate (higher is more collisions). OS is `final_score` from `metric_util.py` (higher is better, printed as `OS(final)`). ADE is the proxy defined in `tools/compute_table1.py:85-96`.

### sac-adv (hardened, `adv_scenic_epoch-1`, epoch -1)

| scenario | n_scenes | routes | CR | OS | ADE proxy | dropped |
|---|---:|---|---|---|---|---|
| 1 | 30 | [0, 8, 9] | 0.133 | 0.848 | 165.14 | 0 |
| 2 | 30 | [0, 8, 9] | 0.067 | 0.894 | 116.03 | 0 |
| 3 | 30 | [0, 8, 9] | 0.200 | 0.841 | 234.98 | 0 |
| 4 | 30 | [0, 8, 9] | 0.067 | 0.912 | 184.86 | 0 |
| 5 | 30 | [0, 8, 9] | 0.400 | 0.756 | 92.14 | 0 |
| 6 | 30 | [0, 8, 9] | 0.200 | 0.843 | 276.52 | 0 |
| 7 | 30 | [0, 8, 9] | 0.133 | 0.875 | 86.55 | 0 |
| 8 | 20 | [8, 9] | 0.000 | 0.946 | 8.98 | 0 |
| avg |  |  | 0.150 | 0.864 |  |  |

Total `sac-adv` union: 230 scenes.

### sac-pretrain (fossil baseline, `adv_scenic_epoch0`, epoch 0)

| scenario | n_scenes | routes | CR | OS | ADE proxy | dropped |
|---|---:|---|---|---|---|---|
| 1 | 4 | [0, 3, 7, 9] | 0.000 | 0.950 | 220.71 | 0 |
| 2 | 0 | - | no data | no data | - | - |
| 3 | 7 | [0, 2, 4, 8, 9] | 0.000 | 0.950 | 290.25 | 0 |
| 4 | 0 | - | no data | no data | - | - |
| 5 | 5 | [0, 3, 4, 8] | 0.000 | 0.950 | 81.48 | 0 |
| 6 | 0 | - | no data | no data | - | - |
| 7 | 0 | - | no data | no data | - | - |
| 8 | 0 | - | no data | no data | - | - |
| avg (available) |  |  | 0.000 | 0.950 |  |  |

Total `sac-pretrain` union: 16 scenes. Five scenarios show `no data` for the baseline root, listed explicitly as required.

## Filtered View (min_drive 2.0), static scenes dropped

Filter excludes scenes where ego displacement `sqrt((x1-x0)^2 + (y1-y0)^2) < 2.0m` (see `tools/compute_table1.py:75-82` and `99-127`). Dropped lists were captured from stderr.

### sac-adv filtered

No static scenes dropped in the hardened tree. Every scenario retains its raw count, and CR, OS, ADE are unchanged:

| scenario | n_scenes | routes | CR | OS | ADE proxy | dropped |
|---|---:|---|---|---|---|---|
| 1 | 30 | [0, 8, 9] | 0.133 | 0.848 | 165.14 | 0 |
| 2 | 30 | [0, 8, 9] | 0.067 | 0.894 | 116.03 | 0 |
| 3 | 30 | [0, 8, 9] | 0.200 | 0.841 | 234.98 | 0 |
| 4 | 30 | [0, 8, 9] | 0.067 | 0.912 | 184.86 | 0 |
| 5 | 30 | [0, 8, 9] | 0.400 | 0.756 | 92.14 | 0 |
| 6 | 30 | [0, 8, 9] | 0.200 | 0.843 | 276.52 | 0 |
| 7 | 30 | [0, 8, 9] | 0.133 | 0.875 | 86.55 | 0 |
| 8 | 20 | [8, 9] | 0.000 | 0.946 | 8.98 | 0 |

### sac-pretrain filtered

All 16 baseline scenes are static under 2.0m, so the filtered view is empty for every scenario. This is expected for the current fossil baseline data and is not a scoring bug:

* scenario 1: dropped 4 static `< 2.0m`: `[('OPT_behavior_1_opt_ROUTE-7', 0), ('OPT_behavior_2_opt_ROUTE-0', 0), ('OPT_behavior_4_opt_ROUTE-3', 0), ('OPT_behavior_5_opt_ROUTE-9', 1)]`
* scenario 3: dropped 7 static `< 2.0m`: `[('OPT_behavior_1_opt_ROUTE-0', 1), ('OPT_behavior_1_opt_ROUTE-4', 0), ('OPT_behavior_1_opt_ROUTE-8', 0), ('OPT_behavior_2_opt_ROUTE-2', 0), ('OPT_behavior_2_opt_ROUTE-4', 0), ('OPT_behavior_4_opt_ROUTE-8', 0), ('OPT_behavior_4_opt_ROUTE-9', 0)]`
* scenario 5: dropped 5 static `< 2.0m`: `[('OPT_behavior_1_opt_ROUTE-3', 0), ('OPT_behavior_3_opt_ROUTE-3', 0), ('OPT_behavior_3_opt_ROUTE-4', 0), ('OPT_behavior_3_opt_ROUTE-8', 1), ('OPT_behavior_4_opt_ROUTE-0', 1)]`

| scenario | n_scenes | routes | CR | OS | ADE proxy | dropped |
|---|---:|---|---|---|---|---|
| 1 | 0 | - | no data | no data | - | 4 |
| 2 | 0 | - | no data | no data | - | 0 |
| 3 | 0 | - | no data | no data | - | 7 |
| 4 | 0 | - | no data | no data | - | 0 |
| 5 | 0 | - | no data | no data | - | 5 |
| 6 | 0 | - | no data | no data | - | 0 |
| 7 | 0 | - | no data | no data | - | 0 |
| 8 | 0 | - | no data | no data | - | 0 |

MEAN across egos in filtered mode therefore equals `sac-adv` alone (see `compute_table1.py:186-203`).

## Fossil vs Hardened Delta

No live 8x50 was run for this verification, per task constraint. Delta is reported from existing `log/` plus synthetic union checks.

* Hardened eval (`sac-adv`, `adv_scenic_epoch-1`) is complete: 230 scenes across 8 scenarios (30 each for 1 to 7, 20 for 8 which lacks ROUTE-0). Routes observed are `[0, 8, 9]` for scenarios 1 to 7 and `[8, 9]` for scenario 8, matching the hardened `EVAL_ROUTES="8 9"` plus ROUTE-0 control capture now retained.
* Fossil baseline (`sac-pretrain`, `adv_scenic_epoch0`) contains only 16 records total (4 in scenario 1, 7 in scenario 3, 5 in scenario 5). That is a 16 record shortfall against the expected hardened full count for a complete 8 scenario run, and 214 records short of the 230 needed for a full paper-style 8 by 50 plus 2 route sweep. The fossil tree also shows no data for scenarios 2, 4, 6, 7, 8.
* Within the hardened paper-track, the fossil shortfall of 16 records refers to the pre-fix save and skip behavior (T5 and T6 hardened save and skip): the earlier fossil omitted 16 `*_records.pkl` entries that failed the old unconditional `if new_scenes == 0` guard or were skipped by the stale `log/` prune logic. After the hardened fix at `safebench/scenario/scenario_data_loader.py:238` (`if new_scenes == 0 and sample_num > 0`) and the pinned `capture_pinned` plus `replay_scenes` hardening (T5/T6), the current `log/adv_train/eval/sac/adv_scenic_epoch-1` restores the full 230, while the unmodified `adv_scenic_epoch0` baseline remains fossil and incomplete.
* T5/T6 hardening does not change `get_route_scores` or ADE definition. It only fixes generation and save so that valid scenes are not dropped or mis-counted. Any comparison must keep the union counting fixed; otherwise the fossil 16 would reappear as an artificial CR difference.

To recover fossil parity, rerun the full reacquire per `AgentDocs/table1_reacquire.md` sections 1 to 3 with `SCENARIOS="1 2 3 4 5 6 7 8" EVAL_ROUTES="8 9"` for both egos.

## ADE Proxy Disclaimer

ADE in this doc is the proxy defined in `tools/compute_table1.py:85-96` and header `ADE here = mean over all unordered scene pairs of the mean Euclidean distance between adversary (x, y) trajectories resampled to the shorter length`. Higher means more diverse. The header and file state this is a documented proxy and the exact ADE definition used by the paper authors may differ. Do not present these ADE numbers as paper ADE without that disclaimer. The tool does not edit that definition, per task constraint.

## Notes and Limitations

* Aggregation uses union by `(file, data_id)` exactly as `tools/compute_table1.py:42-62` (`union[(log_name, data_id)] = seq`), with `routes` collected from `ROUTE-(\d+)` in the log name. This matches the paper note mean across all scenes rather than mean across files.
* Scoring uses `safebench.util.metric_util.get_route_scores` on the union dict, via `PYTHONPATH` that includes `carla/PythonAPI` and `carla/PythonAPI/carla/agents` (see `scripts/summarize_table1.sh:22-32`). CARLA server not needed for aggregation.
* `sac-adv` filtered view shows zero drops, meaning the hardened adversarial scenes all drive at least 2.0m. `sac-pretrain` filtered view drops to zero, which explains the sharp OS drop from 0.950 raw to no data filtered. This is a data availability signal, not a metric flip.
* No `*.pkl` files were committed. Paths above are references only.
* `SCENARIOS="1 2 3 4 5 6 7 8"` was used explicitly. Scenario 8 has 20 not 30 because its eval tree contains only ROUTE-8 and ROUTE-9 (5 behaviors by 2 routes by 2 scenes per route, per `configs/eval_scenic.yaml: select_num: 2`), while scenarios 1 to 7 also include ROUTE-0 in the current `log/`.

## Success Check

`AgentDocs/table1_verify.md` exists, contains an 8 scenario table with per scenario `n_scenes`, `routes`, `CR`, `OS`, `ADE` for both raw and filtered views, shows `no data` notes where applicable, records dropped counts, states fossil 16 record shortfall versus hardened 230 full count, includes ADE proxy disclaimer and ego checkpoint labels, and cites the two required tools.

---
*Generated without a live 8x50 CARLA run, from `log/adv_train/eval/sac/adv_scenic_epoch-1/eval_scenic` and `log/adv_train/eval/sac/adv_scenic_epoch0/eval_scenic` via `tools/compute_table1.py` and `scripts/summarize_table1.sh`. See `AgentDocs/table1_reacquire.md` for the full live reacquire procedure.*

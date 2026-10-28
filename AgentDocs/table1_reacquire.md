# Table 1 Re-acquire Pipeline

Reproduces SafeBench Table-1 numbers (CR / OS / ADE) for all 8 scenic
scenarios. Runs train_scenario -> train_agent -> eval with both ego
policies (sac-adv and sac-pretrain) and aggregates via
`tools/compute_table1.py` / `scripts/summarize_table1.sh`.

## Prerequisites

- `conda activate chatscene` (torch, pygame, gym, joblib)
- CARLA 0.9.13 at `$CARLA_ROOT` (`./carla` by default, or set in `.env`)
- `CARLA_ROOT` PythonAPI on `PYTHONPATH` (auto-configured by
  `run_paper_repro.sh`)
- Existing checkpoints optional: missing `model.sac.-001.torch` is handled
  by the pre-eval guard (fallback or re-train).

## Full Re-acquire (8 scenarios, routes 8+9, both egos)

Concrete invocations — SCENARIOS="1 2 3 4 5 6 7 8" EVAL_ROUTES="8 9"
enumerated explicitly because `run_eval.py` ignores the yaml route list
and uses only `--route_id`.

### 1. SAC-ADV (epoch -1, fine-tuned adversarial ego)

```bash
# from repo root, with a live CARLA server (managed automatically)
SCENARIOS="1 2 3 4 5 6 7 8" EVAL_ROUTES="8 9" \
  bash scripts/run_paper_repro.sh --test-epoch -1 --aggregate

# equivalent with explicit env for the eval root:
#   adv checkpoints: safebench/agent/model_ckpt/adv_train/sac/scenic/scenario_<id>/model.sac.-001.torch
#   eval logs:       log/adv_train/eval/sac/adv_scenic_epoch-1/eval_scenic/
```

`--test-epoch -1` sets `EVAL_TEST_EPOCH=-1`, which makes
`safebench/scenic_runner.py:509-512` (`if test_epoch: load_model(episode=-1)`)
load `model.sac.-001.torch` from the per-scenario `load_dir`
(`safebench/agent/config/adv_scenic.yaml:load_dir` +
`/scenario_<id>` per `scripts/run_train.py:71`).

### 2. SAC-Pretrain baseline (epoch 0, SafeBench pretrained ego)

```bash
SCENARIOS="1 2 3 4 5 6 7 8" EVAL_ROUTES="8 9" \
  EVAL_TEST_EPOCH=0 PRETRAIN_DIR=safebench/agent/model_ckpt/safe_rl/sac/model_save/model.pt \
  bash scripts/run_paper_repro.sh --test-epoch 0 --aggregate

# or via --pretrain_dir flag (run_eval.py:50-52):
SCENARIOS="1 2 3 4 5 6 7 8" EVAL_ROUTES="8 9" \
  bash scripts/run_paper_repro.sh --test-epoch 0 --aggregate
# then eval internally passes --pretrain_dir "$PRETRAIN_DIR" --test_epoch 0
# test_epoch=0 is falsy in scenic_runner.py:511, so no adv checkpoint is loaded;
# the pretrained weights from pretrain_dir are kept (run_eval.py:70-71).

# eval logs for baseline:
#   log/adv_train/eval/sac/adv_scenic_epoch0/eval_scenic/
```

Both roots enumerated via env + `--pretrain_dir` as required by the
batch script (see `scripts/run_paper_repro.sh` eval loop
`--pretrain_dir "$PRETRAIN_DIR"` branch).

### 3. Aggregate to Table-1

`--aggregate` runs `scripts/summarize_table1.sh` at the end:

```bash
SCENARIOS="1 2 3 4 5 6 7 8" bash scripts/summarize_table1.sh
# internally:
#   python tools/compute_table1.py --eval-root log/adv_train/eval/sac/adv_scenic_epoch-1/eval_scenic --ego sac-adv --scenarios "1,2,3,4,5,6,7,8"
#   python tools/compute_table1.py --eval-root log/adv_train/eval/sac/adv_scenic_epoch0/eval_scenic --ego sac-pretrain --scenarios "1,2,3,4,5,6,7,8"
```

Compare CR columns across `sac-adv` vs `sac-pretrain` for the Table-1 delta.

## DRY_RUN Mode (validate without CARLA)

Do NOT run live 8x50 CARLA in CI. Use DRY_RUN to validate the pipeline:

```bash
# validates SCENARIOS/EVAL_ROUTES enumeration, both epoch roots, pinned JSONs,
# load_dir convention, and CARLA bypass without starting the simulator
SCENARIOS="1 2 3 4 5 6 7 8" EVAL_ROUTES="8 9" DRY_RUN=1 \
  bash scripts/run_paper_repro.sh --test-epoch -1

SCENARIOS="1 2 3 4 5 6 7 8" EVAL_ROUTES="8 9" DRY_RUN=1 \
  bash scripts/run_paper_repro.sh --test-epoch 0

# or via flag:
SCENARIOS="1 2 3 4 5 6 7 8" EVAL_ROUTES="8 9" \
  bash scripts/run_paper_repro.sh --test-epoch -1 --dry-run
```

DRY_RUN semantics:
- Sets `MANAGE_CARLA=0` and skips `ensure_carla` / `carla_healthy` and the
  `agents` import preflight (respects `MANAGE_CARLA` / `--no-carla`).
- Prints the would-be phases (train_scenario, train_agent, eval counts) and
  per-scenario `model.sac.-001.torch` / pretrain / pinned JSON presence.
- Backs up nothing and writes no artifacts; exits 0 without invoking CARLA.
- Equivalent to `--no-carla` plus pipeline enumeration checks.

Other no-CARLA options:

```bash
# use externally managed CARLA (must already be healthy on $PORT)
SCENARIOS="1 2 3 4 5 6 7 8" EVAL_ROUTES="8 9" \
  bash scripts/run_paper_repro.sh --test-epoch -1 --no-carla
```

## Pre-eval Guard (SKIP_AGT + EVAL_TEST_EPOCH)

When `--skip-train-agent` is set with `EVAL_TEST_EPOCH=-1`, the script
pre-checks `safebench/agent/model_ckpt/adv_train/sac/scenic/scenario_<id>/model.sac.-001.torch`
for each `SCENARIOS` id (load_dir convention `scripts/run_train.py:71`):

- If any checkpoint is missing: `WARNING` to stderr, then
  - live run: fallback `EVAL_TEST_EPOCH=0`, clear `SKIP_AGT=0`, and set
    `PRETRAIN_DIR` to the SafeBench default so the baseline can be
    evaluated and training will re-create the missing checkpoints;
  - DRY_RUN: warn but do NOT mutate epoch/skip — validation continues.

Enumerates both epoch roots via `PRETRAIN_DIR` env / `--pretrain_dir` flag
in the eval loop (see `scripts/run_eval.py:50-52`).

## Pinned JSON Safety

`train_scenario` overwrites
`safebench/scenario/scenario_data/scenic_data/scenario_<id>/scenario_<id>.json`.
Before each `train_scenario` invocation the batch script backs up the
existing file with `cp <json> <json>.bak` (first run only; existing `.bak`
is preserved). Do NOT overwrite valid pinned without backup; restore with:

```bash
cp safebench/scenario/scenario_data/scenic_data/scenario_1/scenario_1.json.bak \
   safebench/scenario/scenario_data/scenic_data/scenario_1/scenario_1.json
```

## Conventions to Preserve

- `agent_config['load_dir']` is `load_dir + "/scenario_<id>"` per
  `scripts/run_train.py:71` — do not change this convention.
- `configs/eval_scenic.yaml: select_num: 2` — eval keeps 2 scenes per route.
- `scripts/run_paper_repro.sh:33-38` SCENARIOS / `68-69` EVAL_TEST_EPOCH /
  `413-439` loops — keep in sync when editing.
- No bare `except:` — use `except (OSError, IOError):` or specific types.
- Never commit `*.pkl` artifacts.

## Focused vs Full

- Focused default in script: `SCENARIOS="1 3 5"` (restorable via the
  commented full line at `run_paper_repro.sh:33`).
- Full Table-1: `SCENARIOS="1 2 3 4 5 6 7 8"` with `EVAL_ROUTES="8 9"` (paper
  test split, routes 8 and 9).

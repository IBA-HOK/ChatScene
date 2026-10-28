# Baseline vs DSF comparison bundle

Final snapshot of the epoch-0 baseline and the DSF pilot for scenarios 1/3/5,
routes 8-9.  The DSF pilot completed capture and eval for all three scenarios.

## L1/L2 audit
`avoidability/REPORT.md` contains the baseline collision audit.  L1 rejects
153/1040 collisions (mostly non-adversarial/static and timeout), and L2 flags
only 8 L1-pass collisions below 0.5 avoidability.  See the report for the
s1 behavior 4 route 8 fallback caveat.

## Headline result

DSF reduced CR and increased OS relative to the collision-based baseline, while
increasing ADE.  In the paper's metric directions (CR higher is better, OS
lower is better, ADE higher is better), DSF is worse on adversarial collision
performance and overall score, and better on scene diversity.  The likely cause
is `require_no_collision: true`: DSF selects collision-free high-DSF scenes,
whereas the baseline selects collision scenes.

See `COMPARISON.md` (or `comparison.csv`) for the full table and interpretation.

## Layout

```text
results/
  COMPARISON.md            # final baseline vs DSF table + findings
  comparison.csv           # machine-readable comparison table
  DSF_SNAPSHOT.txt         # snapshot metadata / counts
  avoidability/            # L1/L2 audit of baseline collisions (REPORT, CSV, JSON)
  directional_trial/        # directional-DSF selection, actual eval, inevitability
  avoidfirst_trial/         # avoidability-first selection trial (actual eval)
  pathdsf_trial/            # future-path DSF + hard-margin trial (actual eval)
  futuredsf_trial/          # future-frame directional path-DSF trial (actual eval)
  softfuture_trial/         # soft future-front top5 + eval-dispose trial
  dsf_avoidable_pilot/      # fine-tuning-layer dsf_avoidable pilot (s1 r8)
  dsf_avoidable_full/       # full s1/s3/s5 routes8-9 dsf_avoidable run
  directional_full/         # full directional DSF run (no I45 selection)
  baseline/
    maps/                  # scenic_data/scenario_{1,3,5}/ (JSON + Scenic files + .bak)
    capture/               # train_scenario/sac/adv_scenic/scenario_{1,3,5}/.../eval_results
    eval/                  # eval/sac/adv_scenic_epoch0/eval_scenic/scenario_{1,3,5}/.../eval_results
    configs/               # baseline scenario/agent YAMLs
    tables/                # routes 8-9 baseline tables (eval proxy + tail10)
  dsf/
    maps/                  # scenic_data_dsf/scenario_{1,3,5}/scenario_{id}.json (10 keys each)
    capture/               # train_scenario/sac/adv_scenic_dsf/scenario_{1,3,5}/.../eval_results
    eval/                  # eval/sac/adv_scenic_epoch0/eval_scenic_dsf/scenario_{1,3,5}/.../eval_results
    configs/               # DSF scenario/agent YAMLs
    tables/                # routes 8-9 DSF tables (eval proxy + tail10)
    pilot.log.snapshot     # /tmp/dsf_pilot.log snapshot
  tools/                   # compute_table1.py + dsf_select.py + avoidability_audit.py
  docs/                    # dsf_extension.md + epoch0_handoff.md
```

## Baseline routes 8-9 (eval proxy)

| scenario | n | CR | OS | ADE |
|---|---:|---:|---:|---:|
| 1 | 20 | 1.000 | 0.436 | 2.628 |
| 3 | 20 | 0.700 | 0.584 | 12.687 |
| 5 | 20 | 0.850 | 0.531 | 4.456 |
| avg | | 0.850 | 0.517 | |

## DSF routes 8-9 (eval proxy)

| scenario | n | CR | OS | ADE |
|---|---:|---:|---:|---:|
| 1 | 20 | 0.000 | 0.872 | 5.079 |
| 3 | 20 | 0.350 | 0.770 | 16.498 |
| 5 | 20 | 0.600 | 0.661 | 5.516 |
| avg | | 0.317 | 0.768 | |

## Re-aggregate

```bash
cd /home/hokuto/chatScene_Strata/ChatScene

PYTHONPATH="$PWD:$PWD/carla/PythonAPI/carla:$PWD/carla/PythonAPI:$(ls carla/PythonAPI/carla/dist/carla-*.egg | head -1)" \
python tools/compute_table1.py \
  --eval-root log/adv_train/eval/sac/adv_scenic_epoch0/eval_scenic_dsf \
  --ego sac-dsf --scenarios 1,3,5 --routes 8,9

PYTHONPATH="$PWD:$PWD/carla/PythonAPI/carla:$PWD/carla/PythonAPI:$(ls carla/PythonAPI/carla/dist/carla-*.egg | head -1)" \
python tools/compute_table1.py \
  --eval-root log/adv_train/eval/sac/adv_scenic_epoch0/eval_scenic_dsf \
  --ego sac-dsf --scenarios 1,3,5 --routes 8,9 \
  --ade-root log/adv_train/train_scenario/sac/adv_scenic_dsf --ade-tail 10
```

## Integrity notes

- DSF maps: scenario 1/3/5 = 10/10/10 keys.
- Every DSF map `selected` set matches its `pinned` keys.
- DSF capture records: 30; DSF eval records: 30.
- Baseline map mtimes are unchanged (2026-10-23).
- The pilot's final `run_paper_repro.sh` print/aggregate block hit a shell
  syntax error because the script was edited while it was running.  All
  capture/eval artifacts above were already written; the script is
  syntactically valid as of the final check.

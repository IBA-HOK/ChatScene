# Baseline vs full `dsf_avoidable` (valid pinned eval)

Comparison of the valid pinned runs only:
- baseline: collision-based selection, raw baseline
- `dsf_avoidable`: full s1/s3/s5 routes 8-9 fine-tuning-layer run
- current DSF: collision-free DSF pilot (reference only)

CR: higher is better in the paper's adversarial metric. For the
"dangerous but avoidable" objective, CR is expected to decrease.
OS: lower is better. ADE: higher is better.
I45: lower is better; `not_front` is counted unavoidable.

## CR / OS / ADE

| scenario | method | n | CR | OS | ADE |
|---|---|---:|---:|---:|---:|
| 1 | baseline | 20 | 1.000 | 0.436 | 2.628 |
| 1 | dsf_avoidable | 20 | 0.400 | 0.689 | 9.644 |
| 1 | current DSF | 20 | 0.000 | 0.872 | 5.079 |
| 3 | baseline | 20 | 0.700 | 0.584 | 12.687 |
| 3 | dsf_avoidable | 20 | 0.550 | 0.663 | 7.350 |
| 3 | current DSF | 20 | 0.350 | 0.770 | 16.498 |
| 5 | baseline | 20 | 0.850 | 0.531 | 4.456 |
| 5 | dsf_avoidable | 20 | 0.650 | 0.636 | 5.021 |
| 5 | current DSF | 20 | 0.600 | 0.661 | 5.516 |
| avg | baseline | | 0.850 | 0.517 | 6.590 |
| avg | dsf_avoidable | | 0.533 | 0.663 | 7.338 |
| avg | current DSF | | 0.317 | 0.768 | 9.031 |

## I45 / side+rear

| scenario | method | I45 | side+rear |
|---|---|---:|---:|
| 1 | baseline | 0.750 | 3 |
| 1 | dsf_avoidable | 0.625 | 1 |
| 1 | current DSF | n/a | 0 |
| 3 | baseline | 0.357 | 2 |
| 3 | dsf_avoidable | 0.000 | 1 |
| 3 | current DSF | 0.667 | 4 |
| 5 | baseline | 0.824 | 2 |
| 5 | dsf_avoidable | 0.615 | 2 |
| 5 | current DSF | 0.750 | 4 |
| overall | baseline | 0.651 | 7 |
| overall | dsf_avoidable | 0.464 | 4 |
| overall | current DSF | 0.722 | 8 |

## Deltas: dsf_avoidable - baseline

| scenario | ΔCR | ΔOS | ΔADE | ΔI45 | Δ(side+rear) |
|---|---:|---:|---:|---:|---:|
| 1 | -0.600 | +0.253 | +7.016 | -0.125 | -2 |
| 3 | -0.150 | +0.079 | -5.337 | -0.357 | -1 |
| 5 | -0.200 | +0.105 | +0.565 | -0.209 | 0 |
| avg | -0.317 | +0.146 | +0.748 | -0.187 | -3 |

## Reading

- I45: **improved** from 0.651 to 0.464.
- side+rear: **improved** from 7 to 4 (not a target now, diagnostic only).
- CR: decreased from 0.850 to 0.533. This is expected when selecting
  avoidable collisions rather than maximizing collisions.
- OS: worsened from 0.517 to 0.663. This is the main failure: the selected
  scenes are not forcing enough task/comfort degradation.
- ADE: improved overall, but s3 is worse.

Do not compare directional/avoidfirst/pathDSF/futureDSF/softfuture/BM-FP
numbers here; those evals lacked pinned parameters and are not valid.

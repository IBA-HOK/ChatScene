# Baseline vs DSF comparison (routes 8-9, epoch 0 SAC)

Generated: 2026-10-24
Baseline: `adv_scenic.yaml`, `eval_scenic.yaml`, collision-based selection
DSF: `adv_scenic_dsf.yaml`, `eval_scenic_dsf.yaml`, DSF + TTC/DRAC selection

Metric directions from the paper: **CR (collision rate) higher is better** for
adversarial scenario generation, **OS (overall score) lower is better**, and
**ADE higher is better** for scene diversity.

## Eval-population ADE

| scenario | Baseline CR | DSF CR | Baseline OS | DSF OS | Baseline ADE | DSF ADE |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 1.000 | 0.000 | 0.436 | 0.872 | 2.628 | 5.079 |
| 3 | 0.700 | 0.350 | 0.584 | 0.770 | 12.687 | 16.498 |
| 5 | 0.850 | 0.600 | 0.531 | 0.661 | 4.456 | 5.516 |
| avg | 0.850 | 0.317 | 0.517 | 0.768 | | |

## Tail-10 capture ADE

| scenario | Baseline CR | DSF CR | Baseline OS | DSF OS | Baseline ADE | DSF ADE |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 1.000 | 0.000 | 0.436 | 0.872 | 2.392 | 3.165 |
| 3 | 0.700 | 0.350 | 0.584 | 0.770 | 6.687 | 12.825 |
| 5 | 0.850 | 0.600 | 0.531 | 0.661 | 3.876 | 4.214 |
| avg | 0.850 | 0.317 | 0.517 | 0.768 | | |

## Findings

- The DSF selector reduces the collision rate (CR) relative to the
  collision-based baseline in all three scenarios.  Since higher CR is better
  for the paper's adversarial-generation objective, this is **worse
  adversarial performance**, not an improvement.
- The overall score (OS) is higher for DSF in all three scenarios.  Since lower
  OS is better, this is also **worse** on the aggregate ego-performance metric.
- ADE is higher for DSF in all three scenarios, which is **better** for scene
  diversity.
- The main cause is explicit: `require_no_collision: true` in the DSF config
  removes collision scenes from the feasible set.  The selector therefore
  favors high-DSF but collision-free scenes, while ChatScene's original
  objective favors collision scenes.  DSF is not reproducing the paper's
  collision-maximizing selection, even though it increases trajectory
  diversity.
- Scenario 1 is the extreme case: baseline CR 1.000 vs DSF CR 0.000.
- Fallback groups: scenario 3 behavior 2 / route 8 had `feasible=0` and used
  both `fallback_non_collision` and `fallback_legacy`; scenario 5 behavior 3 /
  route 9 used `fallback_non_collision` with one feasible scene.  These groups
  are not evidence of a clean DSF selection.

## Counts / integrity

- DSF maps: scenario 1/3/5 = 10/10/10 behavior-route keys.
- Every map entry has `selected` matching its `pinned` keys.
- DSF capture records: 30 (10 per scenario).
- DSF eval records: 30 (10 per scenario, routes 8 and 9).
- Baseline `scenic_data/scenario_{1,3,5}/scenario_{id}.json` mtimes are
  unchanged from 2026-10-23.

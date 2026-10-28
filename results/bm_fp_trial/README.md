# BM-FP-DSF one-pass trial (exploratory; eval contaminated by missing pinned)

Selection used capture only:
- L1 pass
- 5m+45° detection
- avoidable gate
- Band-Margin (`0 < margin <= 1.0 m`) first
- `future_front_ratio >= 0.35` first
- soft score `F_front - 0.5*(F_side + F_rear)`
- top5 candidate pool from the previous soft-future proposal
- 2nd scene selected with a pair-ADE diversity preference

Selection result: 30/30 groups have 2 scenes; 50/60 are capture-avoidable
collisions.

Evaluation used the already-generated `eval_scenic_softfuture` records.
Those records were produced from maps **without `pinned`**, so
`ScenicDataLoader` regenerated all 50 scenes and the selected `data_id` can
drift.  Therefore the eval numbers below are **not valid for judging BM-FP-DSF**.

Exploratory eval (do not cite as a method result):
- CR: 0.300 / 0.550 / 0.850; average 0.567
- OS: 0.731 / 0.665 / 0.532; average 0.643
- ADE: 6.675 / 10.691 / 4.153; average 7.173
- I45: 0.667 / 0.364 / 0.765; overall 0.613
- side+rear: 8

## Required fix before the next eval

Write `pinned` for every selected `data_id` and use `replay_scenes(pinned)`.
Without pinned, capture collisions become non-collisions/L1 rejects in eval,
and CR/OS/ADE/I45 are meaningless.

Recommended:
1. Calibrate BM-FP-DSF thresholds on routes 0-7.
2. On routes 8-9, select from capture only, extract pinned params for the
   selected IDs, write the map.
3. Run eval once; no eval-dispose on the test set.

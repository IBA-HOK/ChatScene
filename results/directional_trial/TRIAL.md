# Directional DSF trial (capture proxy)

Selection: L1 hard pass, collision, directional DSF front_ratio >= 0.60;
rank by L2 avoidability, OS, directional DSF.  Metrics are computed from
existing baseline capture records (same epoch-0 ego), not a new eval.

| scenario | baseline CR/OS/ADE | directional DSF CR/OS/ADE | current DSF CR/OS/ADE |
|---|---|---|---|
| 1 | 1.000/0.424/2.633 | 0.900/0.459/4.061 | 0.000/0.921/5.040 |
| 3 | 1.000/0.440/5.703 | 1.000/0.440/6.145 | 0.100/0.896/8.169 |
| 5 | 1.000/0.453/2.993 | 1.000/0.453/2.993 | 0.000/0.976/3.578 |

## Selection reasons

- 1/1/r8: collision_front
- 1/1/r9: collision_front
- 1/2/r8: collision_front
- 1/2/r9: collision_front
- 1/3/r8: collision_front
- 1/3/r9: collision_front
- 1/4/r8: fallback_noncollision
- 1/4/r9: collision_front
- 1/5/r8: collision_front
- 1/5/r9: collision_front
- 3/1/r8: collision_front
- 3/1/r9: collision_front
- 3/2/r8: collision_front
- 3/2/r9: collision_front
- 3/3/r8: collision_front
- 3/3/r9: collision_front
- 3/4/r8: collision_front
- 3/4/r9: collision_front
- 3/5/r8: collision_front
- 3/5/r9: collision_front
- 5/1/r8: collision_front
- 5/1/r9: collision_front
- 5/2/r8: collision_front
- 5/2/r9: collision_front
- 5/3/r8: collision_front
- 5/3/r9: collision_front
- 5/4/r8: collision_front
- 5/4/r9: collision_front
- 5/5/r8: collision_front
- 5/5/r9: collision_front

## Collision inevitability (PDF p10 proxy)

`INEVITABILITY.md` / `inevitability.json`.

- Definition: reaction 0.3 s + max decel 8 m/s^2 + max steering
  (lateral accel 5 m/s^2 proxy), collision radius 2 m, recorded adversary
  trajectory.
- Overall L1-pass baseline collisions: 0 unavoidable / 887 known (0.000).
- Baseline selected: s1 0/20 (8 unknown L1-reject), s3 0/20 (1 unknown),
  s5 0/20.
- Directional DSF selected: s1 0/18, s3 0/20, s5 0/20.
- Current DSF capture selection: s1 n/a (0 collisions), s3 0/2,
  s5 n/a.
- Brake-only also gives 0.000 on the same known sets.

Caveat: this is a kinematic proxy.  The first-conflict detection is
TTC<=3 s / distance<=5 m; visibility/occlusion is not modelled.  The exact
PDF definition should eventually be checked with a CARLA counterfactual.

## Metric-source caveat

The CR/OS/ADE table above is a **capture proxy**, not the final eval.  In
particular, the current-DSF capture selection has CR 0/0.1/0 (s1/s3/s5),
while the actual eval of the DSF-selected maps was CR 0/0.35/0.60.  The
directional-DSF row has no eval yet.  Do not mix these numbers with the
paper Table 1.

## Actual eval (authoritative)

See `EVAL_COMPARISON.md`.  Epoch-0 SAC eval on routes 8-9:

- baseline: avg CR .850 / OS .517 / ADE 6.590
- directional DSF: avg CR .750 / OS .558 / ADE 8.168
- current DSF: avg CR .317 / OS .768 / ADE 9.031

Directional keeps CR far above current DSF but below baseline.  Actual eval
contact zones: baseline front 44 / side 7 / rear 0; directional front 38 /
side 7 / rear 0.  Side collisions were not reduced in eval.

Note: `obs_type=0` SAC observes only 4-D ego state.  `obs_range=32 m` is a BEV
rendering range, not SAC's actor detection range.  See `EVAL_COMPARISON.md`.

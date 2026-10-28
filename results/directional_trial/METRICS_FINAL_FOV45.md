# Final metrics: ±45° FOV + 5 m detection; not_front counted unavoidable

Official detection rule: first time the collision actor is within 5 m **and**
within ±45° of the ego heading (90° total front FOV). If this never happens
before collision, the scene is `not_front` and counted as unavoidable.

`I45 = (unavoidable + not_front) / known_collisions`.
`known_collisions` excludes L1 rejects (non-adversary/timeout/overlap/teleport).
CR higher better, OS lower better, ADE higher better. Metrics are actual eval.

| scenario | method | CR | OS | ADE | total col | L1 reject | known | not_front | avoidable | unavoidable | I45 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | baseline | 1.000 | 0.436 | 2.628 | 20 | 8 | 12 | 0 | 3 | 9 | 0.750 |
| 3 | baseline | 0.700 | 0.584 | 12.687 | 14 | 0 | 14 | 1 | 9 | 4 | 0.357 |
| 5 | baseline | 0.850 | 0.531 | 4.456 | 17 | 0 | 17 | 2 | 3 | 12 | 0.824 |
| 1 | directional_dsf | 0.750 | 0.531 | 3.538 | 15 | 5 | 10 | 0 | 1 | 9 | 0.900 |
| 3 | directional_dsf | 0.600 | 0.638 | 16.602 | 12 | 1 | 11 | 3 | 3 | 5 | 0.727 |
| 5 | directional_dsf | 0.900 | 0.505 | 4.364 | 18 | 0 | 18 | 0 | 4 | 14 | 0.778 |
| 1 | current_dsf | 0.000 | 0.872 | 5.079 | 0 | 0 | 0 | 0 | 0 | 0 | n/a |
| 3 | current_dsf | 0.350 | 0.770 | 16.498 | 7 | 1 | 6 | 3 | 2 | 1 | 0.667 |
| 5 | current_dsf | 0.600 | 0.661 | 5.516 | 12 | 0 | 12 | 3 | 3 | 6 | 0.750 |

## Overall
- baseline: total=51, L1reject=8, known=43, not_front=3, unavoidable=28, I45=0.651
- directional_dsf: total=45, L1reject=6, known=39, not_front=3, unavoidable=31, I45=0.795
- current_dsf: total=19, L1reject=1, known=18, not_front=6, unavoidable=13, I45=0.722

## Key points

- Directional DSF: I45=0.795, worse than baseline 0.651 and current 0.722.
- `not_front` is 3 baseline, 3 directional, 6 current. Counting it as unavoidable heavily penalizes current DSF (s3/s5).
- Side collisions in actual eval: baseline 7, directional 7, current 8. Side removal is still not achieved.
- CR/OS/ADE are unchanged by the detection definition: baseline .850/.517/6.590; directional .750/.558/8.168; current .317/.768/9.031.

## Caveat

The 45° half-angle is a front-camera assumption (90° total). `not_front` means
never geometrically inside 5 m + front cone; it does not model occlusion.
Max steering is a 5 m/s^2 lateral / 1 rad/s yaw proxy. This is a kinematic
proxy, not a CARLA counterfactual.

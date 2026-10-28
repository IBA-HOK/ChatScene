# Final metrics: baseline vs directional DSF vs current DSF (actual eval)

Routes 8-9, epoch-0 SAC. CR higher better, OS lower better, ADE higher better.
`I5` = collision inevitability with detection at 5 m proxy. `I32` = detection at 32 m
(SAC `obs_range`, which is BEV render range, not actual SAC actor sensing).
`unknown_l1` = L1-rejected non-adversarial collisions, excluded from I denominator.

| scenario | method | CR | OS | ADE | collisions | known | unknown | I5 | I32 | front | side | rear | side+rear/selected |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | baseline | 1.000 | 0.436 | 2.628 | 20 | 12 | 8 | 0.750 | 0.000 | 17 | 3 | 0 | 0.150 |
| 3 | baseline | 0.700 | 0.584 | 12.687 | 14 | 14 | 0 | 0.286 | 0.000 | 12 | 2 | 0 | 0.100 |
| 5 | baseline | 0.850 | 0.531 | 4.456 | 17 | 17 | 0 | 0.706 | 0.000 | 15 | 2 | 0 | 0.100 |
| 1 | directional_dsf | 0.750 | 0.531 | 3.538 | 15 | 10 | 5 | 0.900 | 0.000 | 13 | 2 | 0 | 0.100 |
| 3 | directional_dsf | 0.600 | 0.638 | 16.602 | 12 | 11 | 1 | 0.455 | 0.000 | 8 | 4 | 0 | 0.200 |
| 5 | directional_dsf | 0.900 | 0.505 | 4.364 | 18 | 18 | 0 | 0.778 | 0.000 | 17 | 1 | 0 | 0.050 |
| 1 | current_dsf | 0.000 | 0.872 | 5.079 | 0 | 0 | 0 | n/a | n/a | 0 | 0 | 0 | 0.000 |
| 3 | current_dsf | 0.350 | 0.770 | 16.498 | 7 | 6 | 1 | 0.167 | 0.000 | 3 | 4 | 0 | 0.200 |
| 5 | current_dsf | 0.600 | 0.661 | 5.516 | 12 | 12 | 0 | 0.500 | 0.000 | 8 | 4 | 0 | 0.200 |

## Overall (weighted by known collisions)
- baseline: collisions=51, known=43, unavoidable@5m=25, I5=0.581, side+rear/selected=0.117
- directional_dsf: collisions=45, known=39, unavoidable@5m=28, I5=0.718, side+rear/selected=0.117
- current_dsf: collisions=19, known=18, unavoidable@5m=7, I5=0.389, side+rear/selected=0.133

## Key findings

- Directional DSF keeps CR (.750) well above current DSF (.317), but below baseline (.850).
- OS is worse than baseline (.558 vs .517) and better than current DSF (.768).
- ADE is higher than baseline (8.168 vs 6.590) and lower than current DSF (9.031).
- At the 5 m proxy, directional DSF has the highest collision inevitability rate (.718 vs baseline .581, current .389).
- At the 32 m proxy all methods are 0.000; the detection definition dominates.
- Side collisions are not reduced in actual eval: baseline 7, directional 7, current 8.
- Directional s3 side count is worse: 4 vs baseline 2.

## Caveat

`I5`/`I32` use a kinematic proxy: reaction 0.3 s, max decel 8 m/s^2, max steering
5 m/s^2 lateral / 1 rad/s yaw cap, collision radius 2 m, recorded adversary trajectory.
It is not a CARLA counterfactual. The PDF definition still needs a detection start and
a max-steering model.

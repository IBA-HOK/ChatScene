# Directional DSF actual eval comparison (routes 8-9)

Date: 2026-10-24
Ego: epoch-0 SAC pretrain (`adv_scenic.yaml`)
Metric directions: CR higher better, OS lower better, ADE higher better.

Directional selection:
- L1 hard pass
- collision
- directional DSF `front_ratio >= 0.60`
- rank by L2 avoidability, OS, directional DSF
- s1 b4 r8 has no valid collision candidate and uses a non-collision fallback

The directional map has no `pinned`; eval regenerates the 50 scenes from the
stored `opt_time` ranges and selects the chosen data ids.  The eval record ids
match the map `select_id` for all 30 behavior-route groups.

## CR / OS / ADE

| scenario | baseline CR/OS/ADE | directional CR/OS/ADE | current DSF CR/OS/ADE |
|---|---|---|---|
| 1 | 1.000 / 0.436 / 2.628 | 0.750 / 0.531 / 3.538 | 0.000 / 0.872 / 5.079 |
| 3 | 0.700 / 0.584 / 12.687 | 0.600 / 0.638 / 16.602 | 0.350 / 0.770 / 16.498 |
| 5 | 0.850 / 0.531 / 4.456 | 0.900 / 0.505 / 4.364 | 0.600 / 0.661 / 5.516 |
| avg | 0.850 / 0.517 / 6.590 | 0.750 / 0.558 / 8.168 | 0.317 / 0.768 / 9.031 |

Directional DSF keeps CR much higher than the current collision-free DSF, but
is below baseline.  OS is worse than baseline and better than current DSF.  ADE
is higher than baseline/current on s1 and s3; s5 is slightly below baseline and
current.

## Actual eval collision contact zones

From the eval records (contact bearing, ±45° front):

- baseline: front 44, side 7, rear 0
- directional: front 38, side 7, rear 0
- current DSF: front 11, side 8, rear 0

The directional filter reduced front collisions but did **not** reduce the
number of side collisions (7 vs 7).  Capture-based `front_ratio` does not
guarantee the eval contact zone; this is a key negative result for the
side/rear-removal goal.  A post-eval front-zone filter or a more robust
selection/replay check is required if side/rear removal must be guaranteed.

## Collision inevitability (PDF p10 proxy)

SAC `obs_type=0` is a 4-D ego state; it does **not** perceive surrounding
actors.  `obs_range=32 m` is only the BEV/LiDAR rendering range and LiDAR is
disabled.  Therefore "SAC detection range" is not an actual SAC sensing range;
32 m is an external proxy.  See `INEVITABILITY_EVAL.md` / `inevitability_eval.json`.

- At 32 m: baseline/directional/current all 0.000
- At 5 m: baseline 0.750 / 0.286 / 0.706; directional 0.900 / 0.455 / 0.778;
  current n/a / 0.167 / 0.500 (s1/s3/s5)
- Unknown entries are L1-rejected non-adversarial collisions and are excluded
  from the rate denominator.

The detection definition dominates the result.  A 32 m start makes every
collision avoidable; a 5 m start produces a non-trivial rate.  The PDF's
reaction-time definition must specify the detection start independently of SAC.

## Files

- `eval_comparison.csv`
- `table1_eval_proxy.txt`
- `INEVITABILITY_EVAL.md`
- `inevitability_eval.json`
- `eval/` (eval records)
- `maps/` (directional scene map)
- `configs/eval_scenic_directional.yaml`

## Official FOV45/5m inevitability

`METRICS_FINAL_FOV45.md` uses the adopted definition: first entry into 5 m and
±45° front FOV; `not_front` counted as unavoidable;

- baseline I45 = 0.651 (28/43 known)
- directional I45 = 0.795 (31/39)
- current DSF I45 = 0.722 (13/18)

Directional is worse than baseline.  Side collisions remain 7/7/8.

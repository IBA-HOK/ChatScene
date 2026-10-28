# Full `dsf_avoidable` fine-tuning experiment (s1/s3/s5 routes 8-9)

No LLM generation stage. Capture uses Scenic `train_scenario`; parameter ranges
are updated every 10 steps by `dsf_avoidable`; eval uses pinned scenes.

## Capture
- 1500 scenes (3 scenarios × 2 routes × 5 behaviors × 50)
- maps: all 3 scenarios have 10/10 keys; selected/pinned match
- selected status:
  - s1: 8 avoidable / 12 non-collision
  - s3: 20 avoidable
  - s5: 18 avoidable / 2 non-collision
- param update sources:
  - avoidable 8
  - band_avoidable 78
  - front_avoidable 11
  - collision_near_miss 35
  - empty 19

## Actual eval (pinned)
- n=20 per scenario
- CR: s1 0.400 / s3 0.550 / s5 0.650; avg 0.533
- OS: 0.689 / 0.663 / 0.636; avg 0.663
- ADE: 9.644 / 7.350 / 5.021; avg 7.338
- I45 (5m+45, not_front unavoidable):
  - s1 0.625 (5/8)
  - s3 0.000 (0/7)
  - s5 0.615 (8/13)
  - overall 0.464 (13/28)
- side+rear: 4 (s1 rear1, s3 rear1, s5 side2)

## Outcome
- Valid full run with pinned eval.
- I45 is below baseline .651 and well below directional .795.
- CR is lower than baseline .850 (expected for safer/avoidable selection), but
  OS is worse (.663 vs .517) and ADE is higher (7.338 vs 6.590).
- Selected collisions are still sparse: 32/60 selected scenes collide.
- This is not yet a clean success: the method lowers I45 but sacrifices OS.

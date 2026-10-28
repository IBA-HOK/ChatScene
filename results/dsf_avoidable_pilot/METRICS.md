# `dsf_avoidable` wider-exploration pilot (s1 route8)

Changes vs previous pilot:
- `explore_margin_min = -2.0` (near-miss collision exploration)
- `opt_record` cleared after every 10-step update
- non-collision never used for parameter updates
- final selection still strict 5m+45 avoidable

## Capture
- 250 scenes
- param updates: 3 `avoidable`, 12 `collision_near_miss`, 10 `empty`
- final selected: 3 avoidable / 10 scenes
  - b1: non-collision fallback
  - b2: 1 avoidable + 1 non-collision
  - b3: 1 avoidable + 1 non-collision
  - b4: non-collision fallback (11 L1 rejects)
  - b5: 1 avoidable + 1 non-collision

## Actual eval (pinned)
- n = 10
- CR = 0.100
- OS = 0.824
- ADE = 10.262
- I45 = 0.000 (1/1 known collision is avoidable; side contact)
- front/side/rear = 0/1/0

## Outcome
- I45 improved to 0.
- CR remains 0.100; only 1 of 10 selected scenes collided in eval.
- 3 selected avoidable scenes did not reproduce collisions in eval; 2 selected
  scenes were non-collision fallback in groups with no avoidable candidate.
- The parameter-update layer still rarely finds avoidable collisions.

## Next
- Multi-seed or wider parameter exploration is required; single seed s1 r8 is
  too sparse.
- For any group with fewer than 2 avoidable collisions, report `insufficient`
  instead of silently filling with non-collision.
- Full s1/s3/s5 was not run.

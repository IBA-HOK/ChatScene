# Avoidability-first directional DSF trial (actual eval)

Selection: L1 hard pass → 5m + ±45° FOV → avoidable → directional DSF
front_ratio ≥ 0.60 → contact/approach front → OS ascending, front DSF
descending.  If fewer than two avoidable-front collisions were available,
non-collision high-front-DSF scenes filled the gap.

## CR / OS / ADE (actual eval)

| scenario | n | CR | OS | ADE |
|---|---:|---:|---:|---:|
| 1 | 20 | 0.300 | 0.736 | 8.148 |
| 3 | 20 | 0.500 | 0.688 | 10.872 |
| 5 | 19 | 0.895 | 0.509 | 5.273 |
| avg | | 0.565 | 0.644 | 8.098 |

## I45 (not_front counted unavoidable)

`I45 = (unavoidable + not_front) / known collisions`; L1 rejects excluded.

- s1: I45 = 1.000 (2/2 known), not_front 0, L1 reject 4
- s3: I45 = 0.556 (5/9), not_front 2, L1 reject 1
- s5: I45 = 0.588 (10/17), not_front 0, L1 reject 0
- overall: I45 = 0.607 (17/28)

## Side/rear in actual eval

- s1: front 1, side 1, rear 0
- s3: front 5, side 1, rear 1
- s5: front 15, side 2, rear 0
- total: front 21, side 4, rear 1 (side+rear = 5)

## Outcome

- I45 improved versus directional (0.607 vs 0.795) and is below baseline
  (0.651).
- Side+rear decreased versus baseline/directional (5 vs 7/7).
- CR collapsed: 0.565 vs directional 0.750 and baseline 0.850.
- OS worsened: 0.644 vs directional 0.558 and baseline 0.517 (lower is better).
- Cause: 26/59 selected scenes became non-collisions in actual eval.  The
  capture-level "avoidable" filter selected collisions that the epoch-0 ego
  avoids on replay.  Avoidability-first alone selects too-easy scenes.

## Next direction

Keep avoidability as a hard gate, but rank candidates by **front DSF first**
and use **actual eval to verify collision occurrence**:

1. Propose top-N (N=4–6) avoidable-front candidates per group by front DSF.
2. Eval all candidates.
3. Keep only candidates that actually collide in eval and have I45 avoidable.
4. Refill from the next front-DSF candidates.
5. Do not fill with capture-avoidable but eval-non-collision scenes.

This is DSF-propose / avoidability-gate / eval-dispose, not avoidability-first
ranking.

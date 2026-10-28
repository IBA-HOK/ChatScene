# Future-path DSF + hard-avoidable margin trial (actual eval)

Selection:
- L1 hard pass
- 5 m + ±45° detection
- avoidable gate
- rank by positive avoidance margin ascending (hardest avoidable),
  then path-DSF descending, then OS ascending
- side/rear allowed
- if fewer than two avoidable collisions: non-collision high-path-DSF fallback

Path-DSF: max adversary field at recorded future ego positions over a 1 s
lookahead (0.1 s steps), using the future adversary position at the same step.

## CR / OS / ADE

| scenario | n | CR | OS | ADE |
|---|---:|---:|---:|---:|
| 1 | 20 | 0.550 | 0.622 | 7.052 |
| 3 | 20 | 0.600 | 0.636 | 15.891 |
| 5 | 20 | 0.850 | 0.530 | 4.821 |
| avg | | 0.667 | 0.596 | 9.255 |

## I45 (5m + ±45°, not_front unavoidable)

- s1: I45 0.667 (2/3 known; L1 reject 8)
- s3: I45 0.500 (6/12; not_front 4)
- s5: I45 0.765 (13/17)
- overall: I45 0.656 (21/32 known)

## Side/rear (actual eval)

- s1: front 9, side 2, rear 0
- s3: front 8, side 4, rear 0
- s5: front 17, side 0, rear 0
- total: front 34, side 6, rear 0

## Outcome vs other methods

| method | CR | OS | ADE | I45 | side+rear |
|---|---:|---:|---:|---:|---:|
| baseline | 0.850 | 0.517 | 6.590 | 0.651 | 7 |
| directional DSF | 0.750 | 0.558 | 8.168 | 0.795 | 7 |
| avoidability-first | 0.565 | 0.644 | 8.098 | 0.607 | 5 |
| path-DSF + hard margin | 0.667 | 0.596 | 9.255 | 0.656 | 6 |

Path-DSF improves CR over avoidability-first, improves I45/side over
directional, and gives the highest ADE.  It does **not** beat baseline on CR or
I45, and OS is worse than baseline/directional.

## Failure mode

- s1 has 8 L1 rejects in eval out of 11 collisions: selected capture collisions
  became non-adversarial/static collisions on replay.
- s3 has 4 not_front collisions.
- One-pass capture selection is still not stable; the candidate was chosen
  before eval and not verified after eval.
- 9/20 s1, 8/20 s3, 3/20 s5 selected scenes became non-collisions.

## Next

Use DSF-propose / eval-dispose:
1. Propose top-N (4–6) hard-avoidable path-DSF candidates per group.
2. Eval all candidates.
3. Keep only actual eval collisions that are L1-pass and avoidable.
4. Refill from the next path-DSF candidates.
5. Recompute CR/OS/ADE/I45; do not select before eval verification.

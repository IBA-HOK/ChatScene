# Future-frame directional path-DSF trial (actual eval)

Selection:
- L1 hard pass
- 5m + ±45° detection for I45
- avoidable gate (positive avoidance margin)
- future-frame front gate: future relative position and future approach direction
  both within ±45° of future ego heading
- rank by future-front path-DSF descending, margin ascending, OS ascending
- side/rear contact allowed; future side/rear approach excluded
- deficient groups filled with non-collision, then avoidable side/rear, then
  unavoidable (explicit fallback)

Path score: adversary DSF at recorded future ego position over a 1 s lookahead
(0.1 s steps), using future adversary state; only contributions whose future
position and approach bearings are both front are counted as F.

## CR / OS / ADE

| scenario | n | CR | OS | ADE |
|---|---:|---:|---:|---:|
| 1 | 20 | 0.350 | 0.707 | 7.764 |
| 3 | 20 | 0.600 | 0.636 | 10.473 |
| 5 | 20 | 0.750 | 0.583 | 4.134 |
| avg | | 0.567 | 0.642 | 7.457 |

## I45 (5m + ±45°, not_front unavoidable)

- s1: 0.667 (2/3 known; L1 reject 4)
- s3: 0.250 (3/12; not_front 2)
- s5: 0.733 (11/15; not_front 2)
- overall: 0.533 (16/30 known)

## Side/rear (actual eval)

- s1: front 7, side 0, rear 0
- s3: front 10, side 1, rear 1
- s5: front 12, side 3, rear 0
- total: front 29, side 4, rear 1 (side+rear 5)

## Comparison

| method | CR | OS | ADE | I45 | side+rear |
|---|---:|---:|---:|---:|---:|
| baseline | 0.850 | 0.517 | 6.590 | 0.651 | 7 |
| directional DSF | 0.750 | 0.558 | 8.168 | 0.795 | 7 |
| avoidability-first | 0.565 | 0.644 | 8.098 | 0.607 | 5 |
| path-DSF + hard margin | 0.667 | 0.596 | 9.255 | 0.656 | 6 |
| future-frame directional path-DSF | 0.567 | 0.642 | 7.457 | 0.533 | 5 |

Future-frame directional path-DSF gives the best I45 and side+rear, but CR is
low and OS is high.  It excluded too many hard collisions: only 34/60 selected
scenes actually collided in eval.

## Methodological caveat

Selection used avoidance margin and future-front path score; I45 is still
evaluated on the same selected set.  This is not a held-out estimate.  Use
routes 0-7 for threshold calibration and routes 8-9 for final evaluation, and
do not use I45 as a selection criterion.

## Next

- Keep future-front path-DSF as a candidate proposal, not a hard final filter.
- Propose top-N (4–6/group), eval, and keep actual eval collisions that are
  avoidable; refill from next candidates.
- If future-front hard gate is kept, CR drops because many scenes have no
  future-front candidate.  Relax it to a soft penalty or use a two-stage
  candidate pool.

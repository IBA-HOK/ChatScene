# Soft future-front top5 + eval-dispose trial

Proposal:
- L1 pass
- 5m+45° detection
- avoidable gate
- future-front path-DSF as a soft score:
  `soft = F_front - 0.5*(F_side + F_rear)`
- top5 avoidable candidates per group
- side/rear contact allowed

Dispose:
- eval all top5
- keep actual eval collisions that are L1-pass and avoidable
- rank by eval soft score, margin, OS
- fill with non-collision, then unavoidable (explicit fallback)

## CR / OS / ADE (actual eval, selected after dispose)

| scenario | n | CR | OS | ADE |
|---|---:|---:|---:|---:|
| 1 | 18 | 0.278 | 0.743 | 7.317 |
| 3 | 19 | 0.737 | 0.567 | 6.237 |
| 5 | 20 | 0.950 | 0.479 | 4.397 |
| avg | | 0.655 | 0.596 | 5.984 |

## I45 (5m + ±45°, not_front unavoidable)

- s1: 0.400 (2/5 known)
- s3: 0.000 (0/14)
- s5: 0.421 (8/19)
- overall: 0.263 (10/38 known)

## Side/rear

- s1: front 4, side 1, rear 0
- s3: front 8, side 6, rear 0
- s5: front 16, side 3, rear 0
- total: front 28, side 10, rear 0

## Comparison

| method | CR | OS | ADE | I45 | side+rear |
|---|---:|---:|---:|---:|---:|
| baseline | 0.850 | 0.517 | 6.590 | 0.651 | 7 |
| directional DSF | 0.750 | 0.558 | 8.168 | 0.795 | 7 |
| avoidability-first | 0.565 | 0.644 | 8.098 | 0.607 | 5 |
| path-DSF + hard margin | 0.667 | 0.596 | 9.255 | 0.656 | 6 |
| future-frame directional | 0.567 | 0.642 | 7.457 | 0.533 | 5 |
| soft future + eval-dispose | 0.655 | 0.596 | 5.984 | 0.263 | 10 |

## Outcome

- I45 is the lowest (0.263), but this is after eval-dispose on the same eval set.
  It is exploratory, not a held-out estimate.
- Side+rear worsened to 10 (baseline 7); allowing side/rear and fallback
  unavoidable scenes increased side collisions.
- CR 0.655 and OS 0.596 are worse than baseline/directional; ADE 5.984 is the
  lowest, i.e. less diverse.
- Top5 candidates were insufficient: several groups had no eval-avoidable
  candidate and needed non-collision/unavoidable fallback. One group selected
  zero scenes (n=18/19/20).

## Next

Larger candidate pool (8-12/group) or a second refill round is required.  Also
separate evaluation methodology: use routes 0-7 for calibration, routes 8-9
for final test, and do not use I45 to select on the test set.

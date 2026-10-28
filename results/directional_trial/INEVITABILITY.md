# Collision inevitability (PDF p10 proxy)

Definition: reaction 0.3 s + max decel 8 m/s^2 + max steering
(lateral accel 5 m/s^2 proxy), collision radius 2 m, recorded adversary
trajectory.  `inevitability = unavoidable / known collisions`.

## Context (baseline capture)

- all collisions: 1040 unavoidable 0 rate 0.000
- L1-pass collisions: 887 unavoidable 0 rate 0.000
- L1-pass brake-only: 887 unavoidable 0 rate 0.000

## Selected sets

| scenario | method | selected | collisions | unavoidable | unknown | inevitability | brake-only |
|---|---|---:|---:|---:|---:|---:|---:|
| 1 | baseline | 20 | 20 | 0 | 8 | 0.000 | 0.000 |
| 1 | directional_dsf | 20 | 18 | 0 | 0 | 0.000 | 0.000 |
| 1 | current_dsf | 20 | 0 | 0 | 0 | n/a | n/a |
| 3 | baseline | 20 | 20 | 0 | 1 | 0.000 | 0.000 |
| 3 | directional_dsf | 20 | 20 | 0 | 0 | 0.000 | 0.000 |
| 3 | current_dsf | 20 | 2 | 0 | 0 | 0.000 | 0.000 |
| 5 | baseline | 20 | 20 | 0 | 0 | 0.000 | 0.000 |
| 5 | directional_dsf | 20 | 20 | 0 | 0 | 0.000 | 0.000 |
| 5 | current_dsf | 20 | 0 | 0 | 0 | n/a | n/a |

# Collision inevitability on actual eval records

SAC observation range = 32 m.  Definition: reaction 0.3 s + max decel
8 m/s^2 + max steering (5 m/s^2 lateral proxy); collision radius 2 m.
5 m row is a sensitivity check.

| scenario | method | collisions | inevitability@32m | inevitability@5m | unknown@32m |
|---|---|---:|---:|---:|---:|
| 1 | baseline | 20 | 0.000 | 0.750 | 8 |
| 1 | directional_dsf | 15 | 0.000 | 0.900 | 5 |
| 1 | current_dsf | 0 | n/a | n/a | 0 |
| 3 | baseline | 14 | 0.000 | 0.286 | 0 |
| 3 | directional_dsf | 12 | 0.000 | 0.455 | 1 |
| 3 | current_dsf | 7 | 0.000 | 0.167 | 1 |
| 5 | baseline | 17 | 0.000 | 0.706 | 0 |
| 5 | directional_dsf | 18 | 0.000 | 0.778 | 0 |
| 5 | current_dsf | 12 | 0.000 | 0.500 | 0 |

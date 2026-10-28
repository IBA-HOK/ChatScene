# Full directional DSF experiment (no I45 selection)

Selection uses current-frame directional DSF only:
- L1 hard pass
- collision allowed
- current-frame `front_ratio >= 0.60`
- rank by front DSF and OS
- no I45/margin/avoidability in selection

LLM generation stage unused.  Parameters follow baseline collision-based updates.

## Actual eval (pinned)
- n = 20 / 18 / 20 (s3 behavior2 route8 selected zero scenes)
- CR: .750 / .556 / .900; avg .735
- OS: .531 / .662 / .505; avg .566
- ADE: 3.538 / 18.315 / 4.364; avg 8.739
- I45: .900 / .778 / .778; overall **.811** (30/37 known)
- side+rear: **5**

## Comparison
| method | CR | OS | ADE | I45 | side+rear |
|---|---:|---:|---:|---:|---:|
| baseline | .850 | .517 | 6.590 | .651 | 7 |
| current DSF | .317 | .768 | 9.031 | .722 | 7 |
| full dsf_avoidable (I45 selection) | .533 | .663 | 7.338 | .464 | 4 |
| full directional (no I45) | .735 | .566 | 8.739 | .811 | 5 |

## Outcome
- Directional is the best non-I45 method on CR and OS among the DSF alternatives.
- It still has higher I45 (.811) than baseline (.651) and current DSF (.722).
- It does not beat baseline on CR/OS/ADE/I45.
- s3 behavior2 route8 has `select_id=[]` (no fallback), giving n=18; this is a selection bug to fix.
- This is a valid pinned full run, unlike earlier directional trials.

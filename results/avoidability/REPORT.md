# L1/L2 avoidability audit (baseline, routes 8-9)

Date: 2026-10-24
Input: baseline `adv_scenic` capture records, scenarios 1/3/5, routes 8/9
Tool: `tools/avoidability_audit.py`
Core: `safebench/util/avoidability.py` / `avoidability_types.py`

## Scope

- 30 behavior-route files, 50 scenes each: 1500 scenes.
- 1040 collisions, 460 non-collisions.
- L1 is a hard reject for degenerate/non-adversarial collisions.
- L2 is a soft avoidability score; it does not reject by itself.
- Occlusion is not used in L1 or L2. A late-visible actor remains a valid scene.
- Baseline is not filtered as a whole; this audit only labels candidate collisions
  for the DSF-side selector.

## L1 hard filters

Applied reasons:

- `collision_actor_not_near`: no adversary within 5 m at the first collision step.
  This is a proxy for collision with a static/world actor because the records do
  not carry the CARLA collision actor id.
- `collision_after_timeout`: collision at or after 15.0 s (the episode cap).
- `initial_overlap`: initial ego/adversary distance below 2 m.
- `actor_teleport`: adversary displacement inconsistent with its speed.
- `collision_before_min_sim`: collision before 0.5 s.
- `route_complete_after_collision`: route_complete >= 99.9 at collision.

Observed:

- L1 reject: **153 / 1040 collisions (14.7%)**
  - `collision_actor_not_near`: 146
  - `collision_after_timeout`: 7
  - `initial_overlap`: 0
  - `actor_teleport`: 0
- L1 pass: **887 / 1040 (85.3%)**

Per scenario:

- s1: 351 collisions, 211 L1 pass, 140 rejected as actor-not-near.
- s3: 279 collisions, 266 L1 pass, 6 actor-not-near + 7 timeout.
- s5: 410 collisions, 410 L1 pass, no L1 rejects.

## L2 soft score

At the first physical conflict (TTC <= 3 s or distance <= 5 m), compute:

- `warning_s = t_collision - t_first_conflict`
- `ttc_conflict`, `drac_conflict`
- `a_req_brake = v_ego^2 / (2 * d_conflict)`
- margins:
  - brake: `a_max / a_req` (a_max = 8 m/s²)
  - TTC: 0.5 s -> 0, 2.0 s -> 1
  - DRAC: 10 m/s² -> 0, 4 m/s² -> 1
  - warning: 0 s -> 0, 2 s -> 1
- `avoidability = min(margins)`

Observed for the 887 L1-pass collisions:

- mean 0.987, median 1.000, min 0.150
- below 0.5: **8 (0.9%)**
- below 0.25: **2 (0.2%)**

Low-avoidability collisions (all s3):

- s3 b5 r9 id0: A=0.15, warning=0.3 s
- s3 b3 r9 id6: A=0.20, warning=0.4 s
- s3 b5 r8 id32: A=0.25, warning=0.5 s
- s3 b4 r9 id46: A=0.30, warning=0.6 s
- s3 b5 r8 id1: A=0.30, warning=0.6 s
- s3 b3 r9 id16: A=0.35, warning=0.7 s
- s3 b5 r8 id12: A=0.40, warning=0.8 s
- s3 b4 r8 id27: A=0.45, warning=0.9 s

These are tight-warning collisions.  Because occlusion is intentionally kept,
they are **not hard rejects**; L2 should only down-rank them.

## Selection readiness

- 30 behavior-route groups.
- 29/30 groups have at least two L1-pass collisions, enough for `select_num=2`.
- The only insufficient group is **s1 behavior 4 route 8**:
  - 46 collisions, all 46 rejected as `collision_actor_not_near`.
  - This behavior uses a pedestrian hidden behind a parked car; the recorded
    collisions are with the parked car/static world, not the pedestrian.
  - Fallback for this group must use non-collision high-DSF scenes (or a
    documented baseline-collision fallback), not the rejected collisions.

## Selection impact projection

Using L1-pass collisions as the candidate pool and ranking by L2 avoidability:

- 29/30 groups have at least two candidates.
- Top-2 per group selects **no** collision with A < 0.5; the minimum selected
  A is 0.85.
- Expected selected collision count is 58/60: s1 18/20 (s1 b4 r8 has no valid
  collision candidate and uses a non-collision fallback), s3 20/20, s5 20/20.
- If capture collisions reproduce under the same ego in eval, the projected
  selected CR is about 0.967 average (s1 0.90, s3 1.00, s5 1.00), versus
  baseline 0.850 and current collision-free DSF 0.317.

This projection is not an eval result.  It assumes the selected collision
scenes reproduce under eval, which is plausible because capture and eval use
the same epoch-0 ego and deterministic pinned scenes, but it must be verified
with a short CARLA eval.

## Impact-zone analysis (side/rear removal)

The L1/L2 audit does not use impact direction.  This matters if the real goal is
to remove side/rear impacts rather than physical unavoidability.

Using the collision contact bearing in the ego frame (±45° front cone):

- all collisions: front 865, side 161, rear 14
- L1-pass collisions: front 712, side 161, rear 14
- approach-zone at first conflict: front 964, side 76, rear 0
- the 8 low-A collisions are all front contact / front approach

So the current L1/L2 policy does **not** remove side/rear collisions.  All 175
side/rear contact collisions pass L1, and none of them are the low-A cases.
A dedicated impact-zone filter is required.

Feasibility of a front-contact hard filter:

- front-contact L1-pass: 712 collisions
- 29/30 groups still have at least two candidates
- only s1 b4 r8 remains insufficient (46/46 non-adversarial collisions)

This is viable as `contact_zone in {front}`.  If the requirement is specifically
"the adversary approached from the side/rear", use the approach bearing instead;
it removes 76 L1-pass collisions.  If both matter, require both contact and
approach to be front (708 candidates).  The definition must be fixed before
implementing the selector.

## Directional DSF (front/side/rear)

The scalar DSF formula does not distinguish front from rear by itself: a rear
approach can have a high DSF because its velocity points toward the ego.  The
fix is to keep the DSF magnitude but assign each adversary contribution to an
ego-relative sector:

1. Compute the adversary bearing in the ego frame.
2. Compute the usual DSF pair contribution.
3. Take the maximum per sector over the first-conflict-to-collision window:
   `dsf_front`, `dsf_side`, `dsf_rear`.
4. `front_ratio = dsf_front / (dsf_front + dsf_side + dsf_rear)`.

Baseline routes 8-9, L1-pass collisions, using contact zone as the check:

- front contact: n=712, mean front_ratio 0.989, median 1.000, min 0.492
- side contact: n=161, mean 0.264, median 0.346, max 0.569
- rear contact: n=14, mean 0.141, median 0.198, max 0.405

Threshold sweep:

- `front_ratio >= 0.5`: keep 743, front keep 711/712, side/rear keep 32
- `front_ratio >= 0.55`: keep 709, front keep 705/712, side/rear keep 4
- `front_ratio >= 0.6`: keep 699, front keep 699/712, side/rear keep 0
- `front_ratio >= 0.7`: keep 694, front keep 694/712, side/rear keep 0

At 0.6, all 175 side/rear contacts are removed and 13 front contacts are lost;
29/30 groups still have at least two candidates (s1 b4 r8 remains the only
insufficient group).  This is a strong fit for the side/rear removal goal.

Recommended use: directional DSF is a **hard or strong soft gate** for impact
sector, while L2 avoidability remains a separate soft ranking.  A practical
combination is:

- hard: L1 invalid collisions
- hard/strong: `front_ratio >= 0.6` (or contact-zone front)
- rank: collision, L2 avoidability, OS, directional DSF
- fallback: non-collision high-DSF

## Recommended selector behavior

1. Apply L1 hard reject.
2. Prefer collision scenes that pass L1.
3. Within those, rank by L2 `avoidability` descending, then OS ascending,
   then DSF descending.
4. If a group has fewer than `select_num` L1-pass collisions, fill from
   non-collision high-DSF scenes.
5. Log `avoidability`, `l1_reasons`, `warning_s`, and the fallback reason.

Expected effect: CR should stay close to the collision-based baseline because
most collisions (887/1040) survive L1.  The 153 rejects remove static/world
and timeout artifacts; L2 only down-ranks 8 tight cases.  This avoids the
current DSF failure mode where `require_no_collision` removes all collisions.

## Caveats

- The records do not contain the CARLA collision actor id or actor type, so
  `collision_actor_not_near` is a proximity proxy.  A large vehicle collision
  could be misclassified; the current scenarios use pedestrians as the
  recorded adversary, so the 5 m proxy is acceptable for this audit.
- L2 uses recorded ego/adversary positions and velocities; it is not a
  counterfactual rollout.  A borderline case can be verified later with a
  brake/steer replay.
- The thresholds are a first calibration.  Adjust only after inspecting the
  low-A set and a small CARLA validation set.

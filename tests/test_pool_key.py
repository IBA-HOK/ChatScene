"""
Regression for scenic_scenario pool key bug (lines 44-56).
- line 47: pool[actor.id]=actor (ego) correct
- line 55: must be pool[adv_actor.id]=adv_actor, not pool[actor.id]=adv_actor
Direct dict simulation + source inspection. Fails RED before fix, passes GREEN after.
"""
import pathlib

FILE = pathlib.Path(__file__).resolve().parents[1] / "safebench" / "scenario" / "scenario_definition" / "scenic_scenario.py"

def _read_lines():
    text = FILE.read_text()
    return text.splitlines()

def _get_pool_lines():
    lines = _read_lines()
    # lines are 1-indexed for report; find pool assignments
    pools = []
    for i, ln in enumerate(lines, start=1):
        if "_carla_actor_pool" in ln and "=" in ln:
            pools.append((i, ln.strip()))
    return pools

def test_source_line55_uses_adv_actor_id():
    """Line 55 must be pool[adv_actor.id]=adv_actor, not pool[actor.id]=adv_actor"""
    lines = _read_lines()
    # line 55 per task (1-indexed)
    assert len(lines) >= 55, f"file too short {len(lines)}"
    line47 = lines[46]  # 0-index 46 = line47
    line55 = lines[54]  # 0-index 54 = line55
    # line47 must remain ego
    assert "CarlaDataProvider._carla_actor_pool[actor.id]" in line47 and "= actor" in line47, f"line47 corrupted: {line47!r}"
    # line55 must use adv_actor.id
    assert "CarlaDataProvider._carla_actor_pool[adv_actor.id]" in line55, f"line55 bug: expected adv_actor.id, got {line55!r}"
    assert "pool[actor.id] = adv_actor" not in line55 and "pool[actor.id]=adv_actor" not in line55.replace(" ", ""), f"line55 still uses actor.id: {line55!r}"
    # exactly the fix pattern
    assert "[adv_actor.id] = adv_actor" in line55 or "[adv_actor.id]=adv_actor" in line55.replace(" ", "")

def test_no_pool_actor_id_adv_actor_remaining():
    """Grep-like: no pool[actor.id]=adv_actor anywhere."""
    text = FILE.read_text()
    # normalized without spaces for robust check
    norm = text.replace(" ", "")
    assert "pool[actor.id]=adv_actor" not in norm, "bug pattern pool[actor.id]=adv_actor still present"

def _simulate_pool(use_fixed: bool):
    """Simulate pool dict insertion as file currently does."""
    # Determine key used by reading file: if fixed, advActorId, else actorId
    text = FILE.read_text()
    # detect bug presence
    is_fixed = "CarlaDataProvider._carla_actor_pool[adv_actor.id] = adv_actor" in text
    # For simulation we mimic actual file behavior, not param
    pool = {}
    class A:
        def __init__(self, i): self.id = i
    ego = A(101)
    adv1 = A(202)
    adv2 = A(203)
    # line 47
    actor = ego
    pool[actor.id] = actor
    # line 55 loop
    for adv_actor in [adv1, adv2]:
        if is_fixed:
            pool[adv_actor.id] = adv_actor
        else:
            pool[actor.id] = adv_actor  # bug: uses ego id
    return pool, ego, adv1, adv2, is_fixed

def test_pool_keys_both_present_two_advs():
    pool, ego, adv1, adv2, is_fixed = _simulate_pool(use_fixed=True)
    # assert adv key != ego key and both present
    assert ego.id in pool, f"ego {ego.id} missing from pool {list(pool.keys())}"
    assert adv1.id in pool, f"adv1 {adv1.id} missing, pool={list(pool.keys())} fixed={is_fixed}"
    assert adv2.id in pool, f"adv2 {adv2.id} missing, pool={list(pool.keys())} fixed={is_fixed}"
    assert adv1.id != ego.id and adv2.id != ego.id, "adv key equals ego key (overwrite)"
    assert pool[ego.id] is ego, f"ego overwritten: pool[101] is {pool[ego.id]}"
    assert pool[adv1.id] is adv1
    assert pool[adv2.id] is adv2
    assert len(pool) == 3, f"pool size {len(pool)} !=3 keys {pool.keys()} (corrupted if bug)"

def test_pool_single_adv_not_overwrite():
    pool, ego, adv1, adv2, is_fixed = _simulate_pool(use_fixed=True)
    # extra check single adv case
    pool2 = {}
    class A:
        def __init__(self, i): self.id = i
    ego2 = A(1)
    adv = A(2)
    actor = ego2
    pool2[actor.id] = actor
    text = FILE.read_text()
    is_fixed = "CarlaDataProvider._carla_actor_pool[adv_actor.id] = adv_actor" in text
    if is_fixed:
        pool2[adv.id] = adv
    else:
        pool2[actor.id] = adv
    assert 1 in pool2 and 2 in pool2, f"single adv case pool {pool2}"
    assert pool2[1] is ego2 and pool2[2] is adv

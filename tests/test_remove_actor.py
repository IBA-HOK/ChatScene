"""
Regression test for CarlaDataProvider.remove_actor_by_id hardening.

Given: actor in pool whose destroy() raises RuntimeError (wedged CARLA)
When: remove_actor_by_id is called
Then: exception does NOT propagate and pool entry is gone (no None residue)
"""
import importlib.util as _ilu
import sys
import types
from pathlib import Path

WORKDIR = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Stub carla so import of CarlaDataProvider succeeds without live CARLA
# ---------------------------------------------------------------------------
try:
    import carla  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    mock_carla = types.ModuleType("carla")

    class _Cmd:
        @staticmethod
        def DestroyActor(actor):
            return ("DestroyActor", actor)

    mock_carla.command = types.SimpleNamespace(DestroyActor=_Cmd.DestroyActor)
    mock_carla.Location = object
    mock_carla.Rotation = object
    mock_carla.Transform = object
    mock_carla.WeatherParameters = object
    sys.modules["carla"] = mock_carla

# Direct file import to avoid pulling safebench.scenario.__init__ (needs agents)
def _load_cdp():
    spec = _ilu.spec_from_file_location(
        "carla_data_provider_direct",
        str(WORKDIR / "safebench" / "scenario" / "scenario_manager" / "carla_data_provider.py"),
    )
    assert spec is not None and spec.loader is not None
    mod = _ilu.module_from_spec(spec)
    sys.modules["carla_data_provider_direct"] = mod
    spec.loader.exec_module(mod)  # type: ignore
    return mod.CarlaDataProvider

CarlaDataProvider = _load_cdp()


class MockActorRuntimeError:
    """Mock actor whose destroy() always raises RuntimeError."""
    def __init__(self, actor_id=42):
        self.id = actor_id

    def destroy(self):
        raise RuntimeError("wedged CARLA: destroy failed")

    def get_location(self):
        class _Loc:
            def distance(self, other):
                return 0.0
        return _Loc()

    @property
    def is_alive(self):
        return True


def test_remove_actor_by_id_runtimeerror_no_propagate_and_no_none_residue():
    # Given: pool contains actor 42 with wedged destroy
    CarlaDataProvider._carla_actor_pool = {}
    actor = MockActorRuntimeError(actor_id=42)
    CarlaDataProvider._carla_actor_pool[42] = actor

    # When: remove_actor_by_id is called (should NOT propagate)
    try:
        CarlaDataProvider.remove_actor_by_id(42)
    except RuntimeError as e:
        assert False, f"RuntimeError propagated instead of being handled: {e}"
    except AttributeError as e:
        assert False, f"AttributeError propagated: {e}"
    except KeyError as e:
        assert False, f"KeyError propagated: {e}"

    # Then: pool entry is gone, no None residue, no ghost key
    assert 42 not in CarlaDataProvider._carla_actor_pool, "pool still contains actor_id 42 after removal"
    for k, v in CarlaDataProvider._carla_actor_pool.items():
        assert v is not None, f"pool[{k}] is None residue"

    # Also ensure calling again does not raise
    CarlaDataProvider.remove_actor_by_id(42)  # non-existing should just print, not raise


def test_remove_actor_by_id_int_key_mismatch_ghost_cleanup():
    """Ensure even if actor.id differs from dict key, the keyed entry is still removed."""
    CarlaDataProvider._carla_actor_pool = {}
    actor = MockActorRuntimeError(actor_id=999)  # actor.id = 999 but key is 42
    CarlaDataProvider._carla_actor_pool[42] = actor

    CarlaDataProvider.remove_actor_by_id(42)

    assert 42 not in CarlaDataProvider._carla_actor_pool
    assert None not in CarlaDataProvider._carla_actor_pool.values()

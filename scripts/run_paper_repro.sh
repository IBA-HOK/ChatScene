#!/usr/bin/env bash
# ChatScene paper repro: train_scenario -> train_agent -> eval for scenario_1..8
# Usage:
#   bash scripts/run_paper_repro.sh [--scenarios "1 2 3"] [--test-epoch -1] [--skip-train-scenario] [--skip-train-agent] [--no-carla] [--restart-carla]
# Env: PORT TM_PORT DEVICE AGENT_CFG CARLA_ROOT EVAL_ROUTES EVAL_TEST_EPOCH STEP_TIMEOUT (or $ROOT_DIR/.env)
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
ulimit -c 0 2>/dev/null || true

# 0. optional .env (same file used for Strata settings; CARLA_ROOT etc. also read from here)
if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT_DIR/.env"
  set +a
fi

PORT="${PORT:-2002}"
TM_PORT="${TM_PORT:-8002}"
DEVICE="${DEVICE:-cpu}"
AGENT_CFG="${AGENT_CFG:-adv_scenic.yaml}"
TEST_POLICY="${TEST_POLICY:-sac}"
PRETRAIN_DIR="${PRETRAIN_DIR:-}"
# separate log trees per ego policy (run_eval.py shares paths per yaml+epoch)
EVAL_LOG_ROOT="${EVAL_LOG_ROOT:-log}"
TEST_EPOCH="${TEST_EPOCH:--1}"
EVAL_TEST_EPOCH="${EVAL_TEST_EPOCH:-}"
# Full set: 1 StraightObstacle, 2 TurningObstacle, 3 LaneChanging,
#   4 VehiclePassing, 5 RedLightRunning, 6 UnprotectedLeft, 7 RightTurn,
#   8 CrossingNegotiation. Restore by uncommenting the line below.
# SCENARIOS="${SCENARIOS:-1 2 3 4 5 6 7 8}"
# Focused experiment (restorable via the commented line above):
SCENARIOS="${SCENARIOS:-1 3 5}"
# run_eval.py ignores the yaml route list and uses only --route_id, so the
# paper test split (routes 8 and 9) must be enumerated here explicitly
EVAL_ROUTES="${EVAL_ROUTES:-8 9}"
CARLA_ROOT="${CARLA_ROOT:-$ROOT_DIR/carla}"
CARLA_START_TIMEOUT="${CARLA_START_TIMEOUT:-600}"
MANAGE_CARLA=1
FORCE_RESTART=0
SKIP_SCE=0
SKIP_AGT=0

while [ $# -gt 0 ]; do
  case "$1" in
    --scenarios=*) SCENARIOS="${1#*=}"; shift ;;
    --scenarios) SCENARIOS="${2:?value required for --scenarios}"; shift 2 ;;
    --test-epoch=*) TEST_EPOCH="${1#*=}"; shift ;;
    --test-epoch) TEST_EPOCH="${2:?value required for --test-epoch}"; shift 2 ;;
    --skip-train-scenario) SKIP_SCE=1; shift ;;
    --skip-train-agent) SKIP_AGT=1; shift ;;
    --no-carla) MANAGE_CARLA=0; shift ;;
    --restart-carla) FORCE_RESTART=1; shift ;;
    --help|-h) sed -n '2,5p' "$0"; exit 0 ;;
    *) # bare "1 2 3" also accepted
      if [[ "$1" =~ ^[0-9\ ]+$ ]]; then SCENARIOS="$1"; shift
      else echo "unknown arg: $1 (try --help)" >&2; exit 2; fi ;;
  esac
done

# eval checkpoint selector, passed as --test_epoch to run_eval.py.
# Resolved here (after CLI parsing) so --test-epoch is honored:
#   -1 loads adv_train/.../model.sac.-001.torch when present;
#   0 skips that load, keeping the SafeBench pretrained ego from
#   pretrain_dir (safe_rl/sac) — use 0 for a Table-1-style baseline.
EVAL_TEST_EPOCH="${EVAL_TEST_EPOCH:-$TEST_EPOCH}"

echo "== ChatScene paper repro =="
echo "scenarios: $SCENARIOS | port: $PORT/$TM_PORT | device: $DEVICE | test_epoch: $TEST_EPOCH"
echo "carla_root: $CARLA_ROOT (manage: $MANAGE_CARLA)"

# training needs the chatscene env (torch/pygame/gym); auto-select it when
# the invoking python lacks torch
if ! python -c "import torch" 2>/dev/null; then
  for cand in "$HOME/miniforge3/envs/chatscene/bin/python" /home/hokuto/miniforge3/envs/chatscene/bin/python; do
    if [ -x "$cand" ] && "$cand" -c "import torch" 2>/dev/null; then
      echo ">> using $cand (invoking python lacks torch)"
      export PATH="$(dirname "$cand"):$PATH"
      break
    fi
  done
fi
if ! python -c "import torch" 2>/dev/null; then
  echo "ERROR: torch not importable. Run: conda activate chatscene" >&2
  exit 1
fi
# put CARLA PythonAPI on the path when the agents module is missing
if ! python -c "from agents.navigation.basic_agent import BasicAgent" 2>/dev/null; then
  for sub in "PythonAPI/carla/agents" "PythonAPI/carla" "PythonAPI"; do
    [ -e "$CARLA_ROOT/$sub" ] && PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}${CARLA_ROOT}/$sub"
  done
  for egg in "$CARLA_ROOT"/PythonAPI/carla/dist/carla-*.egg; do
    [ -e "$egg" ] && PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$egg"
  done
  export PYTHONPATH
  echo ">> PYTHONPATH extended for CARLA API"
fi
# repo tree first: `python scripts/*.py` puts scripts/ first on sys.path, so
# the pip-installed old checkout (easy-install.pth) would otherwise shadow it
PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH
# self-check: abort instead of silently running another checkout's code
SAFEBENCH_SRC="$(python -c "import safebench.scenario.scenario_data_loader as m; print(m.__file__)" 2>/dev/null || true)"
case "$SAFEBENCH_SRC" in
  "$ROOT_DIR"/*) echo ">> safebench from this tree" ;;
  *)
    echo "ERROR: safebench resolves to '$SAFEBENCH_SRC', expected under $ROOT_DIR." >&2
    exit 1
    ;;
esac

# single-instance lock: two managers would kill each other's CARLA
LOCKFILE="$ROOT_DIR/.run_paper_repro.lock"
exec 9>"$LOCKFILE"
if ! flock -n 9; then
  echo "ERROR: another run_paper_repro.sh is already running. Run only one instance." >&2
  exit 1
fi

CARLA_SH="$CARLA_ROOT/CarlaUE4.sh"
CARLA_LOG="$ROOT_DIR/carla_${PORT}.log"
CARLA_PIDFILE="$ROOT_DIR/.carla_${PORT}.pid"

carla_healthy() {
  # A listening port is not enough: the server must actually serve (map
  # loaded). A too-early launch makes workers abort on the first call with
  # an uncatchable C++ TimeoutException, so require a full roundtrip here.
  if python -c "import carla; c=carla.Client('localhost',$PORT); c.set_timeout(3.0); c.get_server_version(); c.get_world().get_map().name" 2>/dev/null; then
    return 0
  fi
  # last resort when this python has no carla module at all
  python -c "import carla" 2>/dev/null && return 1
  (echo > "/dev/tcp/localhost/$PORT") 2>/dev/null
}

carla_stop() {
  if [ -f "$CARLA_PIDFILE" ]; then
    local pid
    pid="$(cat "$CARLA_PIDFILE")"
    # only signal if the PID is still our CARLA (PID reuse guard)
    if [ -n "$pid" ] && grep -qa "CarlaUE4" "/proc/$pid/cmdline" 2>/dev/null; then
      if kill -0 "$pid" 2>/dev/null; then kill "$pid" 2>/dev/null || true; sleep 5; kill -9 "$pid" 2>/dev/null || true; fi
    fi
    rm -f "$CARLA_PIDFILE"
  fi
  local pids
  pids="$(pgrep -f "carla-port=$PORT" 2>/dev/null || true)"
  if [ -n "$pids" ]; then kill $pids 2>/dev/null || true; sleep 5; kill -9 $pids 2>/dev/null || true; fi
}

carla_start() {
  if [ ! -x "$CARLA_SH" ]; then
    echo "ERROR: CarlaUE4.sh not found at $CARLA_SH." >&2
    echo "  Set CARLA_ROOT env or add CARLA_ROOT=<path> to $ROOT_DIR/.env" >&2
    return 1
  fi
  echo ">> starting CARLA on port $PORT (log: $CARLA_LOG)"
  # 9>&-: do not pass the batch lock to the server process
  "$CARLA_SH" -prefernvidia -RenderOffScreen -carla-port="$PORT" 9>&- >>"$CARLA_LOG" 2>&1 &
  echo $! > "$CARLA_PIDFILE"
  local waited=0
  while [ "$waited" -lt "$CARLA_START_TIMEOUT" ]; do
    if carla_healthy; then echo ">> CARLA healthy on port $PORT (${waited}s)"; return 0; fi
    sleep 10; waited=$((waited + 10))
    if [ $((waited % 30)) -eq 0 ]; then echo ">> ... waiting for CARLA (${waited}s/${CARLA_START_TIMEOUT}s)"; fi
  done
  echo "ERROR: CARLA did not become healthy within ${CARLA_START_TIMEOUT}s (see $CARLA_LOG)" >&2
  carla_stop
  return 1
}

ensure_carla() {
  # forced restart applies only to the first call (fresh server for the
  # batch); later calls only revive an unhealthy server
  if [ "$FORCE_RESTART" -eq 1 ] && [ "${RESTART_DONE:-0}" -eq 0 ]; then
    echo ">> [${1:-}] forced CARLA restart"
    RESTART_DONE=1
    carla_stop || return 1
    carla_start || return 1
    return 0
  fi
  if carla_healthy; then return 0; fi
  echo ">> [${1:-}] CARLA unhealthy on port $PORT -> restarting"
  carla_stop || true
  carla_start || return 1
}

if [ "$MANAGE_CARLA" -eq 1 ]; then
  ensure_carla "startup" || exit 1
else
  if ! carla_healthy; then
    echo "ERROR: CARLA not reachable on port $PORT and --no-carla given." >&2
    echo "  cd <carla> && ./CarlaUE4.sh -prefernvidia -RenderOffScreen -carla-port=$PORT &" >&2
    exit 1
  fi
fi
# 0b. preflight: agents module (CARLA PythonAPI) importable?
if ! python -c "from agents.navigation.basic_agent import BasicAgent" 2>/dev/null; then
  echo "ERROR: 'agents' module not importable. Export CARLA PythonAPI first:" >&2
  echo '  export CARLA_ROOT=/home/hokuto/carla' >&2
  echo '  export PYTHONPATH=$PYTHONPATH:${CARLA_ROOT}/PythonAPI/carla/dist/carla-0.9.13-py3.8-linux-x86_64.egg:${CARLA_ROOT}/PythonAPI/carla/agents:${CARLA_ROOT}/PythonAPI/carla:${CARLA_ROOT}/PythonAPI' >&2
  exit 1
fi

FAILED=""
# per-step wall-clock cap (seconds, 0=disable): a wedged simulator call can
# block forever, so fence each step; resume logic makes a retry cheap
STEP_TIMEOUT="${STEP_TIMEOUT:-3600}"
run_step() { # $1=desc, $@=cmd
  local desc="$1"; shift
  local rc=0
  echo ">> $desc (timeout ${STEP_TIMEOUT}s): $*"
  if [ "${STEP_TIMEOUT}" -gt 0 ] 2>/dev/null; then
    # shellcheck disable=SC2068
    timeout -k 120 "$STEP_TIMEOUT" $@ 9>&- || rc=$?
  else
    # shellcheck disable=SC2068
    $@ 9>&- || rc=$?
  fi
  if [ $rc -eq 0 ]; then
    echo "OK: $desc"
  else
    echo "FAIL($rc): $desc (continuing)" >&2
    FAILED="$FAILED [$desc]"
  fi
}

for sid in $SCENARIOS; do
  if [ "$SKIP_SCE" -eq 0 ]; then
    [ "$MANAGE_CARLA" -eq 1 ] && ensure_carla "sid=$sid" || true
    run_step "train_scenario sid=$sid" \
      python scripts/run_train.py --agent_cfg="$AGENT_CFG" --scenario_cfg=train_scenario_scenic.yaml \
        --mode train_scenario --scenario_id "$sid" --port "$PORT" --tm_port "$TM_PORT" --device "$DEVICE"
  fi
done

for sid in $SCENARIOS; do
  if [ "$SKIP_AGT" -eq 0 ]; then
    [ "$MANAGE_CARLA" -eq 1 ] && ensure_carla "sid=$sid" || true
    run_step "train_agent sid=$sid" \
      python scripts/run_train.py --agent_cfg="$AGENT_CFG" --scenario_cfg=train_agent_scenic.yaml \
        --mode train_agent --scenario_id "$sid" --port "$PORT" --tm_port "$TM_PORT" --device "$DEVICE"
  fi
done

for sid in $SCENARIOS; do
  for rid in $EVAL_ROUTES; do
    [ "$MANAGE_CARLA" -eq 1 ] && ensure_carla "sid=$sid" || true
    # --pretrain-dir takes a value: pass it only when set, or argparse
    # consumes the following flag as its value
    if [ -n "$PRETRAIN_DIR" ]; then
      run_step "eval sid=$sid route=$rid ($TEST_POLICY)" \
        python scripts/run_eval.py --agent_cfg="$AGENT_CFG" --scenario_cfg=eval_scenic.yaml \
          --mode eval --scenario_id "$sid" --route_id "$rid" --test_epoch "$EVAL_TEST_EPOCH" --test_policy "$TEST_POLICY" --pretrain_dir "$PRETRAIN_DIR" --output_dir "$EVAL_LOG_ROOT" --port "$PORT" --tm_port "$TM_PORT" --device "$DEVICE"
    else
      run_step "eval sid=$sid route=$rid ($TEST_POLICY)" \
        python scripts/run_eval.py --agent_cfg="$AGENT_CFG" --scenario_cfg=eval_scenic.yaml \
          --mode eval --scenario_id "$sid" --route_id "$rid" --test_epoch "$EVAL_TEST_EPOCH" --test_policy "$TEST_POLICY" --output_dir "$EVAL_LOG_ROOT" --port "$PORT" --tm_port "$TM_PORT" --device "$DEVICE"
    fi
  done
done

echo "== done =="
if [ -n "$FAILED" ]; then echo "FAILED:$FAILED" >&2; exit 1; fi
echo "All green. Artifacts:"
echo "  - scenario JSON: safebench/scenario/scenario_data/scenic_data/scenario_{id}/scenario_{id}.json"
echo "  - checkpoints:   safebench/agent/model_ckpt/adv_train/sac/scenic/scenario_{id}/"
echo "  - logs:          log/adv_train/{train_scenario,train_agent,eval}/sac/adv_scenic/scenario_{id}/"
echo "  - carla left running on port $PORT (stop: kill \$(cat $CARLA_PIDFILE))"

#!/usr/bin/env bash
# ChatScene paper repro: train_scenario -> train_agent -> eval for scenario_1..8
# Usage:
#   bash scripts/run_paper_repro.sh [--scenarios "1 2 3"] [--test-epoch -1] [--skip-train-scenario] [--skip-train-agent] [--no-carla] [--restart-carla] [--aggregate]
# Env: PORT TM_PORT DEVICE AGENT_CFG TRAIN_SCENARIO_CFG TRAIN_AGENT_CFG EVAL_SCENARIO_CFG SCENE_MAP_DIR RUN_TAG CARLA_ROOT EVAL_ROUTES EVAL_TEST_EPOCH STEP_TIMEOUT (or $ROOT_DIR/.env)
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
TRAIN_SCENARIO_CFG="${TRAIN_SCENARIO_CFG:-train_scenario_scenic.yaml}"
TRAIN_AGENT_CFG="${TRAIN_AGENT_CFG:-train_agent_scenic.yaml}"
EVAL_SCENARIO_CFG="${EVAL_SCENARIO_CFG:-eval_scenic.yaml}"
SCENE_MAP_DIR="${SCENE_MAP_DIR:-safebench/scenario/scenario_data/scenic_data}"
RUN_TAG="${RUN_TAG:-}"
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
    --aggregate) AGGREGATE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
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
# DRY_RUN validates the pipeline without a live simulator (no CARLA).
DRY_RUN="${DRY_RUN:-0}"
if [ "$DRY_RUN" -eq 1 ]; then
  MANAGE_CARLA=0
fi

echo "== ChatScene paper repro =="
echo "scenarios: $SCENARIOS | port: $PORT/$TM_PORT | device: $DEVICE | train_epoch: $TEST_EPOCH | eval_epoch: $EVAL_TEST_EPOCH"
echo "carla_root: $CARLA_ROOT (manage: $MANAGE_CARLA)"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "mode: DRY_RUN (no CARLA, pipeline validation only)"
fi

# --- pre-eval guard: sac-adv checkpoint presence (P6) ---
# When --skip-train-agent is set but EVAL_TEST_EPOCH=-1 requires the
# adv-trained SAC checkpoint, verify it exists per scenario. Mirrors
# agent_config load_dir convention in scripts/run_train.py:71:
#   agent_config['load_dir'] = osp.join(agent_config['load_dir'], f"scenario_{sid}")
# where load_dir defaults to safebench/agent/model_ckpt/adv_train/sac/scenic
# (adv_scenic.yaml). Also supports overriding via $PRETRAIN_DIR for the
# baseline (epoch 0) path and enumerates both -1 and 0 roots.
if [ "$SKIP_AGT" -eq 1 ] && [ "$EVAL_TEST_EPOCH" = "-1" ]; then
  _adv_load_base="safebench/agent/model_ckpt/adv_train/sac/scenic"
  # try to resolve actual load_dir from agent config if available
  if [ -f "$ROOT_DIR/safebench/agent/config/${AGENT_CFG}" ]; then
    _cfg_load_dir="$(python -c "
import yaml
try:
    c=yaml.safe_load(open('$ROOT_DIR/safebench/agent/config/${AGENT_CFG}'))
    print(c.get('load_dir', ''))
except Exception:
    print('')
" 2>/dev/null || true)"
    if [ -n "$_cfg_load_dir" ]; then
      _adv_load_base="$_cfg_load_dir"
    fi
  fi
  _missing_sids=""
  for _sid in $SCENARIOS; do
    _ckpt="$ROOT_DIR/$_adv_load_base/scenario_${_sid}/model.sac.-001.torch"
    if [ ! -f "$_ckpt" ]; then
      _missing_sids="$_missing_sids $_sid"
    fi
  done
  if [ -n "$_missing_sids" ]; then
    echo "WARNING: --skip-train-agent with EVAL_TEST_EPOCH=-1 but missing sac-adv checkpoint(s):$_missing_sids" >&2
    echo "  expected: $_adv_load_base/scenario_<id>/model.sac.-001.torch (load_dir convention scripts/run_train.py:71)" >&2
    if [ "$DRY_RUN" -eq 1 ]; then
      echo "WARNING: DRY_RUN: would fallback to epoch 0 (pretrain baseline) or clear --skip-train-agent; continuing validation." >&2
    else
      echo "WARNING: fallback to EVAL_TEST_EPOCH=0 (pretrain_dir: ${PRETRAIN_DIR:-safebench/agent/model_ckpt/safe_rl/sac/model_save/model.pt}); clearing --skip-train-agent so training will re-create checkpoints." >&2
      EVAL_TEST_EPOCH=0
      SKIP_AGT=0
      if [ -z "$PRETRAIN_DIR" ]; then
        PRETRAIN_DIR="safebench/agent/model_ckpt/safe_rl/sac/model_save/model.pt"
        # also resolve absolute pretrain roots for enumeration check
        if [ ! -f "$ROOT_DIR/$PRETRAIN_DIR" ] && [ ! -f "$PRETRAIN_DIR" ]; then
          echo "WARNING: pretrain_dir $PRETRAIN_DIR not found; eval will use agent yaml default." >&2
        fi
      fi
      echo "  -> EVAL_TEST_EPOCH=$EVAL_TEST_EPOCH SKIP_AGT=$SKIP_AGT PRETRAIN_DIR=$PRETRAIN_DIR" >&2
    fi
  else
    echo ">> pre-eval guard: sac-adv checkpoints present for scenarios:$SCENARIOS (epoch -1)"
  fi
  # enumerate both roots for operator visibility (env + --pretrain_dir)
  _pretrain_root="${PRETRAIN_DIR:-safebench/agent/model_ckpt/safe_rl/sac/model_save/model.pt}"
  echo ">> eval roots: sac-adv(epoch -1)=$_adv_load_base/scenario_<id>/model.sac.-001.torch sac-pretrain(epoch 0)=$_pretrain_root"
fi
# also enumerate roots when EVAL_TEST_EPOCH=0 for symmetry (no guard needed)
if [ "$EVAL_TEST_EPOCH" = "0" ]; then
  _pretrain_root="${PRETRAIN_DIR:-safebench/agent/model_ckpt/safe_rl/sac/model_save/model.pt}"
  echo ">> eval roots: sac-adv(epoch -1)=safebench/agent/model_ckpt/adv_train/sac/scenic/scenario_<id>/model.sac.-001.torch sac-pretrain(epoch 0)=$_pretrain_root (active: epoch 0)"
fi
# DRY_RUN early validation: enumerate SCENARIOS/EVAL_ROUTES and both epoch roots without CARLA
if [ "$DRY_RUN" -eq 1 ]; then
  echo ">> DRY_RUN: validating pipeline without CARLA (SCENARIOS=\"$SCENARIOS\" EVAL_ROUTES=\"$EVAL_ROUTES\" EVAL_TEST_EPOCH=$EVAL_TEST_EPOCH)"
  echo ">> DRY_RUN: would run phases:"
  echo ">> DRY_RUN:   train_scenario x$(echo "$SCENARIOS" | wc -w) (scenarios: $SCENARIOS)"
  if [ "$SKIP_AGT" -eq 1 ]; then
    echo ">> DRY_RUN:   train_agent SKIPPED (--skip-train-agent)"
  else
    echo ">> DRY_RUN:   train_agent x$(echo "$SCENARIOS" | wc -w) (scenarios: $SCENARIOS)"
  fi
  echo ">> DRY_RUN:   eval x$(echo "$SCENARIOS" | wc -w) scenarios x $(echo "$EVAL_ROUTES" | wc -w) routes = $(( $(echo "$SCENARIOS" | wc -w) * $(echo "$EVAL_ROUTES" | wc -w) )) runs (routes: $EVAL_ROUTES)"
  # validate checkpoint roots
  _adv_base="safebench/agent/model_ckpt/adv_train/sac/scenic"
  _pre_base="${PRETRAIN_DIR:-safebench/agent/model_ckpt/safe_rl/sac/model_save/model.pt}"
  for _sid in $SCENARIOS; do
    if [ "$EVAL_TEST_EPOCH" = "-1" ]; then
      _ckpt="$ROOT_DIR/$_adv_base/scenario_${_sid}/model.sac.-001.torch"
      if [ -f "$_ckpt" ]; then
        echo ">> DRY_RUN: OK sac-adv checkpoint scenario_$_sid: $_ckpt"
      else
        echo ">> DRY_RUN: MISSING sac-adv checkpoint scenario_$_sid: $_ckpt (would trigger fallback)" >&2
      fi
    fi
  done
  if [ -f "$ROOT_DIR/$_pre_base" ] || [ -f "$_pre_base" ]; then
    echo ">> DRY_RUN: OK pretrain checkpoint: $_pre_base"
  else
    echo ">> DRY_RUN: pretrain checkpoint not found at $_pre_base (yaml default will be used)" >&2
  fi
  for _sid in $SCENARIOS; do
    for _rid in $EVAL_ROUTES; do
      if [ -n "$PRETRAIN_DIR" ]; then
        echo ">> DRY_RUN: eval sid=$_sid route=$_rid epoch=$EVAL_TEST_EPOCH pretrain_dir=$PRETRAIN_DIR"
      else
        echo ">> DRY_RUN: eval sid=$_sid route=$_rid epoch=$EVAL_TEST_EPOCH"
      fi
    done
  done
  # validate pinned JSONs
  for _sid in $SCENARIOS; do
    _jfile="$ROOT_DIR/$SCENE_MAP_DIR/scenario_${_sid}/scenario_${_sid}.json"
    if [ -f "$_jfile" ]; then
      echo ">> DRY_RUN: OK pinned JSON scenario_$_sid: $_jfile"
    else
      echo ">> DRY_RUN: MISSING pinned JSON scenario_$_sid: $_jfile (will be created by train_scenario)" >&2
    fi
  done
  # validate agent_config load_dir convention (scripts/run_train.py:71)
  echo ">> DRY_RUN: load_dir convention: agent_config['load_dir'] + '/scenario_<id>' (scripts/run_train.py:71)"
  echo ">> DRY_RUN: CARLA management: MANAGE_CARLA=$MANAGE_CARLA (--no-carla respected)"
  echo ">> DRY_RUN: pinned backup: cp <json> <json>.bak before overwrite"
  echo ">> DRY_RUN: pipeline validation complete (no CARLA invoked)."
fi

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

cleanup_stale_workers() {
  # Only processes tied to OUR ports are touched; our own shell is excluded.
  local stale=" " p cmd
  for p in $(pgrep -f "run_train.py" 2>/dev/null || true); do
    [ "$p" = "$$" ] && continue
    cmd="$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null || true)"
    case "$cmd" in
      *"--port $PORT"*|*"--tm_port $TM_PORT"*) stale="$stale$p " ;;
    esac
  done
  for p in $(ss -tlnp 2>/dev/null | grep -E ":$TM_PORT([^0-9]|$)" | grep -oP 'pid=\K[0-9]+' | sort -u || true); do
    [ "$p" = "$$" ] && continue
    case "$stale" in *" $p "*) ;; *) stale="$stale$p " ;; esac
  done
  if [ "$stale" != " " ]; then
    echo ">> preflight: killing stale port holders:$stale"
    # shellcheck disable=SC2086
    kill -9 $stale 2>/dev/null || true
    sleep 2
    echo ">> preflight: ports $PORT/$TM_PORT should now be free"
  else
    echo ">> preflight: no stale port holders"
  fi
}

# single-instance lock: two managers would kill each other's CARLA
LOCKFILE="$ROOT_DIR/.run_paper_repro.lock"
exec 9>"$LOCKFILE"
if ! flock -n 9; then
  echo "ERROR: another run_paper_repro.sh is already running. Run only one instance." >&2
  exit 1
fi

# preflight: a dead batch (Ctrl-C/OOM) can leave train workers holding
# --port/--tm_port, and every new worker then dies with a traffic-manager
# bind error. We hold the lock here, so any such holder is stale.
cleanup_stale_workers

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

tm_warmup() {
  # First get_trafficmanager on a fresh server can wedge the first worker;
  # pay that cost here (bounded) instead. Failure only warns: in-worker
  # fences still guard every step.
  timeout 120 python -c "
import carla
c = carla.Client('localhost', $PORT)
c.set_timeout(10.0)
tm = c.get_trafficmanager($TM_PORT)
print('tm warmup ok')
" 2>/dev/null
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
    if carla_healthy; then echo ">> CARLA healthy on port $PORT (${waited}s)"; tm_warmup || echo ">> WARNING: TM warmup failed, continuing (workers are fenced)" >&2; return 0; fi
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

if [ "$DRY_RUN" -eq 1 ]; then
  echo ">> DRY_RUN: skipping CARLA startup/health checks (--no-carla semantics)"
elif [ "$MANAGE_CARLA" -eq 1 ]; then
  ensure_carla "startup" || exit 1
else
  if ! carla_healthy; then
    echo "ERROR: CARLA not reachable on port $PORT and --no-carla given." >&2
    echo "  cd <carla> && ./CarlaUE4.sh -prefernvidia -RenderOffScreen -carla-port=$PORT &" >&2
    exit 1
  fi
fi
# 0b. preflight: agents module (CARLA PythonAPI) importable?
if [ "$DRY_RUN" -eq 0 ] && ! python -c "from agents.navigation.basic_agent import BasicAgent" 2>/dev/null; then
  echo "ERROR: 'agents' module not importable. Export CARLA PythonAPI first:" >&2
  echo '  export CARLA_ROOT=/home/hokuto/carla' >&2
  echo '  export PYTHONPATH=$PYTHONPATH:${CARLA_ROOT}/PythonAPI/carla/dist/carla-0.9.13-py3.8-linux-x86_64.egg:${CARLA_ROOT}/PythonAPI/carla/agents:${CARLA_ROOT}/PythonAPI/carla:${CARLA_ROOT}/PythonAPI' >&2
  exit 1
fi

FAILED=""
# per-step wall-clock cap (seconds, 0=disable): a wedged simulator call can
# block forever, so fence each step; resume logic makes a retry cheap.
# Train steps run 50 episodes per config and need hours; eval steps are short.
STEP_TIMEOUT="${STEP_TIMEOUT:-3600}"
STEP_TIMEOUT_TRAIN="${STEP_TIMEOUT_TRAIN:-21600}"
# Watchdog for wedged train workers (env-overridable). A wall-clock timeout
# alone cannot catch a worker whose CPU is frozen and output is stalled
# (e.g. hang in post-route actor cleanup, past the 600s episode cap): that
# would burn the full STEP_TIMEOUT_TRAIN. The watchdog polls and declares the
# step stuck when BOTH worker CPU time and progress markers (scenario JSON +
# newest result pkl) are frozen for STUCK_WINDOW seconds. CPU is compared by
# delta, not equality: a wedged worker still accrues CPU from periodic RPC
# timeout bursts, so exact equality never holds. 300 jiffies/poll (5 CPU-s
# per 60s, ~8% of a core) is far below active training (60%+ of a core)
# yet far above hang bursts. kill -9 (workers
# ignore SIGTERM) frees the TM port automatically; a CARLA restart clears
# actor residue; the retry then resumes from pinned skip, so it is cheap.
# STUCK_WATCHDOG=0 restores the plain run_step behavior. STUCK_RETRIES=0
# (default) retries forever; a positive N caps retries at N. Each attempt is
# still fenced by STEP_TIMEOUT. Note: a deterministically wedged config will
# loop forever — stop the batch (Ctrl-C) if the same config hangs repeatedly.
STUCK_WATCHDOG="${STUCK_WATCHDOG:-1}"
STUCK_WINDOW="${STUCK_WINDOW:-720}"
STUCK_GRACE="${STUCK_GRACE:-1200}"
STUCK_RETRIES="${STUCK_RETRIES:-0}"
STUCK_POLL="${STUCK_POLL:-60}"
STUCK_CPU_JIFFIES="${STUCK_CPU_JIFFIES:-300}"

_step_cpu_jiffies() { # $1=pgrep pattern -> sum of utime+stime over matches
  local total=0 j p
  for p in $(pgrep -f "$1" 2>/dev/null || true); do
    j="$(awk '{print $14+$15}' "/proc/$p/stat" 2>/dev/null || true)"
    case "$j" in ''|*[!0-9]*) continue ;; esac
    total=$((total + j))
  done
  echo "$total"
}

_step_progress_mtime() { # $1=sid -> newest epoch over json + result pkls (0 if none)
  local sid="$1" best=0 m jfile eddir log_group="adv_scenic"
  [ -n "$RUN_TAG" ] && log_group="adv_scenic_${RUN_TAG}"
  jfile="$ROOT_DIR/$SCENE_MAP_DIR/scenario_${sid}/scenario_${sid}.json"
  if [ -f "$jfile" ]; then
    m="$(stat -c%Y "$jfile" 2>/dev/null || echo 0)"
    case "$m" in ''|*[!0-9]*) m=0 ;; esac
    [ "$m" -gt "$best" ] && best="$m"
  fi
  eddir="$ROOT_DIR/log/adv_train/train_scenario/sac/${log_group}/scenario_${sid}/exp/exp_rl_scenic_seed_0/eval_results"
  if [ -d "$eddir" ]; then
    m="$(find "$eddir" -type f -printf '%T@\n' 2>/dev/null | sort -rn | head -1 | cut -d. -f1 || true)"
    case "$m" in ''|*[!0-9]*) m=0 ;; esac
    [ "$m" -gt "$best" ] && best="$m"
  fi
  echo "$best"
}

run_step_watchdog() { # $1=desc, $2=sid, $@=cmd (train_scenario only)
  local desc="$1" sid="$2"; shift 2
  local attempt=0 rc=0 rc_prev=0 no_restart_streak=0 wdpid
  local pattern="run_train.py.*train_scenario.*scenario_id $sid"
  echo ">> $desc (timeout ${STEP_TIMEOUT}s, watchdog ${STUCK_WINDOW}s/grace ${STUCK_GRACE}s, retries ${STUCK_RETRIES:-unlimited}): $*"
  while [ "$STUCK_RETRIES" -eq 0 ] || [ "$attempt" -le "$STUCK_RETRIES" ]; do
    if [ "$attempt" -gt 0 ]; then
      local retry_of="$STUCK_RETRIES"; [ "$STUCK_RETRIES" -eq 0 ] && retry_of="unlimited"
      echo ">> retry $attempt/$retry_of for $desc (resume from pinned skip)"
      # exit 43 = setup-hang class: keep the warm server, no restart. After
      # two consecutive no-restart retries, restart anyway in case the
      # server itself is wedged.
      if [ "$rc_prev" -eq 43 ] && [ "$no_restart_streak" -lt 2 ]; then
        echo ">> [retry-$desc] keeping warm server (no CARLA restart)"
        no_restart_streak=$((no_restart_streak + 1))
      elif [ "$MANAGE_CARLA" -eq 1 ]; then
        echo ">> [retry-$desc] CARLA restart to clear actor residue"
        no_restart_streak=0
        carla_stop || true
        if ! carla_start; then
          echo "FAIL: $desc (CARLA restart failed, continuing)" >&2
          FAILED="$FAILED [$desc]"
          return 0
        fi
      fi
    fi
    local killed_by_watchdog=0 t0 now cpu prog frozen_since ncpu nprog
    t0="$(date +%s)"
    cpu="$(_step_cpu_jiffies "$pattern")"
    prog="$(_step_progress_mtime "$sid")"
    frozen_since=0
    # shellcheck disable=SC2068
    timeout -k 120 "$STEP_TIMEOUT" $@ 9>&- &
    wdpid=$!
    while kill -0 "$wdpid" 2>/dev/null; do
      sleep "$STUCK_POLL"
      kill -0 "$wdpid" 2>/dev/null || break
      now="$(date +%s)"
      ncpu="$(_step_cpu_jiffies "$pattern")"
      nprog="$(_step_progress_mtime "$sid")"
      if [ "$((now - t0))" -lt "$STUCK_GRACE" ] || [ "$((ncpu - cpu))" -gt "$STUCK_CPU_JIFFIES" ] || [ "$nprog" != "$prog" ]; then
        cpu="$ncpu"; prog="$nprog"; frozen_since=0; continue
      fi
      [ "$frozen_since" -eq 0 ] && frozen_since="$now"
      if [ "$((now - frozen_since))" -ge "$STUCK_WINDOW" ]; then
        echo ">> WATCHDOG: $desc stuck (cpu+progress frozen ${STUCK_WINDOW}s) -> kill -9 + retry" >&2
        # shellcheck disable=SC2207
        local victims=( $(pgrep -f "$pattern" 2>/dev/null || true) )
        if [ "${#victims[@]}" -gt 0 ]; then kill -9 "${victims[@]}" 2>/dev/null || true; fi
        killed_by_watchdog=1
        break
      fi
    done
    rc=0
    wait "$wdpid" || rc=$?
    if [ "$rc" -eq 0 ]; then
      echo "OK: $desc"
      return 0
    fi
    # retryable: watchdog kill, or worker fence-trip (42 = restart server,
    # 43 = keep warm server; worker already dead in both cases)
    if { [ "$killed_by_watchdog" -eq 1 ] || [ "$rc" -eq 42 ] || [ "$rc" -eq 43 ]; } && { [ "$STUCK_RETRIES" -eq 0 ] || [ "$attempt" -lt "$STUCK_RETRIES" ]; }; then
      rc_prev=$rc
      attempt=$((attempt + 1))
      continue
    fi
    echo "FAIL($rc): $desc (continuing)" >&2
    FAILED="$FAILED [$desc]"
    return 0
  done
}
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

_SAVED_STEP_TIMEOUT="$STEP_TIMEOUT"
STEP_TIMEOUT="$STEP_TIMEOUT_TRAIN"
if [ "$DRY_RUN" -eq 1 ]; then
  echo ">> DRY_RUN: skipping train_scenario / train_agent / eval loops (validation only)"
  STEP_TIMEOUT="$_SAVED_STEP_TIMEOUT"
else
for sid in $SCENARIOS; do
  if [ "$SKIP_SCE" -eq 0 ]; then
    # backup pinned JSON before overwrite (cp .bak) — do NOT overwrite valid pinned without backup
    _pinned_json="$ROOT_DIR/$SCENE_MAP_DIR/scenario_${sid}/scenario_${sid}.json"
    if [ -f "$_pinned_json" ]; then
      # only backup if .bak does not already exist or is older than the current file
      if [ ! -f "${_pinned_json}.bak" ]; then
        cp "$_pinned_json" "${_pinned_json}.bak" 2>/dev/null || true
        echo ">> backup pinned JSON: $_pinned_json -> ${_pinned_json}.bak"
      fi
    fi
    [ "$MANAGE_CARLA" -eq 1 ] && ensure_carla "sid=$sid" || true
    if [ "${STUCK_WATCHDOG:-1}" -eq 1 ]; then
      run_step_watchdog "train_scenario sid=$sid" "$sid" \
        python scripts/run_train.py --agent_cfg="$AGENT_CFG" --scenario_cfg="$TRAIN_SCENARIO_CFG" --run_tag "$RUN_TAG" \
          --mode train_scenario --scenario_id "$sid" --port "$PORT" --tm_port "$TM_PORT" --device "$DEVICE"
    else
      run_step "train_scenario sid=$sid" \
        python scripts/run_train.py --agent_cfg="$AGENT_CFG" --scenario_cfg="$TRAIN_SCENARIO_CFG" --run_tag "$RUN_TAG" \
          --mode train_scenario --scenario_id "$sid" --port "$PORT" --tm_port "$TM_PORT" --device "$DEVICE"
    fi
  fi
done

for sid in $SCENARIOS; do
  if [ "$SKIP_AGT" -eq 0 ]; then
    [ "$MANAGE_CARLA" -eq 1 ] && ensure_carla "sid=$sid" || true
    run_step "train_agent sid=$sid" \
      python scripts/run_train.py --agent_cfg="$AGENT_CFG" --scenario_cfg="$TRAIN_AGENT_CFG" --run_tag "$RUN_TAG" \
        --mode train_agent --scenario_id "$sid" --port "$PORT" --tm_port "$TM_PORT" --device "$DEVICE"
  fi
done
STEP_TIMEOUT="$_SAVED_STEP_TIMEOUT"

for sid in $SCENARIOS; do
  for rid in $EVAL_ROUTES; do
    [ "$MANAGE_CARLA" -eq 1 ] && ensure_carla "sid=$sid" || true
    # --pretrain-dir takes a value: pass it only when set, or argparse
    # consumes the following flag as its value
    if [ -n "$PRETRAIN_DIR" ]; then
      run_step "eval sid=$sid route=$rid ($TEST_POLICY)" \
        python scripts/run_eval.py --agent_cfg="$AGENT_CFG" --scenario_cfg="$EVAL_SCENARIO_CFG" \
          --mode eval --scenario_id "$sid" --route_id "$rid" --test_epoch "$EVAL_TEST_EPOCH" --test_policy "$TEST_POLICY" --pretrain_dir "$PRETRAIN_DIR" --output_dir "$EVAL_LOG_ROOT" --port "$PORT" --tm_port "$TM_PORT" --device "$DEVICE"
    else
      run_step "eval sid=$sid route=$rid ($TEST_POLICY)" \
        python scripts/run_eval.py --agent_cfg="$AGENT_CFG" --scenario_cfg="$EVAL_SCENARIO_CFG" \
          --mode eval --scenario_id "$sid" --route_id "$rid" --test_epoch "$EVAL_TEST_EPOCH" --test_policy "$TEST_POLICY" --output_dir "$EVAL_LOG_ROOT" --port "$PORT" --tm_port "$TM_PORT" --device "$DEVICE"
    fi
  done
done
fi

echo "== done =="
if [ "$DRY_RUN" -eq 1 ]; then
  echo ">> DRY_RUN: done (no artifacts written, no CARLA used)"
else
if [ "${AGGREGATE:-0}" -eq 1 ]; then
  echo "== aggregation =="
  SCENARIOS="$SCENARIOS" bash scripts/summarize_table1.sh || echo "aggregation failed (tables above may be partial)" >&2
fi
fi
if [ -n "$FAILED" ]; then echo "FAILED:$FAILED" >&2; exit 1; fi
if [ "$DRY_RUN" -eq 1 ]; then
  echo "DRY_RUN green. Validated pipeline without CARLA."
else
echo "All green. Artifacts:"
_final_log_group="adv_scenic"
[ -n "$RUN_TAG" ] && _final_log_group="adv_scenic_${RUN_TAG}"
_final_agent_base="${AGENT_CFG%.*}"
_final_eval_group="${_final_agent_base}_epoch${EVAL_TEST_EPOCH}"
_final_eval_scenario="${EVAL_SCENARIO_CFG%.*}"
echo "  - scenario JSON: $SCENE_MAP_DIR/scenario_{id}/scenario_{id}.json"
echo "  - checkpoints:   <load_dir from safebench/agent/config/$AGENT_CFG>/scenario_{id}/"
echo "  - train logs:    log/adv_train/{train_scenario,train_agent}/sac/${_final_log_group}/scenario_{id}/"
echo "  - eval logs:     log/adv_train/eval/sac/${_final_eval_group}/${_final_eval_scenario}/scenario_{id}/"
echo "  - carla left running on port $PORT (stop: kill \$(cat $CARLA_PIDFILE))"
fi

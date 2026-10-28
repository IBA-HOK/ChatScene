#!/usr/bin/env bash
# Summarize eval outputs into Table-1-style CR/OS/ADE tables.
# Part of the whole-experiment batch flow: run after eval completes.
# Usage:
#   bash scripts/summarize_table1.sh [--scenarios "1 3 5"] [--egos "sac-pretrain,sac-adv"]
# Env: EVAL_SAC_PRE=sac/adv_scenic_epoch0 EVAL_SAC_ADV=sac/adv_scenic_epoch-1
# Resolves roots as log/adv_train/eval/<policy>/<stem>/eval_scenic.
set -u
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
SCENARIOS="${SCENARIOS:-1 3 5}"
EGOS="${EGOS:-sac-pretrain,sac-adv}"
EVAL_SAC_PRE="${EVAL_SAC_PRE:-sac/adv_scenic_epoch0}"
EVAL_SAC_ADV="${EVAL_SAC_ADV:-sac/adv_scenic_epoch-1}"

if ! command -v python >/dev/null 2>&1; then
  echo "ERROR: python not found" >&2; exit 1
fi
if ! python -c "import torch, joblib" 2>/dev/null; then
  echo "ERROR: torch/joblib not importable (need chatscene env)" >&2; exit 1
fi
# safebench import chain needs the repo tree first plus CARLA PythonAPI
# (agents module); reuse CARLA_ROOT defaulting to ./carla with fallback
CARLA_ROOT="${CARLA_ROOT:-$ROOT_DIR/carla}"
PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
for sub in "PythonAPI/carla/agents" "PythonAPI/carla" "PythonAPI"; do
  [ -e "$CARLA_ROOT/$sub" ] && PYTHONPATH="$PYTHONPATH:${CARLA_ROOT}/$sub"
done
for egg in "$CARLA_ROOT"/PythonAPI/carla/dist/carla-*.egg /home/hokuto/carla/PythonAPI/carla/dist/carla-*.egg; do
  [ -e "$egg" ] && PYTHONPATH="$PYTHONPATH:$egg" && break
done
export PYTHONPATH

scen_csv="$(echo "$SCENARIOS" | tr ' ' ',')"
rc=0
OLD_IFS="$IFS"
IFS=','
for ego in $EGOS; do
  case "$ego" in
    sac-pretrain) stem="$EVAL_SAC_PRE" ;;
    sac-adv) stem="$EVAL_SAC_ADV" ;;
    *) echo "unknown ego label: $ego (use sac-pretrain|sac-adv)" >&2; rc=2; continue ;;
  esac
  root="log/adv_train/eval/$stem/eval_scenic"
  echo "===== ego=$ego root=$root scenarios=[$scen_csv] ====="
  echo "--- raw (min_drive=0) ---"
  python tools/compute_table1.py --eval-root "$root" --ego "$ego" \
    --scenarios "$scen_csv" --min-drive 0 || rc=$?
  echo "--- filtered (min_drive=2.0, dropped via ego_displacement) ---"
  python tools/compute_table1.py --eval-root "$root" --ego "$ego" \
    --scenarios "$scen_csv" --min-drive 2.0 || rc=$?
done
IFS="$OLD_IFS"
echo "summarize rc=$rc (outputs above; compare CR columns across egos)"
exit "$rc"

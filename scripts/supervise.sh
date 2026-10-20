#!/usr/bin/env bash
# Supervise a running paper-repro batch to completion without tokens:
# watches worker CPU + output freshness, SIGKILLs wedged workers so the
# batch advances (it records FAIL and continues), then runs aggregation.
# The batch itself must already be running (launched from your terminal).
# Usage:
#   bash scripts/supervise.sh <batch-log> [--stall-min 15] [--interval 600] [--dry-run]
# Never kills: the batch shell itself, CARLA server processes.
set -u
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
LOG="${1:?batch log required (e.g. repro_pinned2.log)}"
STALL_MIN=15
INTERVAL=600
DRY=0
shift || true
while [ $# -gt 0 ]; do
  case "$1" in
    --stall-min) STALL_MIN="${2:?}"; shift 2 ;;
    --interval) INTERVAL="${2:?}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    --help|-h) sed -n '2,7p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

worker_pids() { pgrep -f "python scripts/run_(train|eval).py" 2>/dev/null || true; }
worker_cpu() { ps -o time= -p "$1" 2>/dev/null | tr -d ' ' || echo "?"; }
newest_output() { local mins=$(( ($2 + 59) / 60 )); [ "$mins" -lt 1 ] && mins=1; find log safebench/scenario/scenario_data/scenic_data -type f -newermt "-$mins minutes" 2>/dev/null | head -n 1; }
batch_alive() { pgrep -f "[r]un_paper_repro.sh" >/dev/null 2>&1; }

echo "supervising $LOG (stall ${STALL_MIN}min, interval ${INTERVAL}s, dry=$DRY)"
last_cpu=""; last_out=""; still=0
while true; do
  sleep "$INTERVAL"
  ts="$(date '+%m-%d %H:%M')"
  pids="$(worker_pids)"
  if [ -z "$pids" ]; then
    if batch_alive; then
      echo "$ts batch alive, no worker (between steps)" ; continue
    fi
    echo "$ts batch finished:"
    tail -n 3 "$LOG" | cut -c1-120
    break
  fi
  pid="$(echo "$pids" | head -n 1)"
  cpu="$(worker_cpu "$pid")"
  out="$(newest_output . "$INTERVAL")"
  echo "$ts pid=$pid cpu=$cpu fresh_output=$([ -n "$out" ] && echo yes || echo no)"
  if [ "$cpu" = "$last_cpu" ] && [ -z "$out" ]; then
    still=$((still + 1))
  else
    still=0
  fi
  # stuck if frozen across enough polls to cover STALL_MIN
  need=$(( (STALL_MIN * 60 + INTERVAL - 1) / INTERVAL ))
  [ "$need" -lt 1 ] && need=1
  if [ "$still" -ge "$need" ]; then
    if [ "$DRY" -eq 1 ]; then
      echo "$ts DRY-RUN would kill -9 $pid"
    else
      echo "$ts wedged ${STALL_MIN}min+ -> kill -9 $pid"
      kill -9 "$pid" 2>/dev/null || true
    fi
    still=0
  fi
  last_cpu="$cpu"; last_out="$out"
done
echo "supervision ended; aggregate with: bash scripts/summarize_table1.sh"

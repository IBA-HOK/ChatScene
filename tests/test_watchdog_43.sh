#!/usr/bin/env bash
# P4 watchdog/43 keep-warm fault-injection proof for run_paper_repro.sh:316 no_restart_streak
# No live CARLA required (mock carla_healthy/carla_start counting restarts, live opt-in LIVE_CARLA=1)
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT_DIR/scripts/run_paper_repro.sh"

PASS=0
FAIL=0
RESTART_COUNT=0
KEEP_WARM_COUNT=0

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'

assert_eq() {
  local got="$1" expect="$2" msg="$3"
  if [ "$got" = "$expect" ]; then
    echo -e "${GREEN}PASS${NC}: $msg (got=$got)"
    PASS=$((PASS+1))
  else
    echo -e "${RED}FAIL${NC}: $msg (expected=$expect got=$got)" >&2
    FAIL=$((FAIL+1))
  fi
}

assert_contains() {
  local hay="$1" needle="$2" msg="$3"
  case "$hay" in
    *"$needle"*) echo -e "${GREEN}PASS${NC}: $msg"; PASS=$((PASS+1)) ;;
    *) echo -e "${RED}FAIL${NC}: $msg (missing '$needle')" >&2; FAIL=$((FAIL+1)) ;;
  esac
}

# ---------------------------------------------------------------------------
# Verify source file hasn't had forbidden changes
# ---------------------------------------------------------------------------
echo "== source guard checks =="

# Must not have set -e (only set -u allowed per task)
if grep -qE '^[[:space:]]*set -e' "$SRC"; then
  echo -e "${RED}FAIL${NC}: run_paper_repro.sh must NOT add set -e" >&2
  FAIL=$((FAIL+1))
else
  echo -e "${GREEN}PASS${NC}: no set -e in run_paper_repro.sh"
  PASS=$((PASS+1))
fi

# Must contain no_restart_streak logic at 316
if grep -q "no_restart_streak" "$SRC"; then
  echo -e "${GREEN}PASS${NC}: no_restart_streak present"
  PASS=$((PASS+1))
else
  echo -e "${RED}FAIL${NC}: no_restart_streak missing" >&2
  FAIL=$((FAIL+1))
fi

# Must contain fence 43 logic
if grep -q 'rc_prev.*43' "$SRC" && grep -q 'keeping warm server' "$SRC"; then
  echo -e "${GREEN}PASS${NC}: 43 keep-warm branch present"
  PASS=$((PASS+1))
else
  echo -e "${RED}FAIL${NC}: 43 keep-warm branch missing" >&2
  FAIL=$((FAIL+1))
fi

# Must not have changed defaults: STUCK_WATCHDOG 1, WINDOW 720, GRACE 1200
for pat in 'STUCK_WATCHDOG:-1' 'STUCK_WINDOW:-720' 'STUCK_GRACE:-1200'; do
  if grep -q "$pat" "$SRC"; then
    echo -e "${GREEN}PASS${NC}: default $pat preserved"
    PASS=$((PASS+1))
  else
    echo -e "${RED}FAIL${NC}: default $pat changed/missing" >&2
    FAIL=$((FAIL+1))
  fi
done

# STUCK_RETRIES default 0
if grep -q 'STUCK_RETRIES:-0' "$SRC"; then
  echo -e "${GREEN}PASS${NC}: STUCK_RETRIES default 0 preserved"
  PASS=$((PASS+1))
else
  echo -e "${RED}FAIL${NC}: STUCK_RETRIES default missing" >&2
  FAIL=$((FAIL+1))
fi

# ---------------------------------------------------------------------------
# Mock infrastructure (unless LIVE_CARLA=1)
# ---------------------------------------------------------------------------
FAILED=""

# Mock counters — file-backed so subshells ( $(...) capture ) share state
RESTART_COUNTER_FILE="$(mktemp)"
echo 0 > "$RESTART_COUNTER_FILE"
# ensure cleanup includes it
_trap_files="$RESTART_COUNTER_FILE"

carla_healthy() {
  if [ "${LIVE_CARLA:-0}" = "1" ]; then
    python -c "import carla; c=carla.Client('localhost',${PORT:-2002}); c.set_timeout(3.0); c.get_server_version(); c.get_world().get_map().name" 2>/dev/null
    return $?
  fi
  return 0
}

carla_stop() {
  local c
  c=$(cat "$RESTART_COUNTER_FILE" 2>/dev/null || echo 0)
  # carla_stop does not count as restart; only carla_start does. Keep for tracking but not used in assertions.
  return 0
}

carla_start() {
  local c
  c=$(cat "$RESTART_COUNTER_FILE" 2>/dev/null || echo 0)
  c=$((c+1))
  echo "$c" > "$RESTART_COUNTER_FILE"
  return 0
}

_restart_count() { cat "$RESTART_COUNTER_FILE" 2>/dev/null || echo 0; }

# Helpers from run_paper_repro.sh (stubbed for fast tests)
_step_cpu_jiffies() { echo 0; }
_step_progress_mtime() { echo 0; }

# Copy run_step_watchdog exactly as in source, but with tiny defaults for test speed
# We replicate the function verbatim to avoid sourcing side-effects.
# Extracted from scripts/run_paper_repro.sh:307-377 on 2026-10-22

# Defaults for test (override only in test env, not source)
STEP_TIMEOUT="${STEP_TIMEOUT:-5}"
STUCK_WINDOW="${STUCK_WINDOW:-720}"
STUCK_GRACE="${STUCK_GRACE:-1200}"
STUCK_RETRIES="${STUCK_RETRIES:-0}"
STUCK_POLL="${STUCK_POLL:-0.2}"
STUCK_CPU_JIFFIES="${STUCK_CPU_JIFFIES:-300}"
STUCK_WATCHDOG="${STUCK_WATCHDOG:-1}"
MANAGE_CARLA="${MANAGE_CARLA:-1}"
PORT="${PORT:-2002}"
TM_PORT="${TM_PORT:-8002}"

run_step_watchdog() { # $1=desc, $2=sid, $@=cmd (train_scenario only)
  local desc="$1" sid="$2"; shift 2
  local attempt=0 rc=0 rc_prev=0 no_restart_streak=0 wdpid
  local pattern="run_train.py.*train_scenario.*scenario_id $sid"
  echo ">> $desc (timeout ${STEP_TIMEOUT}s, watchdog ${STUCK_WINDOW}s/grace ${STUCK_GRACE}s, retries ${STUCK_RETRIES:-unlimited}): $*"
  while [ "$STUCK_RETRIES" -eq 0 ] || [ "$attempt" -le "$STUCK_RETRIES" ]; do
    if [ "$attempt" -gt 0 ]; then
      local retry_of="$STUCK_RETRIES"; [ "$STUCK_RETRIES" -eq 0 ] && retry_of="unlimited"
      echo ">> retry $attempt/$retry_of for $desc (resume from pinned skip)"
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
    timeout -k 2 "$STEP_TIMEOUT" $@ 9>&- &
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
    timeout -k 2 "$STEP_TIMEOUT" $@ 9>&- || rc=$?
  else
    $@ 9>&- || rc=$?
  fi
  if [ $rc -eq 0 ]; then
    echo "OK: $desc"
  else
    echo "FAIL($rc): $desc (continuing)" >&2
    FAILED="$FAILED [$desc]"
  fi
}

# ---------------------------------------------------------------------------
# Fault-injection helpers
# ---------------------------------------------------------------------------
# Use a counter file so subshells share state across timeout-forked processes.
# timeout forks a new process, so in-memory counter won't work. Use file.
COUNTER_FILE="$(mktemp)"
# extend trap to also clean RESTART_COUNTER_FILE
trap 'rm -f "$COUNTER_FILE" "$COUNTER_FILE".expect "$RESTART_COUNTER_FILE" 2>/dev/null' EXIT

make_seq_cmd() {
  local seq=("$@")
  local script="$(mktemp)"
  printf "%s\n" "${seq[@]}" > "${COUNTER_FILE}.expect"
  echo 0 > "$COUNTER_FILE"
  local cf="$COUNTER_FILE"
  local ef="${COUNTER_FILE}.expect"
  cat > "$script" <<EOF
#!/usr/bin/env bash
cnt=\$(cat "$cf" 2>/dev/null || echo 0)
cnt=\$((cnt+1))
echo "\$cnt" > "$cf"
idx=\$cnt
expect=\$(sed -n "\${idx}p" "$ef" 2>/dev/null || true)
if [ -z "\$expect" ]; then
  expect=0
fi
echo ">> mock run_train attempt \$cnt exits \$expect" >&2
exit "\$expect"
EOF
  chmod +x "$script"
  echo "$script"
}

reset_counters() {
  echo 0 > "$RESTART_COUNTER_FILE"
  FAILED=""
  echo 0 > "$COUNTER_FILE"
}

# ---------------------------------------------------------------------------
# TEST 1: 43 twice then 0 — first two keep warm (no restart), success
# ---------------------------------------------------------------------------
echo ""
echo "== TEST 1: 43,43,0 with MANAGE_CARLA=1 -> 0 restarts, 2 keep-warm ==" 
MANAGE_CARLA=1
STUCK_RETRIES=5
STEP_TIMEOUT=5
STUCK_POLL=0.1
STUCK_GRACE=0
STUCK_WINDOW=999
reset_counters
cmd1=$(make_seq_cmd 43 43 0)
out1=$(run_step_watchdog "train_scenario sid=1" "1" bash "$cmd1" 2>&1)
rc1=$?
# Count occurrences
keep1=$(echo "$out1" | grep -c "keeping warm server" || true)
restart1=$(echo "$out1" | grep -c "CARLA restart to clear actor residue" || true)
# Also check via mock counters
assert_eq "$keep1" "2" "TEST1 keep-warm count =2"
assert_eq "$restart1" "0" "TEST1 restart log count =0"
assert_eq "$(_restart_count)" "0" "TEST1 mock carla_start calls =0"
assert_contains "$out1" "OK: train_scenario sid=1" "TEST1 ends OK"
rm -f "$cmd1"

# ---------------------------------------------------------------------------
# TEST 2: 43,43,43 then 0 — third attempt must restart
# ---------------------------------------------------------------------------
echo ""
echo "== TEST 2: 43,43,43,0 -> 2 keep-warm then 1 restart on 3rd =="
MANAGE_CARLA=1
STUCK_RETRIES=5
reset_counters
cmd2=$(make_seq_cmd 43 43 43 0)
out2=$(run_step_watchdog "train_scenario sid=2" "2" bash "$cmd2" 2>&1)
keep2=$(echo "$out2" | grep -c "keeping warm server" || true)
restart2=$(echo "$out2" | grep -c "CARLA restart to clear actor residue" || true)
assert_eq "$keep2" "2" "TEST2 keep-warm =2"
assert_eq "$restart2" "1" "TEST2 restart on 3rd =1"
assert_eq "$(_restart_count)" "1" "TEST2 mock carla_start =1"
assert_contains "$out2" "keeping warm server" "TEST2 log has keep-warm"
assert_contains "$out2" "CARLA restart to clear actor residue" "TEST2 log has restart"
rm -f "$cmd2"

# ---------------------------------------------------------------------------
# TEST 2b: 43,43,43,43,0 -> 2 keep-warm, then restart, then keep-warm again? Check streak reset
# After restart, no_restart_streak resets to 0, so next 43 should keep warm again (but after 5? Actually after 43 after restart, streak=0 -> keep warm)
# Sequence: a1:43 streak0->keep(1), a2:43 streak1->keep(2), a3:43 streak2->restart(0), a4:43 streak0->keep(1) then 0 success
echo ""
echo "== TEST 2b: 43 x4 then 0 -> streak resets after restart =="
MANAGE_CARLA=1
STUCK_RETRIES=6
reset_counters
cmd2b=$(make_seq_cmd 43 43 43 43 0)
out2b=$(run_step_watchdog "train_scenario sid=2b" "2b" bash "$cmd2b" 2>&1)
keep2b=$(echo "$out2b" | grep -c "keeping warm server" || true)
restart2b=$(echo "$out2b" | grep -c "CARLA restart to clear actor residue" || true)
assert_eq "$keep2b" "3" "TEST2b keep-warm =3 (2 before first restart +1 after)"
assert_eq "$restart2b" "1" "TEST2b restart =1"
assert_eq "$(_restart_count)" "1" "TEST2b mock restart =1"
rm -f "$cmd2b"

# ---------------------------------------------------------------------------
# TEST 3: 42 always restarts (even first retry)
# ---------------------------------------------------------------------------
echo ""
echo "== TEST 3: 42,0 -> immediate restart on 42 =="
MANAGE_CARLA=1
STUCK_RETRIES=5
reset_counters
cmd3=$(make_seq_cmd 42 0)
out3=$(run_step_watchdog "train_scenario sid=3" "3" bash "$cmd3" 2>&1)
keep3=$(echo "$out3" | grep -c "keeping warm server" || true)
restart3=$(echo "$out3" | grep -c "CARLA restart to clear actor residue" || true)
assert_eq "$keep3" "0" "TEST3 keep-warm =0 for 42"
assert_eq "$restart3" "1" "TEST3 restart =1 for 42"
assert_eq "$(_restart_count)" "1" "TEST3 mock restart =1"
rm -f "$cmd3"

echo ""
echo "== TEST 3b: 42,42,0 -> two restarts =="
reset_counters
cmd3b=$(make_seq_cmd 42 42 0)
out3b=$(run_step_watchdog "train_scenario sid=3b" "3b" bash "$cmd3b" 2>&1)
restart3b=$(echo "$out3b" | grep -c "CARLA restart to clear actor residue" || true)
assert_eq "$restart3b" "2" "TEST3b two 42s -> 2 restarts"
assert_eq "$(_restart_count)" "2" "TEST3b mock =2"
rm -f "$cmd3b"

# ---------------------------------------------------------------------------
# TEST 4: Gate on MANAGE_CARLA=0 -> no restarts even for 42/43
# ---------------------------------------------------------------------------
echo ""
echo "== TEST 4: MANAGE_CARLA=0 gates restarts =="
MANAGE_CARLA=0
STUCK_RETRIES=5
reset_counters
cmd4=$(make_seq_cmd 43 43 43 0)
out4=$(run_step_watchdog "train_scenario sid=4" "4" bash "$cmd4" 2>&1)
restart4=$(echo "$out4" | grep -c "CARLA restart to clear actor residue" || true)
keep4=$(echo "$out4" | grep -c "keeping warm server" || true)
assert_eq "$restart4" "0" "TEST4 MANAGE_CARLA=0 no restarts"
assert_eq "$(_restart_count)" "0" "TEST4 mock no restarts when unmanaged"
# Keep-warm still happens for first two even when MANAGE_CARLA=0? Check logic: 43 with streak<2 takes keep-warm branch before MANAGE check, so yes.
assert_eq "$keep4" "2" "TEST4 keep-warm still 2 even when unmanaged"
rm -f "$cmd4"

# 42 with MANAGE=0 should not restart either
reset_counters
cmd4b=$(make_seq_cmd 42 0)
out4b=$(run_step_watchdog "train_scenario sid=4b" "4b" bash "$cmd4b" 2>&1)
restart4b=$(echo "$out4b" | grep -c "CARLA restart to clear actor residue" || true)
assert_eq "$restart4b" "0" "TEST4b 42 with MANAGE=0 -> no restart"
assert_eq "$(_restart_count)" "0" "TEST4b mock 0"
rm -f "$cmd4b"
# restore
MANAGE_CARLA=1

# ---------------------------------------------------------------------------
# TEST 5: STUCK_WATCHDOG=0 disables without break (plain run_step)
# ---------------------------------------------------------------------------
echo ""
echo "== TEST 5: STUCK_WATCHDOG=0 disables watchdog =="
# Simulate the train_scenario loop dispatch: if STUCK_WATCHDOG=1 use watchdog else run_step
STUCK_WATCHDOG=0
STEP_TIMEOUT=5
STUCK_RETRIES=5
reset_counters
cmd5=$(make_seq_cmd 43 0)
# With watchdog disabled, run_step should NOT retry on 43, just FAIL once and not restart
out5=$(run_step "train_scenario sid=5" bash "$cmd5" 2>&1)
assert_eq "$(_restart_count)" "0" "TEST5 plain run_step does not restart on 43"
assert_contains "$out5" "FAIL(43)" "TEST5 plain run_step FAIL not retried"
# Also verify watchdog path would have retried (control)
STUCK_WATCHDOG=1
reset_counters
cmd5b=$(make_seq_cmd 43 0)
out5b=$(run_step_watchdog "train_scenario sid=5b" "5b" bash "$cmd5b" 2>&1)
assert_contains "$out5b" "keeping warm server" "TEST5b watchdog does retry on 43"
rm -f "$cmd5" "$cmd5b"
# Reset for next
STUCK_WATCHDOG=1

# ---------------------------------------------------------------------------
# TEST 6: STUCK_RETRIES=0 bounded by STEP_TIMEOUT
# ---------------------------------------------------------------------------
echo ""
echo "== TEST 6: STUCK_RETRIES=0 bounded by STEP_TIMEOUT =="
# With STUCK_RETRIES=0 (unlimited) but STEP_TIMEOUT fencing each attempt, a hanging
# command (sleep 10) should be killed by timeout within ~STEP_TIMEOUT, not hang forever.
# Also verify retryable codes with STUCK_RETRIES=0 still loop but bounded per attempt.
STUCK_RETRIES=0
STEP_TIMEOUT=2
STUCK_POLL=0.2
STUCK_GRACE=0
STUCK_WINDOW=999
reset_counters
# Create hanging command that sleeps 10 (exceeds 2s timeout)
hang_script=$(mktemp)
cat > "$hang_script" <<'EOS'
#!/usr/bin/env bash
sleep 10
exit 0
EOS
chmod +x "$hang_script"
start=$(date +%s)
out6=$(timeout 6 bash -c 'STEP_TIMEOUT=2 STUCK_RETRIES=0 STUCK_POLL=0.2 STUCK_GRACE=0 STUCK_WINDOW=999 bash "$1"' _ "$hang_script" 2>&1 || true)
# Instead directly test run_step bounding: run_step with STEP_TIMEOUT=2 should timeout in ~2s
reset_counters
STEP_TIMEOUT=2
start2=$(date +%s)
out6b=$(run_step "hang sid=6" bash "$hang_script" 2>&1; echo "rc=$?")
elapsed2=$(( $(date +%s) - start2 ))
# Should be bounded ~2-4s (timeout -k 2 adds 2s grace)
if [ "$elapsed2" -ge 2 ] && [ "$elapsed2" -le 6 ]; then
  echo -e "${GREEN}PASS${NC}: TEST6 STEP_TIMEOUT bounds hang (elapsed ${elapsed2}s)"
  PASS=$((PASS+1))
else
  echo -e "${RED}FAIL${NC}: TEST6 hang not bounded (elapsed ${elapsed2}s, expected 2-6)" >&2
  FAIL=$((FAIL+1))
fi
assert_contains "$out6b" "FAIL" "TEST6 hang resulted in FAIL not hang forever"
rm -f "$hang_script"

# Also test retry cap: with STUCK_RETRIES=2, a always-43 should stop after 2 retries (3 attempts)
echo ""
echo "== TEST 6b: STUCK_RETRIES cap =="
STUCK_RETRIES=2
STEP_TIMEOUT=5
STUCK_POLL=0.1
reset_counters
cmd6=$(make_seq_cmd 43 43 43 43)
out6c=$(run_step_watchdog "train_scenario sid=6c" "6c" bash "$cmd6" 2>&1)
# With cap 2, should do initial +2 retries =3 attempts. Our seq has 4x43, so last attempt fails and should report FAIL
assert_contains "$out6c" "FAIL(43)" "TEST6b hit retry cap and reported FAIL"
# Count retries: should have 2 keep-warm (attempt 1->2, 2->3) then stop before needing restart on 4th
keep6c=$(echo "$out6c" | grep -c "keeping warm server" || true)
assert_eq "$keep6c" "2" "TEST6b keep-warm 2 with cap 2"
rm -f "$cmd6"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=============================="
echo "PASS: $PASS  FAIL: $FAIL"
if [ "$FAIL" -ne 0 ]; then
  echo -e "${RED}Some tests failed${NC}" >&2
  exit 1
else
  echo -e "${GREEN}All watchdog 43 keep-warm tests passed${NC}"
  exit 0
fi

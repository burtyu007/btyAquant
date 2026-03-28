#!/bin/zsh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"

BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
BACKEND_LOG="$RUN_DIR/backend.log"
FRONTEND_LOG="$RUN_DIR/frontend.log"

BACKEND_HOST="127.0.0.1"
BACKEND_PORT="8899"
FRONTEND_HOST="127.0.0.1"
FRONTEND_PORT="5173"
MYSQL_HOST_DEFAULT="127.0.0.1"
MYSQL_PORT_DEFAULT="3380"
MYSQL_USER_DEFAULT="root"
MYSQL_PASSWORD_DEFAULT="Burtyu1989"
MYSQL_DB_DEFAULT="quant"
REDIS_HOST_DEFAULT="127.0.0.1"
REDIS_PORT_DEFAULT="6379"
REDIS_DB_DEFAULT="0"

mkdir -p "$RUN_DIR"

is_pid_running() {
  local pid="$1"
  kill -0 "$pid" >/dev/null 2>&1
}

read_pid() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    cat "$pid_file"
  fi
}

cleanup_pid_file() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    rm -f "$pid_file"
  fi
}

launch_detached() {
  local workdir="$1"
  local log_file="$2"
  local pid_file="$3"
  shift 3

  cleanup_pid_file "$pid_file"
  python - "$workdir" "$log_file" "$pid_file" "$@" <<'PY'
import os
import subprocess
import sys

workdir = sys.argv[1]
log_file = sys.argv[2]
pid_file = sys.argv[3]
command = sys.argv[4:]

with open(log_file, "ab", buffering=0) as log_handle, open(os.devnull, "rb") as stdin_handle:
    process = subprocess.Popen(
        command,
        cwd=workdir,
        stdin=stdin_handle,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )

with open(pid_file, "w", encoding="utf-8") as pid_handle:
    pid_handle.write(str(process.pid))
PY
}

start_backend() {
  local existing_pid
  existing_pid="$(read_pid "$BACKEND_PID_FILE" || true)"
  if [[ -n "${existing_pid:-}" ]] && is_pid_running "$existing_pid"; then
    echo "Backend already running on http://$BACKEND_HOST:$BACKEND_PORT (PID $existing_pid)"
    return
  fi
  launch_detached \
    "$ROOT_DIR/backend" \
    "$BACKEND_LOG" \
    "$BACKEND_PID_FILE" \
    env \
    MYSQL_HOST="$MYSQL_HOST_DEFAULT" \
    MYSQL_PORT="$MYSQL_PORT_DEFAULT" \
    MYSQL_USER="$MYSQL_USER_DEFAULT" \
    MYSQL_PASSWORD="$MYSQL_PASSWORD_DEFAULT" \
    MYSQL_DB="$MYSQL_DB_DEFAULT" \
    REDIS_HOST="$REDIS_HOST_DEFAULT" \
    REDIS_PORT="$REDIS_PORT_DEFAULT" \
    REDIS_DB="$REDIS_DB_DEFAULT" \
    python -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT"
  echo "Backend started on http://$BACKEND_HOST:$BACKEND_PORT"
}

start_frontend() {
  local existing_pid
  existing_pid="$(read_pid "$FRONTEND_PID_FILE" || true)"
  if [[ -n "${existing_pid:-}" ]] && is_pid_running "$existing_pid"; then
    echo "Frontend already running on http://$FRONTEND_HOST:$FRONTEND_PORT (PID $existing_pid)"
    return
  fi
  launch_detached \
    "$ROOT_DIR/frontend" \
    "$FRONTEND_LOG" \
    "$FRONTEND_PID_FILE" \
    npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
  echo "Frontend started on http://$FRONTEND_HOST:$FRONTEND_PORT"
}

stop_by_pid_file() {
  local pid_file="$1"
  local service_name="$2"
  local pid
  pid="$(read_pid "$pid_file" || true)"
  if [[ -z "${pid:-}" ]]; then
    echo "$service_name is not running (no PID file)."
    return
  fi
  if is_pid_running "$pid"; then
    kill "$pid" >/dev/null 2>&1 || true
    sleep 1
    if is_pid_running "$pid"; then
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
    echo "$service_name stopped (PID $pid)."
  else
    echo "$service_name PID file was stale (PID $pid)."
  fi
  cleanup_pid_file "$pid_file"
}

stop_backend_fallback() {
  local pids
  pids="$(lsof -ti tcp:$BACKEND_PORT -sTCP:LISTEN || true)"
  if [[ -n "${pids:-}" ]]; then
    echo "$pids" | xargs kill >/dev/null 2>&1 || true
  fi
}

stop_frontend_fallback() {
  local pids
  pids="$(lsof -ti tcp:$FRONTEND_PORT -sTCP:LISTEN || true)"
  if [[ -n "${pids:-}" ]]; then
    echo "$pids" | xargs kill >/dev/null 2>&1 || true
  fi
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local attempts="${3:-20}"
  local i
  for ((i = 1; i <= attempts; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$label is ready: $url"
      return 0
    fi
    sleep 1
  done
  echo "$label did not become ready in time: $url"
  return 1
}

print_logs_hint() {
  echo "Backend log:  $BACKEND_LOG"
  echo "Frontend log: $FRONTEND_LOG"
}

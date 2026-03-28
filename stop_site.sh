#!/bin/zsh

set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/site_common.sh"

stop_by_pid_file "$BACKEND_PID_FILE" "Backend"
stop_by_pid_file "$FRONTEND_PID_FILE" "Frontend"
stop_backend_fallback
stop_frontend_fallback

echo "Site stop sequence completed."

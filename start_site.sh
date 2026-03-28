#!/bin/zsh

set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/site_common.sh"

start_backend
start_frontend

wait_for_url "http://$BACKEND_HOST:$BACKEND_PORT/health" "Backend"
wait_for_url "http://$FRONTEND_HOST:$FRONTEND_PORT" "Frontend"

print_logs_hint

#!/bin/zsh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

"$ROOT_DIR/stop_site.sh"
"$ROOT_DIR/start_site.sh"

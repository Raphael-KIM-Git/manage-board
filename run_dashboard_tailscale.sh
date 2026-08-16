#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
export OPS_DASHBOARD_HOST="${OPS_DASHBOARD_HOST:-127.0.0.1}"
export OPS_DASHBOARD_PORT="${OPS_DASHBOARD_PORT:-8765}"
exec python3 "$SCRIPT_DIR/operations_dashboard_server.py"

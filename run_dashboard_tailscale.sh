#!/usr/bin/env bash
set -euo pipefail
export OPS_DASHBOARD_HOST="${OPS_DASHBOARD_HOST:-127.0.0.1}"
export OPS_DASHBOARD_PORT="${OPS_DASHBOARD_PORT:-8765}"
exec python3 /home/raphael/myproject/operations_dashboard_server.py

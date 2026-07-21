#!/usr/bin/env bash
# Idempotent recovery entrypoint called by Windows Task Scheduler.
# Starts the dashboard supervisor and HermesPM gateway/watchdog when absent.
set -euo pipefail

DASHBOARD_SESSION=agent-hub-dashboard
DASHBOARD_SUPERVISOR=/home/raphael/myproject/dashboard-supervisor.sh
HERMES_PM_START=/home/raphael/start-hermes-pm-gw.sh

if ! command -v tmux >/dev/null 2>&1; then
  echo 'tmux is required for Agent Hub recovery' >&2
  exit 1
fi

if ! tmux has-session -t "$DASHBOARD_SESSION" 2>/dev/null; then
  tmux new-session -d -s "$DASHBOARD_SESSION" "bash $DASHBOARD_SUPERVISOR"
  echo "started: $DASHBOARD_SESSION"
else
  echo "already running: $DASHBOARD_SESSION"
fi

bash "$HERMES_PM_START"

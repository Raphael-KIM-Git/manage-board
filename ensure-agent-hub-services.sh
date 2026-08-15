#!/usr/bin/env bash
# Idempotent recovery entrypoint called by Windows Task Scheduler.
# Starts the dashboard supervisor and HermesPM gateway/watchdog when absent.
set -euo pipefail

DASHBOARD_SESSION=${DASHBOARD_SESSION:-agent-hub-dashboard}
DASHBOARD_SUPERVISOR=${DASHBOARD_SUPERVISOR:-/home/raphael/myproject/dashboard-supervisor.sh}
HERMES_PM_START=${HERMES_PM_START:-/home/raphael/start-hermes-pm-gw.sh}
DASHBOARD_HEALTH_URL=${DASHBOARD_HEALTH_URL:-http://127.0.0.1:8765/api/health}
DASHBOARD_HEALTH_FAILURES_FILE=${DASHBOARD_HEALTH_FAILURES_FILE:-/tmp/agent-hub-dashboard-health-failures}

if ! command -v tmux >/dev/null 2>&1; then
  echo 'tmux is required for Agent Hub recovery' >&2
  exit 1
fi

if ! tmux has-session -t "$DASHBOARD_SESSION" 2>/dev/null; then
  tmux new-session -d -s "$DASHBOARD_SESSION" "bash $DASHBOARD_SUPERVISOR"
  rm -f "$DASHBOARD_HEALTH_FAILURES_FILE"
  echo "started: $DASHBOARD_SESSION"
else
  if curl -fsS --max-time 5 "$DASHBOARD_HEALTH_URL" >/dev/null 2>&1; then
    rm -f "$DASHBOARD_HEALTH_FAILURES_FILE"
    echo "healthy: $DASHBOARD_SESSION"
  else
    failures=0
    if [[ -f "$DASHBOARD_HEALTH_FAILURES_FILE" ]]; then
      read -r failures < "$DASHBOARD_HEALTH_FAILURES_FILE" || failures=0
    fi
    failures=$((failures + 1))
    printf '%s\n' "$failures" > "$DASHBOARD_HEALTH_FAILURES_FILE"
    if (( failures >= 2 )); then
      tmux kill-session -t "$DASHBOARD_SESSION" 2>/dev/null || true
      tmux new-session -d -s "$DASHBOARD_SESSION" "bash $DASHBOARD_SUPERVISOR"
      rm -f "$DASHBOARD_HEALTH_FAILURES_FILE"
      echo "restarted unhealthy: $DASHBOARD_SESSION"
    else
      echo "health check failed (1/2): $DASHBOARD_SESSION"
    fi
  fi
fi

bash "$HERMES_PM_START"

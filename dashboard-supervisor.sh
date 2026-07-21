#!/usr/bin/env bash
# Keep the operations dashboard alive inside a persistent tmux session.
set -u

LOG_DIR=/home/raphael/myproject/logs
mkdir -p "$LOG_DIR"

while true; do
  printf '[%s] starting operations dashboard\n' "$(date '+%F %T')" >> "$LOG_DIR/dashboard-supervisor.log"
  /home/raphael/myproject/run_dashboard_tailscale.sh >> "$LOG_DIR/dashboard.log" 2>&1
  rc=$?
  printf '[%s] dashboard exited (rc=%s); retrying in 10s\n' "$(date '+%F %T')" "$rc" >> "$LOG_DIR/dashboard-supervisor.log"
  sleep 10
done

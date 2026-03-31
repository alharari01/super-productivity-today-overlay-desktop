#!/usr/bin/env bash

set -euo pipefail

APP="$HOME/.config/super-today-overlay/today-overlay.py"
LOG="/tmp/super-today-overlay.log"
PIDFILE="$HOME/.config/super-today-overlay/overlay.pid"

mkdir -p "$(dirname "$PIDFILE")"

if [[ -f "$PIDFILE" ]]; then
  PID="$(cat "$PIDFILE")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
    sleep 0.3
  fi
fi

nohup python3 "$APP" >"$LOG" 2>&1 &
echo $! >"$PIDFILE"


#!/usr/bin/env bash

set -euo pipefail

PIDFILE="$HOME/.config/super-today-overlay/overlay.pid"

if [[ -f "$PIDFILE" ]]; then
  PID="$(cat "$PIDFILE")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
  fi
  rm -f "$PIDFILE"
  exit 0
fi

pkill -f "today-overlay.py" 2>/dev/null || true


#!/usr/bin/env bash
# Tradedesk launcher — starts the backend and dashboard, opens the app.
# Usage: ./start.sh          (Ctrl-C stops both servers)
set -euo pipefail
set -m   # job control: each background job gets its own process group (for clean kills)

cd "$(dirname "$0")"

BACKEND_PORT=8000
FRONTEND_PORT=5173
LOG_DIR=.logs
mkdir -p "$LOG_DIR"

# uv may live in ~/.local/bin without being on PATH
UV=$(command -v uv || echo "$HOME/.local/bin/uv")

port_busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

PIDS=()
cleanup() {
  echo
  echo "Shutting down…"
  # kill each subshell's whole process group so uvicorn/vite children die too
  for pid in "${PIDS[@]:-}"; do kill -- -"$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
  echo "Stopped."
}
trap cleanup EXIT INT TERM

# --- backend ---
if port_busy $BACKEND_PORT; then
  echo "✓ Backend already running on :$BACKEND_PORT"
else
  echo "Starting backend on :$BACKEND_PORT…"
  ("$UV" run uvicorn backend.main:app --port $BACKEND_PORT >"$LOG_DIR/backend.log" 2>&1) &
  PIDS+=($!)
fi

# --- frontend ---
if port_busy $FRONTEND_PORT; then
  echo "✓ Dashboard already running on :$FRONTEND_PORT"
else
  echo "Starting dashboard on :$FRONTEND_PORT…"
  (cd frontend && exec npm run dev >"../$LOG_DIR/frontend.log" 2>&1) &
  PIDS+=($!)
fi

# --- wait until both answer ---
echo -n "Waiting for services"
for _ in $(seq 1 60); do
  if curl -sf "http://localhost:$BACKEND_PORT/api/health" >/dev/null 2>&1 \
     && curl -sf "http://localhost:$FRONTEND_PORT/" >/dev/null 2>&1; then
    echo " ready."
    break
  fi
  echo -n "."
  sleep 1
done

if ! curl -sf "http://localhost:$BACKEND_PORT/api/health" >/dev/null 2>&1; then
  echo
  echo "Backend failed to start — see $LOG_DIR/backend.log" >&2
  exit 1
fi

echo "Tradedesk → http://localhost:$FRONTEND_PORT"
command -v open >/dev/null && open "http://localhost:$FRONTEND_PORT"

# If we started anything, stay in the foreground so Ctrl-C stops it all.
if [ ${#PIDS[@]} -gt 0 ]; then
  echo "Logs: $LOG_DIR/backend.log · $LOG_DIR/frontend.log   (Ctrl-C to stop)"
  wait
else
  trap - EXIT INT TERM   # nothing started by us — nothing to clean up
fi

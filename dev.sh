#!/usr/bin/env bash
# Start dashboard + job poller together.
# Usage: ./dev.sh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

# Load environment variables
set -a
source "$PROJECT_ROOT/.env" 2>/dev/null || true
[ -n "$EXTRA_ENV_FILE" ] && source "$EXTRA_ENV_FILE" 2>/dev/null || true
set +a

# Trap to kill both processes on exit
cleanup() {
  echo ""
  echo "[dev] Shutting down..."
  kill $POLLER_PID 2>/dev/null || true
  kill $DASHBOARD_PID 2>/dev/null || true
  wait 2>/dev/null
  echo "[dev] Done."
}
trap cleanup EXIT INT TERM

# Start job poller in background
echo "[dev] Starting job poller..."
python -m scripts.job_poller --interval 10 &
POLLER_PID=$!

# Start dashboard
echo "[dev] Starting dashboard (Next.js)..."
cd dashboard && npm run dev &
DASHBOARD_PID=$!

# Wait for either to exit
wait

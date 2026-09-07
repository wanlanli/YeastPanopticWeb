#!/usr/bin/env bash
# Starts all four YeastPanopticWeb processes (sam_service, panoptic_service,
# backend, frontend) in the background and leaves them running.
#
# One-time setup (per service, before this script will work):
#   cd backend          && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && deactivate
#   cd sam_service       && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && deactivate
#   cd panoptic_service  && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && pip install 'git+https://github.com/cocodataset/panopticapi.git' && deactivate
#   cd frontend          && npm install
#   cp .env.example .env && edit the paths in it (see comments there)
#
# Then just:
#   ./scripts/run_all.sh
#
# Stop everything with scripts/stop_all.sh. Logs go to logs/*.log; PIDs to
# .run/pids.txt.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

mkdir -p logs .run
: > .run/pids.txt

if [ -f .env ]; then
  echo "Loading .env"
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
else
  echo "No .env found -- copy .env.example to .env and fill in your paths first:"
  echo "  cp .env.example .env"
  exit 1
fi

check_venv() {
  local dir="$1"
  if [ ! -x "$dir/.venv/bin/python3" ]; then
    echo "Missing $dir/.venv -- run the one-time setup for $dir first (see the top of this script)."
    exit 1
  fi
}
check_venv backend
check_venv sam_service
check_venv panoptic_service
if [ ! -d frontend/node_modules ]; then
  echo "Missing frontend/node_modules -- run 'cd frontend && npm install' first."
  exit 1
fi

start() {
  local name="$1" dir="$2" cmd="$3"
  echo "Starting $name..."
  (
    cd "$dir"
    # shellcheck disable=SC2086
    nohup $cmd > "$REPO_ROOT/logs/$name.log" 2>&1 &
    echo "$name:$!" >> "$REPO_ROOT/.run/pids.txt"
  )
}

start sam_service      sam_service      ".venv/bin/uvicorn app:app --host 0.0.0.0 --port 8100"
start panoptic_service panoptic_service ".venv/bin/uvicorn app:app --host 0.0.0.0 --port 8200"
start backend          backend          ".venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000"
start frontend         frontend         "node_modules/.bin/vite --host 0.0.0.0"

wait_healthy() {
  local name="$1" url="$2"
  printf "Waiting for %s" "$name"
  for _ in $(seq 1 60); do
    if curl -sf "$url" > /dev/null 2>&1; then
      echo " -- up"
      return 0
    fi
    printf "."
    sleep 2
  done
  echo " -- still not responding after 2min; check logs/$name.log"
}

wait_healthy sam_service      "http://localhost:8100/health"
wait_healthy panoptic_service "http://localhost:8200/health"
wait_healthy backend          "http://localhost:8000/api/health"
wait_healthy frontend         "http://localhost:5173/"

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "======================================================================"
echo "Open:  http://${IP:-<this-server-ip>}:5173"
echo "Logs:  $REPO_ROOT/logs/"
echo "Stop:  $REPO_ROOT/scripts/stop_all.sh"
echo "======================================================================"

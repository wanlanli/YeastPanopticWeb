#!/usr/bin/env bash
# Starts all four YeastPanopticWeb processes (sam_service, panoptic_service,
# backend, frontend) in the background and leaves them running.
#
# One-time setup, before this script will work -- run ONE of these (both
# fetch the companion repos, install every service's deps, and write .env
# for you; the only thing left after either one is adding the panoptic
# model weights, see .env's comments):
#
#   ./scripts/setup_venv_envs.sh    # default -- needs the python3-venv system package
#   ./scripts/setup_conda_envs.sh   # use this instead if venv isn't available but conda is
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

PYTHON_ENV_MANAGER="${PYTHON_ENV_MANAGER:-venv}"  # venv | conda

if [ "$PYTHON_ENV_MANAGER" = "conda" ]; then
  CONDA_BASE="$(conda info --base 2>/dev/null || true)"
  if [ -z "$CONDA_BASE" ]; then
    echo "PYTHON_ENV_MANAGER=conda but 'conda info --base' failed -- is conda on PATH?"
    exit 1
  fi
elif [ "$PYTHON_ENV_MANAGER" != "venv" ]; then
  echo "Unknown PYTHON_ENV_MANAGER=$PYTHON_ENV_MANAGER (expected venv or conda)"
  exit 1
fi

# The interpreter for a given service dir, under whichever env manager is
# configured. Deliberately NOT `conda run -n ...`/`conda activate` -- those
# spawn a wrapper process, so the PID scripts/stop_all.sh tracks would be
# the wrapper, not the real server, leaving it orphaned after "stop".
# Calling the env's own interpreter directly (same idea as venv's
# .venv/bin/python3) avoids that.
#
# Already have a conda env with the right deps under a different name (e.g.
# an existing panoptic/SAM env, so you don't have to pip install into a
# fresh yeastpanoptic-* one)? Set an override in .env instead of renaming
# anything: BACKEND_PYTHON=/path/to/python3, SAM_SERVICE_PYTHON=..., or
# PANOPTIC_SERVICE_PYTHON=... (find the path with `conda env list`, or
# `conda run -n <env> which python3`). It's used as-is, no env-manager
# checks -- works the same whether PYTHON_ENV_MANAGER is venv or conda.
service_python() {
  local dir="$1"
  local override_var
  override_var="$(echo "$dir" | tr '[:lower:]' '[:upper:]')_PYTHON"
  if [ -n "${!override_var:-}" ]; then
    echo "${!override_var}"
  elif [ "$PYTHON_ENV_MANAGER" = "conda" ]; then
    echo "$CONDA_BASE/envs/yeastpanoptic-$dir/bin/python3"
  else
    echo "$REPO_ROOT/$dir/.venv/bin/python3"
  fi
}

check_env() {
  local dir="$1"
  local py; py="$(service_python "$dir")"
  local override_var
  override_var="$(echo "$dir" | tr '[:lower:]' '[:upper:]')_PYTHON"
  if [ ! -x "$py" ]; then
    if [ -n "${!override_var:-}" ]; then
      echo "$override_var=$py is set but not an executable file -- check the path."
    elif [ "$PYTHON_ENV_MANAGER" = "conda" ]; then
      echo "Missing conda env yeastpanoptic-$dir -- see the setup commands at the top of this script, or set $override_var=/path/to/python3 in .env to use an existing env instead."
    else
      echo "Missing $dir/.venv -- run the one-time setup for $dir first (see the top of this script), or set $override_var=/path/to/python3 in .env to use an existing env instead."
    fi
    exit 1
  fi
}
check_env backend
check_env sam_service
check_env panoptic_service
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

start sam_service      sam_service      "$(service_python sam_service) -m uvicorn app:app --host 0.0.0.0 --port 8100"
start panoptic_service panoptic_service "$(service_python panoptic_service) -m uvicorn app:app --host 0.0.0.0 --port 8200"
start backend          backend          "$(service_python backend) -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
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

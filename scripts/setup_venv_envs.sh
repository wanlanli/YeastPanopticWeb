#!/usr/bin/env bash
# One-time setup using plain venv (the default env manager for
# scripts/run_all.sh). Fetches the two companion repos (panoptic model
# code, CellMate), creates a .venv per service, installs each service's
# deps into it, and builds CellMate's Cython extension. Needs the
# python3-venv system package -- see scripts/setup_conda_envs.sh instead
# if that's not available and conda is (or can be installed without root).
#
# Safe to re-run: skips any repo/venv that already exists instead of
# recreating it, so you can re-run this after a partial failure (e.g. a
# network blip mid-install) without losing what already installed.
#
# Usage:
#   ./scripts/setup_venv_envs.sh
#
# Then: add the panoptic model weights (PANOPTIC_MODEL_DIR in .env -- the
# only thing this script can't fetch for you, see .env's comments) and run
# ./scripts/run_all.sh.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

"$REPO_ROOT/scripts/fetch_models.sh"

create_venv_and_install() {
  local dir="$1"
  shift
  if [ -x "$dir/.venv/bin/python3" ]; then
    echo "== $dir/.venv already exists, skipping creation =="
  else
    echo "== Creating $dir/.venv =="
    python3 -m venv "$dir/.venv"
  fi
  echo "== Installing $dir/requirements.txt =="
  "$dir/.venv/bin/pip" install -r "$REPO_ROOT/$dir/requirements.txt"
  for extra in "$@"; do
    echo "== Installing $extra into $dir/.venv =="
    "$dir/.venv/bin/pip" install "$extra"
  done
}

create_venv_and_install backend
create_venv_and_install sam_service
create_venv_and_install panoptic_service 'git+https://github.com/cocodataset/panopticapi.git'

MEASURE_DIR="$REPO_ROOT/external/CellMate/cellmate/image_measure/measure"
echo "== Building CellMate's Cython extension for backend's Python =="
backend/.venv/bin/pip install Cython
(cd "$MEASURE_DIR" && "$REPO_ROOT/backend/.venv/bin/python" setup.py build_ext --inplace)

if [ ! -f "$REPO_ROOT/.env" ]; then
  cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
fi
set_env_value() {
  local key="$1" value="$2"
  if grep -q "^${key}=" "$REPO_ROOT/.env"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$REPO_ROOT/.env"
  else
    echo "${key}=${value}" >> "$REPO_ROOT/.env"
  fi
}
set_env_value PANOPTIC_REPO_PATH "$REPO_ROOT/external/PytrochDeepyeast"
set_env_value CELLMATE_PATH "$REPO_ROOT/external/CellMate"

if [ ! -d frontend/node_modules ]; then
  echo "== Running npm install in frontend/ =="
  (cd frontend && npm install)
fi

echo
echo "======================================================================"
echo "Done. .env is set up and points at the cloned repos already."
echo "Only thing left: add the panoptic model weights -- edit"
echo "PANOPTIC_MODEL_DIR in .env (see its comment for what that is)."
echo
echo "Then:  ./scripts/run_all.sh"
echo
echo "GPU check once running (should print True if this machine has one):"
echo "  sam_service/.venv/bin/python3 -c \"import torch; print(torch.cuda.is_available())\""
echo "======================================================================"

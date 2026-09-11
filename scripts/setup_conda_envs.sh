#!/usr/bin/env bash
# One-time setup for a server with: conda already installed, no sudo/root,
# and (optionally) a GPU. Fetches the two companion repos (panoptic model
# code, CellMate), creates the three yeastpanoptic-* conda envs
# scripts/run_all.sh expects, installs each service's deps into them, and
# builds CellMate's Cython extension -- nothing here needs root, and torch
# installs with GPU support automatically from PyPI (no CUDA toolkit /
# driver install needed, as long as `nvidia-smi` already works on this
# machine).
#
# Safe to re-run: skips any repo/env that already exists instead of
# recreating it, so you can re-run this after a partial failure (e.g. a
# network blip mid-install) without losing what already installed.
#
# Usage:
#   ./scripts/setup_conda_envs.sh
#
# Then: add the panoptic model weights (PANOPTIC_MODEL_DIR in .env -- the
# only thing this script can't fetch for you, see .env's comments) and run
# ./scripts/run_all.sh.
#
# Some machines (often ones set up for/by NVIDIA NGC container workflows)
# have pip pre-configured to check pypi.ngc.nvidia.com -- NVIDIA's own
# internal PyPI mirror -- ahead of/instead of the public PyPI. If that
# hostname doesn't resolve from this network (common outside an actual NGC
# container), every torch-related install (torch, triton, the
# nvidia-*-cu12 wheels) hangs retrying it before failing. Everything this
# project needs is also on the public PyPI, so pip installs below are
# pinned to it explicitly rather than depending on whatever's already
# configured system/user-wide. Override with PIP_INDEX_URL=... before
# running this script if you deliberately want a different mirror (e.g. an
# internal one that isn't broken).

set -euo pipefail
export PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.org/simple}"
# A pip.conf/PIP_EXTRA_INDEX_URL pointing at the broken mirror would still
# make pip check it even with PIP_INDEX_URL overridden above (index-url and
# extra-index-url are independent settings) -- clear it unless the caller
# explicitly set one, since pip env vars take precedence over pip.conf.
export PIP_EXTRA_INDEX_URL="${PIP_EXTRA_INDEX_URL:-}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

CONDA_BASE="$(conda info --base 2>/dev/null || true)"
if [ -z "$CONDA_BASE" ]; then
  echo "conda not found on PATH. Install it first (e.g. Miniconda to your home dir --" \
       "no root needed), then re-run this script."
  exit 1
fi
# shellcheck disable=SC1091
source "$CONDA_BASE/etc/profile.d/conda.sh"

"$REPO_ROOT/scripts/fetch_models.sh"

create_env() {
  local name="$1"
  if conda env list | grep -qE "^${name}\s"; then
    echo "== $name already exists, skipping creation =="
  else
    echo "== Creating conda env $name (python 3.10) =="
    conda create -n "$name" python=3.10 -y
  fi
}

install_reqs() {
  local name="$1" dir="$2"
  echo "== Installing $dir/requirements.txt into $name =="
  conda run -n "$name" pip install -r "$REPO_ROOT/$dir/requirements.txt"
}

create_env yeastpanoptic-backend
install_reqs yeastpanoptic-backend backend

create_env yeastpanoptic-sam_service
install_reqs yeastpanoptic-sam_service sam_service

create_env yeastpanoptic-panoptic_service
install_reqs yeastpanoptic-panoptic_service panoptic_service
echo "== Installing panopticapi into yeastpanoptic-panoptic_service =="
conda run -n yeastpanoptic-panoptic_service pip install 'git+https://github.com/cocodataset/panopticapi.git'

MEASURE_DIR="$REPO_ROOT/external/CellMate/cellmate/image_measure/measure"
echo "== Building CellMate's Cython extension for yeastpanoptic-backend's Python =="
conda run -n yeastpanoptic-backend pip install Cython
(cd "$MEASURE_DIR" && conda run -n yeastpanoptic-backend python setup.py build_ext --inplace)

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
set_env_value PYTHON_ENV_MANAGER conda

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
echo "  $CONDA_BASE/envs/yeastpanoptic-sam_service/bin/python3 -c \"import torch; print(torch.cuda.is_available())\""
echo "======================================================================"

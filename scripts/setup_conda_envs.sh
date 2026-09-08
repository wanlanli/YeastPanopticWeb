#!/usr/bin/env bash
# One-time setup for a server with: conda already installed, no sudo/root,
# and (optionally) a GPU. Creates the three yeastpanoptic-* conda envs
# scripts/run_all.sh expects and installs each service's deps into them --
# nothing here needs root, and torch installs with GPU support
# automatically from PyPI (no CUDA toolkit / driver install needed, as
# long as `nvidia-smi` already works on this machine).
#
# Safe to re-run: skips any env that already exists instead of recreating
# it, so you can re-run this after a partial failure (e.g. a network blip
# mid-install) without losing what already installed successfully.
#
# Usage:
#   ./scripts/setup_conda_envs.sh
#
# Then: cp .env.example .env, edit the paths in it (model repo, checkpoint,
# CellMate -- see the comments in that file), set PYTHON_ENV_MANAGER=conda
# in it, and ./scripts/run_all.sh starts everything.

set -euo pipefail
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

echo
echo "======================================================================"
echo "Done. Next steps:"
echo "  1. cp .env.example .env   # then edit the paths in it (see the"
echo "     comments in that file -- model repo, checkpoint, CellMate)"
echo "  2. Add to .env: PYTHON_ENV_MANAGER=conda"
echo "  3. cd frontend && npm install && cd .."
echo "  4. ./scripts/run_all.sh"
echo
echo "GPU check once running (should print True if this machine has one):"
echo "  $CONDA_BASE/envs/yeastpanoptic-sam_service/bin/python3 -c \"import torch; print(torch.cuda.is_available())\""
echo "======================================================================"

#!/usr/bin/env bash
# Clones the two companion repos this project needs -- the yeast panoptic
# model code and the CellMate quantification library -- into external/,
# if they aren't already there. Safe to re-run: skips any repo that's
# already checked out here, so it never clobbers local edits or a Cython
# build you've already done.
#
# Called automatically by scripts/setup_conda_envs.sh and
# scripts/setup_venv_envs.sh -- you don't need to run this by hand unless
# you're doing your own env setup and just want the repos.
#
# Usage:
#   ./scripts/fetch_models.sh

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXTERNAL_DIR="$REPO_ROOT/external"
mkdir -p "$EXTERNAL_DIR"

clone_if_missing() {
  local name="$1" url="$2"
  local dir="$EXTERNAL_DIR/$name"
  if [ -d "$dir/.git" ]; then
    echo "== $name already checked out at external/$name, skipping =="
  else
    echo "== Cloning $name =="
    git clone --depth 1 "$url" "$dir"
  fi
}

clone_if_missing PytrochDeepyeast https://github.com/wanlanli/PytrochDeepyeast.git
clone_if_missing CellMate https://github.com/wanlanli/CellMate.git

echo
echo "PANOPTIC_REPO_PATH=$EXTERNAL_DIR/PytrochDeepyeast"
echo "CELLMATE_PATH=$EXTERNAL_DIR/CellMate"

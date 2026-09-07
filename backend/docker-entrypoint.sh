#!/bin/sh
# If CELLMATE_PATH is mounted in and its Cython extension hasn't been built
# for this container's Python yet, build it now -- automatically, once.
# Safe to run on every container start: skipped if the .so files already
# exist (they persist on the host volume across restarts/rebuilds).
set -e

if [ -n "$CELLMATE_PATH" ] && [ -d "$CELLMATE_PATH/cellmate/image_measure/measure" ]; then
  MEASURE_DIR="$CELLMATE_PATH/cellmate/image_measure/measure"
  if ! ls "$MEASURE_DIR"/_moments_cy*.so > /dev/null 2>&1; then
    echo "Building CellMate's Cython extension for $(python3 --version)..."
    (cd "$MEASURE_DIR" && python3 setup.py build_ext --inplace)
  fi
fi

exec "$@"

#!/usr/bin/env bash
# Stops everything started by scripts/run_all.sh.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$REPO_ROOT/.run/pids.txt"

if [ ! -f "$PIDFILE" ]; then
  echo "No $PIDFILE -- nothing to stop (or it was already cleaned up)."
  exit 0
fi

while IFS=: read -r name pid; do
  [ -z "$pid" ] && continue
  if kill -0 "$pid" 2>/dev/null; then
    echo "Stopping $name (pid $pid)"
    kill "$pid" 2>/dev/null
  else
    echo "$name (pid $pid) already gone"
  fi
done < "$PIDFILE"

rm -f "$PIDFILE"

#!/usr/bin/env bash
#
# Stop the background Gacha Companion service started by start-service.sh
# (or setup.sh). Safe to run when nothing is running.

set -uo pipefail
cd "$(dirname "$0")"

pid=""
[[ -f serve.pid ]] && pid=$(cat serve.pid)
if [[ -z $pid ]] || ! kill -0 "$pid" 2>/dev/null; then
    pid=$(pgrep -f '\.venv/bin/game-companion serve' | head -n 1)
fi
[[ -n $pid ]] || { echo "Gacha Companion is not running."; exit 0; }

kill "$pid" 2>/dev/null || true
for _ in $(seq 1 20); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.25
done
kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null
rm -f serve.pid
echo "Stopped Gacha Companion (pid $pid)."

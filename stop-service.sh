#!/usr/bin/env bash
#
# Stop the background Gacha Companion service started by start-service.sh
# (or setup.sh). Safe to run when nothing is running.

set -uo pipefail
cd "$(dirname "$0")"

# a pid only counts as ours if its command line actually mentions the
# companion — serve.pid survives reboots and pids get recycled
pid_is_ours() {
    [[ -n $1 ]] && [[ -r "/proc/$1/cmdline" ]] \
        && grep -aq 'game.companion' "/proc/$1/cmdline"
}

pid=""
[[ -f serve.pid ]] && pid=$(cat serve.pid)
if [[ -n $pid ]] && ! kill -0 "$pid" 2>/dev/null; then
    pid=""
fi
if [[ -n $pid ]] && ! pid_is_ours "$pid"; then
    echo "stale serve.pid (pid $pid is not Gacha Companion) — ignoring it"
    pid=""
fi
if [[ -z $pid ]]; then
    pid=$(pgrep -f 'game-companion serve|game_companion\.cli serve' | head -n 1)
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

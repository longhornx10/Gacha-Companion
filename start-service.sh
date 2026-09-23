#!/usr/bin/env bash
#
# Start the Gacha Companion service in the background.
# Appends to serve.log in this folder; PID is saved to serve.pid.
# Does nothing if the service is already answering on its port.

set -uo pipefail
cd "$(dirname "$0")"

port=${GAME_COMPANION_PORT:-$(grep -m1 '^GAME_COMPANION_PORT=' .env 2>/dev/null | cut -d= -f2-)}
port=${port:-8765}
health="http://127.0.0.1:${port}/health"

# -f: an HTTP error (e.g. 404 from some other process on the port) must not
# read as "already running" — only a genuine 200 counts.
if curl -s -f -m 2 "$health" >/dev/null 2>&1; then
    echo "Gacha Companion is already running at $health"
    exit 0
fi

if [[ ! -x .venv/bin/game-companion ]]; then
    echo "No .venv found — run:  bash setup.sh" >&2
    exit 1
fi

nohup .venv/bin/game-companion serve >> serve.log 2>&1 &
echo $! > serve.pid

for _ in $(seq 1 60); do
    if curl -s -f -m 1 "$health" >/dev/null 2>&1; then
        echo "Gacha Companion is running at $health  (pid $(cat serve.pid), log: serve.log)"
        exit 0
    fi
    if ! kill -0 "$(cat serve.pid)" 2>/dev/null; then
        echo "Service exited during startup — last log lines:" >&2
        tail -n 8 serve.log >&2
        exit 1
    fi
    sleep 0.25
done

echo "Service did not become healthy within 15s — last log lines:" >&2
tail -n 8 serve.log >&2
exit 1

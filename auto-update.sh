#!/usr/bin/env bash
#
# Gacha Companion — automatic updater. Safe to run unattended (systemd timer
# or cron): pulls the latest code, reinstalls, restarts the service when
# anything changed, ROLLS BACK if the new version won't start, and relaunches
# the service if it ever stopped. Everything lands in update.log.
#
# Manual use:  bash auto-update.sh

set -uo pipefail
cd "$(dirname "$0")"

LOG=update.log
say() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"; }

port=${GAME_COMPANION_PORT:-$(grep -m1 '^GAME_COMPANION_PORT=' .env 2>/dev/null | cut -d= -f2-)}
port=${port:-8765}
health="http://127.0.0.1:${port}/health"

say "── update check start ──"

# housekeeping: update.log is append-only — trim it to its last ~64KB monthly-ish
if [[ -f $LOG ]] && (( $(stat -c%s "$LOG") > 65536 )); then
    tail -c 32768 "$LOG" > "$LOG.tmp" && mv -f "$LOG.tmp" "$LOG"
fi

[[ -x .venv/bin/game-companion ]] || { say "not installed yet (no .venv) — run setup.sh first; skipping"; exit 0; }
command -v git >/dev/null 2>&1 || { say "git is missing — skipping"; exit 0; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { say "not a git checkout — skipping"; exit 0; }

if ! git fetch origin --quiet 2>>"$LOG"; then
    say "could not reach the update server (offline?) — skipping"
    exit 0
fi

branch=$(git rev-parse --abbrev-ref HEAD)
upstream="origin/${branch:-main}"
if ! git rev-parse --verify --quiet "$upstream" >/dev/null 2>&1; then
    say "no upstream branch $upstream — skipping"
    exit 0
fi

behind=$(git rev-list --count HEAD.."$upstream")
dirty=$(git status --porcelain | grep -v '^??' || true)

uv=$(command -v uv || true)
[[ -n $uv && -x $uv ]] || uv="$HOME/.local/bin/uv"
if [[ ! -x $uv ]]; then
    say "uv missing — installing it"
    curl -LsSf https://astral.sh/uv/install.sh | sh >>"$LOG" 2>&1
    uv="$HOME/.local/bin/uv"
fi
install_deps() { "$uv" pip install --python .venv/bin/python -e ".[dev]" >>"$LOG" 2>&1; }

if (( behind == 0 )); then
    if [[ -n $dirty ]]; then
        say "up to date at $(git rev-parse --short HEAD) (your local changes were left untouched)"
    else
        say "up to date at $(git rev-parse --short HEAD)"
    fi
else
    if [[ -n $dirty ]]; then
        say "$behind update(s) available, but this folder has local changes — skipping to be safe (fix: git stash, then re-run)"
        exit 0
    fi

    old=$(git rev-parse --short HEAD)
    say "$behind update(s) available — updating from $old…"
    if ! git pull --ff-only >>"$LOG" 2>&1; then
        say "git pull failed — keeping the current version"
        exit 0
    fi
    if ! install_deps; then
        say "installing the new version failed — rolling back to $old"
        git reset --hard "$old" >>"$LOG" 2>&1
        install_deps
        say "rollback complete — still running $old"
        exit 0
    fi

    say "restarting the service…"
    bash stop-service.sh >>"$LOG" 2>&1
    # snapshot the database while the service is down: if the new version
    # migrates the schema and then fails to start, rolling back the code alone
    # would leave old code on a newer schema (permanently unstartable)
    dbdir=${GAME_COMPANION_DATA_DIR:-$(grep -m1 '^GAME_COMPANION_DATA_DIR=' .env 2>/dev/null | cut -d= -f2- | tr -d '"')}
    dbdir=${dbdir:-$HOME/.local/share/gacha-companion}
    dbdir=${dbdir/#\~/$HOME}
    snapshot=""
    [[ -f $dbdir/gacha_companion.db ]] && { snapshot="$dbdir/gacha_companion.db.pre-update"; cp "$dbdir/gacha_companion.db" "$snapshot"; }
    if ! bash start-service.sh >>"$LOG" 2>&1; then
        say "the new version did not start — rolling back to $old"
        git reset --hard "$old" >>"$LOG" 2>&1
        install_deps
        if [[ -n $snapshot && -f $snapshot ]]; then
            cp "$snapshot" "$dbdir/gacha_companion.db"
            rm -f "$dbdir/gacha_companion.db-wal" "$dbdir/gacha_companion.db-shm"
            say "database restored to its pre-update schema"
        fi
        bash stop-service.sh >>"$LOG" 2>&1
        if bash start-service.sh >>"$LOG" 2>&1; then
            say "rollback complete — running $old again (the broken update was reported in the log above)"
        else
            say "ROLLBACK FAILED TOO — please run: bash setup.sh   (see serve.log)"
        fi
        exit 0
    fi
    [[ -n $snapshot ]] && rm -f "$snapshot"
    # refresh the desktop launchers so they always match the current layout
    if python3 setup-gui.py --shortcuts >>"$LOG" 2>&1; then
        say "desktop launchers refreshed"
    fi
    say "updated to $(git rev-parse --short HEAD) — service healthy at $health"
fi

# watchdog: whatever happened above, make sure the companion is running
if ! curl -s -f -m 3 "$health" >/dev/null 2>&1; then
    say "service was down — starting it"
    if bash start-service.sh >>"$LOG" 2>&1; then
        say "service started"
    else
        say "could not start the service — see serve.log"
    fi
fi
say "── update check done ──"

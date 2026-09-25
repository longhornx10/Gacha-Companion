#!/usr/bin/env bash
#
# Gacha Companion — guided setup.
#
#     cd Gacha-Companion && bash setup.sh
#
# Safe to re-run any time: each step checks existing state first, and
# existing files (.env, player profiles, a running service) are kept unless
# you choose to change them.

set -uo pipefail

# ----------------------------------------------------------------- pretty I/O

if [[ -t 1 && ${TERM:-} != dumb ]]; then
    RESET=$'\e[0m'; BOLD=$'\e[1m'; DIM=$'\e[2m'
    CYAN=$'\e[36m'; GREEN=$'\e[32m'; YELLOW=$'\e[33m'; RED=$'\e[31m'
else
    RESET=""; BOLD=""; DIM=""; CYAN=""; GREEN=""; YELLOW=""; RED=""
fi

REPO_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$REPO_DIR"

# Diagnostic report: works everywhere, no browser needed, prints clean text.
if [[ ${1:-} == "--report" ]]; then
    exec python3 setup-gui.py --report
fi

step_n=0
step()  { step_n=$((step_n + 1)); printf '\n%s── [%s] %s ──%s\n' "$CYAN$BOLD" "$step_n" "$*" "$RESET"; }
hr()    { printf '%s%s%s\n' "$DIM" "$(printf '%.0s─' $(seq 1 64))" "$RESET"; }
ok()    { printf '  %s✓%s %s\n' "$GREEN" "$RESET" "$*"; }
note()  { printf '  %s%s%s\n' "$DIM" "$*" "$RESET"; }
warn()  { printf '  %s!%s %s\n' "$YELLOW" "$RESET" "$*"; }
die()   { printf '\n%s✗ %s%s\n\n' "$RED$BOLD" "$*" "$RESET" >&2; exit 1; }

ask() {  # ask VAR "prompt" "default"  — empty answer takes the default
    local __var=$1 __prompt=$2 __def=${3:-} __ans=""
    if [[ -n $__def ]]; then
        printf '  %s %s[%s]%s: ' "$__prompt" "$DIM" "$__def" "$RESET"
    else
        printf '  %s: ' "$__prompt"
    fi
    IFS= read -r __ans || true
    __ans=${__ans%$'\r'}
    printf -v "$__var" '%s' "${__ans:-$__def}"
}

ask_secret() {  # ask_secret VAR "prompt" — typed input is not echoed
    local __var=$1 __prompt=$2 __ans=""
    printf '%s' "$__prompt"
    IFS= read -rs __ans || true
    __ans=${__ans%$'\r'}
    printf '\n'
    printf -v "$__var" '%s' "$__ans"
}

ask_yn() {  # ask_yn "prompt" y|n  → returns 0 for yes
    local __prompt=$1 __def=${2:-y} __ans=""
    if [[ $__def == y ]]; then
        printf '  %s %s[Y/n]%s: ' "$__prompt" "$DIM" "$RESET"
    else
        printf '  %s %s[y/N]%s: ' "$__prompt" "$DIM" "$RESET"
    fi
    IFS= read -r __ans || true
    __ans=${__ans%$'\r'}
    [[ ${__ans:-$__def} =~ ^[Yy] ]]
}

env_key() {  # env_key FILE KEY → value of KEY= line, empty if absent
    [[ -f $1 ]] && grep -m1 "^$2=" "$1" | cut -d= -f2- || true
}

service_port() {
    local p=${GAME_COMPANION_PORT:-$(env_key .env GAME_COMPANION_PORT)}
    echo "${p:-8765}"
}

TMPDIR_SETUP=$(mktemp -d)
trap 'rm -rf "$TMPDIR_SETUP"' EXIT
trap 'printf "\n%sInterrupted — re-run bash setup.sh any time; finished steps are kept.%s\n" "$YELLOW" "$RESET"; exit 130' INT

printf '%s\n' "${BOLD}${CYAN}"
cat <<'BANNER'
══════════════════════════════════════════════════════════════
     ✦  GACHA COMPANION — GUIDED SETUP  ✦
══════════════════════════════════════════════════════════════
BANNER
printf '%s\n' "$RESET"
note "This script checks prerequisites, installs everything, asks a few"
note "questions, starts the service, and tells you the one step left in"
note "Open WebUI. Re-run it any time — nothing is done twice."

# Graphical wizard: with a desktop session, open the browser wizard straight
# away — no questions. Terminal mode: bash setup.sh --cli
if [[ ${1:-} != "--cli" && ( -n ${DISPLAY:-} || -n ${WAYLAND_DISPLAY:-} ) ]] \
   && command -v python3 >/dev/null 2>&1 && [[ -f setup-gui.py ]]; then
    note "opening the setup wizard in your browser… (for terminal mode run: bash setup.sh --cli)"
    exec python3 setup-gui.py
fi

# ---------------------------------------------------------------- 1. basics

hr
step "Checking prerequisites"
[[ -f pyproject.toml && -d game_companion ]] || die "run me from inside the Gacha-Companion folder:  cd Gacha-Companion && bash setup.sh"
command -v git  >/dev/null 2>&1 || die "git is missing — install it first (e.g. 'sudo apt install git'), then re-run."
command -v curl >/dev/null 2>&1 || die "curl is missing — install it first (e.g. 'sudo apt install curl'), then re-run."
[[ $(uname -s) == Linux ]] || warn "This project targets Linux; continuing anyway."
ok "git and curl present"

# ---------------------------------------------------------------- 2. uv

step "Python tooling (uv)"
UV_BIN=""
if command -v uv >/dev/null 2>&1; then
    UV_BIN=$(command -v uv)
elif [[ -x "$HOME/.local/bin/uv" ]]; then
    UV_BIN="$HOME/.local/bin/uv"
fi
if [[ -z $UV_BIN ]]; then
    note "uv not found — installing it (official installer, to ~/.local/bin)…"
    curl -LsSf https://astral.sh/uv/install.sh | sh \
        || die "could not install uv — install it manually from https://docs.astral.sh/uv/, then re-run."
    [[ -x "$HOME/.local/bin/uv" ]] || die "uv was installed but not found at ~/.local/bin/uv — open a new terminal and re-run."
    UV_BIN="$HOME/.local/bin/uv"
fi
ok "uv $("$UV_BIN" --version | awk '{print $2}')"

# ---------------------------------------------------------------- 3. code

step "Updating the code"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if pull_out=$(git pull --ff-only 2>&1); then
        ok "git: ${pull_out}"
    else
        warn "skipped git pull ($pull_out) — continuing with the local copy"
    fi
else
    warn "not a git checkout — skipping update"
fi

# ---------------------------------------------------------------- 4. env+deps

step "Python environment and dependencies"
if [[ ! -x .venv/bin/python ]]; then
    "$UV_BIN" venv --python 3.12 || die "could not create the .venv (see message above)"
fi
"$UV_BIN" pip install --python .venv/bin/python -e ".[dev]" --quiet \
    || "$UV_BIN" pip install --python .venv/bin/python -e ".[dev]" \
    || die "dependency installation failed — see the output above"
ok "installed into .venv (30-ish packages)"
GC=.venv/bin/game-companion
[[ -x $GC ]] || die "game-companion entry point missing from .venv — installation went wrong; re-run"
if games=$("$GC" list-games 2>&1); then
    while IFS= read -r g; do ok "adapter: $g"; done <<< "$games"
else
    die "sanity check failed: $games"
fi

# ---------------------------------------------------------------- 5. .env

step "LLM endpoint configuration (.env)"
ENV_FILE=.env
have_base=$(env_key "$ENV_FILE" GAME_COMPANION_LLM_BASE_URL)
have_model=$(env_key "$ENV_FILE" GAME_COMPANION_LLM_MODEL)
have_key=$(env_key "$ENV_FILE" GAME_COMPANION_LLM_API_KEY)

reconfig=y
if [[ -f $ENV_FILE ]]; then
    note "current .env:"
    note "  base URL:  ${have_base:-<unset>}"
    note "  model:     ${have_model:-<unset>}"
    if [[ -n $have_key ]]; then note "  API key:   set"; else note "  API key:   NOT set"; fi
    note "  (the API key is never shown or committed)"
    ask_yn "Change these settings?" n && reconfig=y || reconfig=n
fi

if [[ $reconfig == y ]]; then
    ask LLM_BASE  "LLM base URL (OpenAI-compatible, the companion service calls this)" "${have_base:-https://llm.tictac.one/v1}"
    ask LLM_MODEL "model name" "${have_model:-muse-glimmer-30b-vlm-128k}"
    ask_secret LLM_KEY "  API key (input hidden, Enter to keep current): "
    [[ -n $LLM_KEY ]] || LLM_KEY=$have_key   # empty answer keeps the existing key
    [[ -n $LLM_KEY ]] || warn "no API key set — screenshot extraction / tutor / research will return 503 until you add one (re-run setup.sh)"

    if [[ -f $ENV_FILE ]]; then
        cp "$ENV_FILE" "$ENV_FILE.backup.$(date +%Y%m%d-%H%M%S)"
        note "existing .env backed up"
    elif [[ -f .env.example ]]; then
        cp .env.example "$ENV_FILE"
    fi

    # values pass through the environment (not argv) so the key is never
    # visible in `ps` / /proc/*/cmdline to other local users
    GC_ENV_FILE="$ENV_FILE" GC_W_BASE="$LLM_BASE" GC_W_MODEL="$LLM_MODEL" GC_W_KEY="$LLM_KEY" \
        .venv/bin/python - <<'PYEOF' || die "could not write .env"
import os, re, sys, pathlib
path = pathlib.Path(os.environ["GC_ENV_FILE"])
pairs = {
    "GAME_COMPANION_LLM_BASE_URL": os.environ["GC_W_BASE"],
    "GAME_COMPANION_LLM_MODEL": os.environ["GC_W_MODEL"],
    "GAME_COMPANION_LLM_API_KEY": os.environ["GC_W_KEY"],
}
text = path.read_text() if path.exists() else ""
for key, val in pairs.items():
    line = f"{key}={val}"
    if re.search(rf"(?m)^{key}=", text):
        text = re.sub(rf"(?m)^{key}=.*$", lambda _m: line, text)
    else:
        text = (text.rstrip("\n") + "\n" if text else "") + line + "\n"
path.write_text(text)
PYEOF
    chmod 600 "$ENV_FILE"
    have_base=$LLM_BASE; have_model=$LLM_MODEL; [[ -n $LLM_KEY ]] && have_key=$LLM_KEY
    ok ".env written (permissions 600, listed in .gitignore — it stays local)"
else
    ok "keeping existing .env"
fi

if [[ -n $have_key ]]; then
    if ask_yn "Test the LLM endpoint now? (one small request)" y; then
        hdr="$TMPDIR_SETUP/hdr"; printf 'Authorization: Bearer %s\n' "$have_key" > "$hdr"; chmod 600 "$hdr"
        code=$(curl -s -m 12 -o /dev/null -w '%{http_code}' -H "@$hdr" "$have_base/models" 2>/dev/null || echo 000)
        case $code in
            2*) ok "endpoint reachable (HTTP $code)";;
            401|403) warn "endpoint reachable but rejected the API key (HTTP $code) — check the key";;
            000) warn "could not reach $have_base — check the URL / network (you can continue)";;
            *) note "endpoint answered HTTP $code (not fatal; /models may be disabled)";;
        esac
    fi
fi

# ---------------------------------------------------------------- 6. player

step "Player profile"
PLAYER_ID=""; PLAYER_NAME=""
db_out=$("$GC" init-db 2>&1) || warn "database init reported: $db_out"
mapfile -t players < <(.venv/bin/python - <<'PYEOF' 2>/dev/null
from game_companion.config import get_settings
from game_companion.db.session import create_db_engine, create_session_factory
from game_companion.db.repositories import PlayerRepository
engine = create_db_engine(get_settings().resolved_database_url)
session = create_session_factory(engine)()
try:
    for p in PlayerRepository(session).list_all():
        print(f"{p.id}\t{p.display_name}")
finally:
    session.close()
    engine.dispose()
PYEOF
)
if ((${#players[@]})); then
    note "existing profile(s):"
    for p in "${players[@]}"; do
        IFS=$'\t' read -r pid pname <<< "$p"
        note "  $pname  ($pid)"
    done
    if ask_yn "Create another profile?" n; then
        ask NEW_NAME "display name" "$(whoami)"
        out=$("$GC" create-player "$NEW_NAME" 2>&1) || die "create-player failed: $out"
        PLAYER_ID=$(printf '%s' "$out" | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
        PLAYER_NAME=$NEW_NAME
        ok "created profile '$NEW_NAME'"
    else
        IFS=$'\t' read -r PLAYER_ID PLAYER_NAME <<< "${players[0]}"
        ok "using existing profile '$PLAYER_NAME'"
    fi
else
    ask NEW_NAME "No profile yet — pick a display name (used in Open WebUI later)" "$(whoami)"
    out=$("$GC" create-player "$NEW_NAME" 2>&1) || die "create-player failed: $out"
    PLAYER_ID=$(printf '%s' "$out" | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
    PLAYER_NAME=$NEW_NAME
    ok "created profile '$NEW_NAME'"
fi
note "player id: $PLAYER_ID  (you'll paste this into the Open WebUI tool)"

# ---------------------------------------------------------------- 7. service

step "Local service"
PORT=$(service_port)
HEALTH="http://127.0.0.1:$PORT/health"
SERVICE_STATE="running"
if body=$(curl -s -f -m 3 "$HEALTH"); then
    ok "already running — $body"
else
    if ask_yn "Start the service now (background, logs to serve.log)?" y; then
        bash "$REPO_DIR/start-service.sh" || die "service did not start — last log lines:
$(tail -n 8 serve.log 2>/dev/null)"
        ok "running at $HEALTH"
    else
        SERVICE_STATE="stopped"
        warn "skipped — start it later with:  bash start-service.sh"
    fi
fi

# ---------------------------------------------------------------- 8. summary

DATA_DIR=${GAME_COMPANION_DATA_DIR:-$(env_key .env GAME_COMPANION_DATA_DIR)}
DATA_DIR=${DATA_DIR:-$HOME/.local/share/gacha-companion}
TOOLFILE="$REPO_DIR/game_companion/integrations/openwebui/gacha_companion_tools.py"

hr
printf '\n%s%sSETUP COMPLETE%s — here is everything you need:\n\n' "$BOLD$GREEN" "" "$RESET"

print_box() {
    local lines=("$@") w=0 l
    for l in "${lines[@]}"; do ((${#l} > w)) && w=${#l}; done
    local bar; bar=$(printf '%*s' $((w + 2)) '' | tr ' ' '-')
    printf '  +%s+\n' "$bar"
    for l in "${lines[@]}"; do printf '  | %-*s |\n' "$w" "$l"; done
    printf '  +%s+\n' "$bar"
}
print_box \
    "service    : http://127.0.0.1:$PORT  ($SERVICE_STATE)" \
    "player     : $PLAYER_NAME" \
    "player id  : $PLAYER_ID" \
    "data       : $DATA_DIR" \
    "service log: $REPO_DIR/serve.log   (tail -f $REPO_DIR/serve.log)" \
    "stop/start : bash $REPO_DIR/stop-service.sh | start-service.sh"

printf '\n%s%sONE STEP LEFT — connect Open WebUI Desktop (5 minutes, GUI only)%s\n' "$BOLD$CYAN" "" "$RESET"
cat <<EOF
  1. Open WebUI → Settings → Admin Settings → Connections → OpenAI API:
     add ${have_base:-https://llm.tictac.one/v1} with your API key,
     then pick ${have_model:-muse-glimmer-30b-vlm-128k} as the chat model.
  2. Open WebUI → Workspace → Tools → "+": paste the entire contents of
     $TOOLFILE
  3. Tool → Valves (gear icon):
     base_url = http://127.0.0.1:$PORT
     game_id  = zzz
     player_id= $PLAYER_ID
  4. In a new chat: "+" next to the message box → Tools → enable
     "Gacha Companion", then try:
     "I own Burnice, Ellen and Lycaon."
EOF

printf '\n'
ok "re-run bash setup.sh any time (updates code, reuses your data)"
printf '\n'

# Getting Started: 0 → 100

From a bare Linux machine to daily use with the companion's own app. Everything
here matches the code on `main`. See [architecture.md](architecture.md) for
design details. Open WebUI is **optional** — see [openwebui.md](openwebui.md).

## 0. The easy way: setup wizard

```bash
git clone https://github.com/longhornx10/Gacha-Companion.git
bash ~/Gacha-Companion/setup.sh
```

On a desktop, this opens a **wizard in your browser**: two boxes (secret key +
your name), one big "Start setup" button, and an animated checklist that
installs everything, saves settings, creates your profile, and starts the
service. It auto-detects what's already done (existing settings, profiles, a
running service, even a local Open WebUI — and the model list straight from
the LLM endpoint), skips itself straight to the done screen when everything is
ready, and ends with four copy-paste cards for the Open WebUI hookup plus an
optional desktop icon so you never need the terminal again. Manual,
step-by-step controls live under "Manual controls" at the bottom of the page.

No desktop/browser (`--cli`) or over SSH? `setup.sh` falls back to the same
flow in the terminal, and `bash stop-service.sh` / `bash start-service.sh`
manage the background service afterwards.

After setup, the **"Gacha Companion" desktop app** (added by the wizard's
"Add desktop icons" button) opens a small control panel: check/apply updates,
start/stop the service, peek at logs, open the data folder, and copy a
secrets-redacted problem report — the same report as `bash setup.sh --report`
in a terminal.

The rest of this document explains each step manually — useful when something
needs fixing or you want to understand the moving parts.

## 1. Prerequisites (one-time)

```bash
# git + python are usually already there; install uv (fast Python manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

You need Linux, Python 3.12+ (3.12 recommended — it's what the project is
tested on), and roughly 100 MB of disk. The service only ever talks to
`127.0.0.1` — nothing is exposed to your network.

## 2. Clone and install

```bash
git clone https://github.com/longhornx10/Gacha-Companion.git
cd Gacha-Companion

uv venv --python 3.12
uv pip install -e ".[dev]"
```

(Plain-venv alternative:
`python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`.)

Sanity check:

```bash
uv run game-companion list-games
# example  Aether Tactics (Example) (Vanguard, Sigil, Charm, team 4-4)
# zzz      Zenless Zone Zero (Agent, W-Engine, Drive Disc, team 3-3)
```

## 3. Configure

```bash
cp .env.example .env
```

Edit `.env` — three lines matter:

```ini
GAME_COMPANION_LLM_BASE_URL=https://llm.tictac.one/v1
GAME_COMPANION_LLM_API_KEY=<your key>
GAME_COMPANION_LLM_MODEL=muse-glimmer-30b-vlm-128k
```

Notes:

- The `.env` file is read from the directory you launch from — run everything
  from the repo root (or export the vars in your shell instead).
- This endpoint is what the **companion service** uses for screenshot
  extraction, research, and tutoring. It is separate from what Open WebUI
  chats with (step 5). The key never leaves the service and is scrubbed from
  logs.
- Everything else (host, port 8765, data dir) has good defaults. Data lives in
  `~/.local/share/gacha-companion/` (SQLite DB + exports + personas).

## 4. First run

```bash
uv run game-companion serve
```

This creates and migrates the SQLite DB automatically, then serves at
`http://127.0.0.1:8765`. Verify in another terminal:

```bash
curl -s http://127.0.0.1:8765/health
# {"status":"ok","service":"gacha-companion"}
curl -s http://127.0.0.1:8765/api/health
# {"status":"ok","service":"gacha-companion","games":["example","zzz"]}
```

Create your player profile and copy the `id` it prints:

```bash
uv run game-companion create-player "Nick"
# {"id":"a1b2c3...","display_name":"Nick"}
```

Leave `serve` running — it's a normal foreground process; put it in a tmux
window or a systemd user unit if you want it persistent.

## 5. Open your companion (the app)

The companion has its own interface now — no Open WebUI needed:

```bash
game-companion app        # app-style window (chromium --app); falls back to your browser
```

or just open **<http://127.0.0.1:8765/ui>**. What's inside:

- **Dashboard** — counts, active team, resource statuses, recent results.
- **Imports** — paste your roster as text or upload a screenshot; review the
  proposed changes, then **Apply**. Nothing is saved before you confirm.
- **Roster / Inventory / Teams / Resources / Codes** — read views with inline
  **Edit** buttons; saving marks the data as verified by you.
- **Chat** — talk to your companion. It reads your real data through tools,
  shows which tools it used, and can propose lasting "memories" (visible and
  deletable under **Settings**).
- **Personas** — tone-only characters, optionally bound to a game.
- **Settings** — profiles, backups (create/restore), memories, games.
- **Game switcher** (top header) — switch everything at once: theme, persona,
  chats and data follow the game.

> Prefer Open WebUI? It still works — see [openwebui.md](openwebui.md) for the
> tool setup (this is now the optional path).

## 6. Using it (the fun part)

Open the **Chat** page (or, if you use the optional Open WebUI path, enable the
tool there) and talk normally — the model calls the tools to read/write your
real data before answering.

**Store your account:**

> "I own Burnice, Ellen, Lycaon, Lucy, Anby, Koleda, Grace, Qingyi, Soukaku,
> and Rina. Burnice is level 60, Mindscape 1, and her basic attack is 12."

This hits `list_characters` / `update_character`. Then:
> "My Burnice is now Mindscape 2."

**Authoritative reads (the core promise):** start a *brand-new* chat (no
memory of the above) and ask:
> "What is my Burnice running?"

The model calls `get_character` and answers from stored SQLite state, not from
guesses.

**Account-aware advice:**

> "Who should my Burnice partner with?"
> "What should I farm next?"
> "Which of my discs should I keep?"

These trigger `recommend_teams`, `get_upgrade_plan`,
`evaluate_gear_inventory` — all deterministic scoring with visible HEURISTIC
components and written reasons.

**Teams:**

> "Save a team called Fire Crew with Burnice, Lighter, and Lucy, and make it
> active."

Activation enforces the real game constraint — a character already on another
*active* team gets rejected with an explanation.

**Codes — just type:**

> `#CODES`

Returns tracked codes; used ones render struck through (`~~CODE~~`), recycled
ones come back flagged. After redeeming: "mark ZZZFREE100 as used."

**Record results:**

> "Deadly Assault slot 1 cleared with 3 stars using Fire Crew."
> "How's my win rate looking?"

## 7. Screenshots (vision ingestion)

The golden rule: **extraction never writes to your DB — you confirm first.**
Currently this goes through the API (from a terminal):

```bash
IMG=$(base64 -w0 burnice_overview.png)

curl -s -X POST http://127.0.0.1:8765/api/games/zzz/imports \
  -H 'Content-Type: application/json' \
  -d "{\"screen_type\":\"character_overview\",\"image_base64\":\"$IMG\",\"character_hint\":\"burnice\"}"
```

The response contains a proposed change set (`diff`) and an `import_id`.
Review it, then:

```bash
curl -s -X POST http://127.0.0.1:8765/api/games/zzz/imports/<import_id>/confirm
# or /reject
```

`screen_type` options for ZZZ: `character_overview`, `skills`, `equipment`
(W-Engine), `gear_detail` (single Drive Disc — the best one, it captures
substats), `gear_list` (informational only), `resources`. Unreadable values
come back as `null`, never guessed. Only `character_overview`, `skills`,
`equipment`, and `gear_detail` produce applicable changes.

## 8. Human-readable exports & backups

```bash
uv run game-companion export --game zzz
```

Writes to `~/.local/share/gacha-companion/exports/zzz/`: `account.json` plus
`roster.md`, `teams.md`, `resources.md`, `codes.md`, `gear.md`, `training.md`,
`history.md` — regenerable any time, safe to read while the service runs.

**Backup** = copy `~/.local/share/gacha-companion/` (it's just SQLite +
files). **Reset** = delete that folder.

## 9. Updates and maintenance

**Automatic (recommended):** the setup wizard's done screen has a
**"Turn on automatic updates"** button — one click installs a daily systemd
user timer that runs `auto-update.sh`: it pulls the latest code, reinstalls,
restarts the service when anything changed, rolls back automatically if an
update refuses to start, and relaunches the service if it ever stopped. All
activity lands in `update.log` in the repo folder. Turn it off the same way.

**Manual:**

```bash
bash auto-update.sh        # same logic, on demand — or simply:
git pull
uv pip install -e ".[dev]"
# restart serve; the DB migrates automatically if the schema changed
```

Optional: `uv run game-companion check-sources --game zzz` fetches the trusted
ZZZ sources, records any content changes as pending `change_records` for your
review, and is meant to be run periodically (e.g., a weekly systemd user
timer).

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| Tool replies "service unreachable" | `serve` isn't running, or wrong `base_url` valve |
| 404 "no unique player profile" | You have 2+ profiles — paste your player UUID into the tool's `player_id` valve |
| 503 "LLM endpoint is not configured" on tutor/research/screenshots | `.env` not set or you launched `serve` from a different directory; keys weren't loaded |
| Tools don't fire in chat | Tool not toggled on for that chat, or the chat model doesn't support function calling — switch models |
| Screenshot import status `"failed"` | Extraction couldn't produce valid JSON; the record keeps the error — retry with a cleaner crop, or pass a manual `candidate` instead of an image |
| Auto-update says "local changes — skipping" | You edited tracked files in the repo — `git stash` (or commit) them, then re-run `bash auto-update.sh` |
| An update was rolled back automatically | The new version wouldn't start; you're running the previous commit (see `update.log`) — check in with whoever publishes updates |
| "cannot activate team …" | A character is on another active team — deactivate that one first, that's by design |
| **Hand a full diagnostic back for help** | `bash setup.sh --report` — prints a complete, secrets-redacted report (logs, versions, settings, disk) to copy-paste. The "Gacha Companion" desktop app has the same button plus a live log viewer. |
| Everything else | `GET /health`, then check the terminal running `serve` (logs are human-readable; keys are redacted) |

**Data-honesty caveat:** ZZZ static data in the adapter (agent
attributes/factions, level caps, set names) is hand-curated starter data, and
resource requirement numbers ship as unknown — statuses will say `unknown`
until real numbers are filled in. Scoring is always labeled HEURISTIC with its
reasons visible; nothing pretends to be simulated DPS.

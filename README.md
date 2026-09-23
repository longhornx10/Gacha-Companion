# Gacha Companion

A local-first, **game-agnostic** framework for persistent, account-aware gacha game
companions — a companion that knows *your* account, not just facts about the game.

- **Game-agnostic core.** ZZZ concepts (Agents, W-Engines, Drive Discs, Mindscapes…) live in a
  ZZZ game adapter; the core only understands generic concepts (characters, equipment, gear,
  teams, resources…). Honkai: Star Rail, NTE, and other games plug in as adapters.
- **The LLM is not the database.** Authoritative account state lives in local SQLite behind
  deterministic application code. The LLM converses, explains, researches, and proposes —
  it never silently owns your data.
- **Local and inspectable.** Single-user local service bound to `127.0.0.1`, SQLite storage,
  regenerable JSON + Markdown exports.

## Quick start (Linux)

```bash
git clone https://github.com/longhornx10/Gacha-Companion.git
bash ~/Gacha-Companion/setup.sh
```

That's it — `setup.sh` opens a **setup wizard in your browser** (one big
button, plain language, checks everything as it goes). If no browser is
available it falls back to a terminal guide (`bash setup.sh --cli` forces it).
The wizard can also add a desktop icon so future runs need no terminal at all.
It's safe to re-run any time; `bash stop-service.sh` / `bash start-service.sh`
manage the background service.

Prefer doing it by hand?

```bash
# 1. Create the environment and install
uv venv --python 3.12
uv pip install -e ".[dev]"

# 2. Configure (optional; defaults work out of the box)
cp .env.example .env   # then edit: API key, model, etc.

# 3. Start the local service (creates/migrates the SQLite DB automatically)
uv run game-companion serve          # http://127.0.0.1:8765

# 4. Export your account data to readable files
uv run game-companion export --game zzz
```

Other CLI commands: `list-games`, `create-player`, `init-db`, `check-sources`.

## Documentation

| Doc | Contents |
| --- | --- |
| [docs/getting-started.md](docs/getting-started.md) | **start here** — install → Open WebUI → daily use |
| [docs/SPEC.md](docs/SPEC.md) | full product specification |
| [docs/architecture.md](docs/architecture.md) | design, layering rules, decision log |
| [docs/data-model.md](docs/data-model.md) | every table, integrity rules |
| [docs/game-adapter.md](docs/game-adapter.md) | how to add HSR/NTE as a new adapter |
| [docs/openwebui.md](docs/openwebui.md) | connecting Open WebUI tools |
| [docs/zzz.md](docs/zzz.md) | ZZZ adapter rules, data honesty notes |
| [docs/TODO.md](docs/TODO.md) | milestone tracker / current status |

## Development

```bash
uv run pytest tests                      # 89 tests; fully offline (no API calls)
uv run ruff check game_companion tests   # lint
```

See `docs/architecture.md` for the design, [docs/getting-started.md](docs/getting-started.md)
for the full 0→100 walkthrough (clone → configure → Open WebUI → daily use),
and `docs/game-adapter.md` to add a new game.

## Status

See `docs/TODO.md` for the milestone tracker (foundation → first useful release →
advanced milestones).

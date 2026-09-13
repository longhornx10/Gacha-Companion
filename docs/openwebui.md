# Open WebUI Integration

Gacha Companion ships a thin Open WebUI **Tools** file:
`game_companion/integrations/openwebui/gacha_companion_tools.py`.

It contains no business logic. Every tool is a small HTTP call to the local
service; all state lives in the companion's SQLite database.

## Setup

1. Start the companion service:

   ```bash
   uv run game-companion serve     # http://127.0.0.1:8765
   ```

2. Configure the LLM endpoint (used by the service, not by Open WebUI, for
   tutoring / research / screenshot extraction): set `GAME_COMPANION_LLM_*`
   variables (see `.env.example`).

3. In Open WebUI: **Workspace → Tools → +** (or Settings → Tools) and create a
   new tool by pasting the contents of `gacha_companion_tools.py`.

4. In a chat, enable the **Gacha Companion** tool. Set the valves:
   - `base_url`: `http://127.0.0.1:8765` (default)
   - `game_id`: `zzz` (or another registered game; see `/api/games`)
   - `player_id`: leave empty if you have exactly one player profile — the
     service then resolves it automatically.

## Tool catalog (what the model sees)

| Tool | When the model should call it |
| --- | --- |
| `get_player_profile` | before account-specific answers that need the player identity |
| `list_characters` | ALWAYS before roster/team questions — advice must use the real roster |
| `get_character` / `get_build` | "what is my X running?" — returns stored authoritative build |
| `update_character` / `update_build` | when the user states a change to their account |
| `list_equipment`, `list_gear`, `add_gear`, `favorite_gear` | equipment / gear inventory questions |
| `get_resources`, `update_resource` | resource amounts and deterministic threshold statuses |
| `list_teams`, `save_team` | team storage; activation enforces per-character mutual exclusion |
| `recommend_teams` | "who should X partner with?" — account-aware, from real roster |
| `evaluate_gear_inventory` | "which discs should I keep?" — verdicts with reasons |
| `get_upgrade_plan` | "what should I farm next?" |
| `search_game_sources` | patch-sensitive/meta questions; returns cited claims |
| `get_active_codes`, `mark_code_used` | **`#CODES`** and code questions (used codes render struck through) |
| `record_combat_result`, `get_combat_history` | endgame results and performance trends |
| `record_training_issue`, `get_training_focus` | adapt tutoring to known weaknesses |

Tool descriptions embed the retrieval discipline from the spec: account
questions trigger authoritative lookups *before* the model answers.

## Screenshot ingestion through chat

The REST API accepts screenshot uploads (`POST /api/games/{game}/imports` with
`image_base64`) and returns a **proposed change set** that must be confirmed
(`POST .../imports/{id}/confirm`) before anything is stored. From Open WebUI,
uploading a screenshot to the chat attached to a vision-capable model can be
followed by manual confirmation through the API or the CLI. Raw VLM output is
never applied silently — by design.

## Security notes

- The service binds `127.0.0.1` only by default. Do not expose it to your LAN
  without adding authentication.
- API keys for the LLM endpoint live only in the companion's environment —
  they are never sent to Open WebUI and never logged.

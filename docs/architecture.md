# Gacha Companion — Architecture

Status: living document. Describes what is implemented and why.
The product requirements live in [SPEC.md](SPEC.md); the milestone tracker in [TODO.md](TODO.md).

## 1. Goals

1. A reusable, **game-agnostic** framework for account-aware gacha companions.
   Zenless Zone Zero is only the first adapter; HSR/NTE-style games must fit without
   touching core business logic.
2. **The LLM is not the database.** Authoritative state = local SQLite + deterministic code.
   The LLM converses, explains, researches, extracts candidates — it never silently owns data.
3. Local-first, single Linux desktop user, no distributed infrastructure.

## 2. High-level layout

```
Open WebUI (chat)                      CLI: game-companion serve|export|init-db
      │  OpenAI-compatible tools               │
      ▼                                        ▼
┌────────────────────────────  FastAPI app (127.0.0.1:8765)  ─────────────────────────┐
│  api/routes  ──► api/schemas (pydantic I/O)                                        │
│        │                                                                           │
│        ▼                                                                           │
│  core services (roster, gear, teams, resources, research, coaching, vision,        │
│  recommendations, optimizer, history, codes, exports, persona, llm)                │
│        │ uses rules/hooks from ──►  GameAdapter (per game)                         │
│        │                              ├── games/zzz        (ZZZ specifics)         │
│        │                              └── games/example_game (contract-test game)  │
│        ▼                                                                           │
│  db/repositories ──► SQLAlchemy 2.x models ──► SQLite (authoritative)              │
└─────────────────────────────────────────────────────────────────────────────────────┘
         │                                    │
         ▼                                    ▼
  exports/{game}/*.md|json            integrations/openwebui (thin tool wrapper)
```

Layering rules:

- Route handlers validate I/O and call services; **no domain logic in routes**.
- Services own business rules and call adapters for game-specific facts; **core never
  imports `game_companion.games.*`** (enforced by a test). The only place that maps a game
  id to an adapter module is `core/games/registry.py`, by *string* path, imported lazily.
- Open WebUI integration is a thin file that calls the local REST API; no business logic.
- Exports are regenerated from SQLite; they are never an input to the DB.

## 3. Game adapter contract (summary)

A `GameAdapter` (see `core/games/base.py`) supplies, per game:

| Capability | Purpose |
| --- | --- |
| `game_id`, `display_name`, terminology nouns | Character/equipment/gear/duplication naming per game |
| `stat_definitions`, `skill_definitions` | Canonical stat & skill keys, display names, kinds |
| `team_rules` | Team size min/max, team compatibility/synergy hooks |
| `gear_rules` | Gear slots, main-stat pools, set metadata, gear scoring hook |
| `equipment_rules` | Equipment (weapon-like) semantics & comparison hook |
| `progression_rules` | Skill keys, level caps, ascension stages |
| `resource_rules` | Resource categories + threshold config for status evaluation |
| `encounter_rules` | Endgame modes, slot constraints (e.g. 3 Deadly Assault slots) |
| `source_registry` | Trusted research sources w/ category + trust |
| `screenshot_specs` | Typed extraction schemas + per-screen VLM prompt fragments |
| `code_config` | Redeem-code discovery guidance, markdown rendering |
| validation hooks | Game-specific validation of flexible `data` JSON |
| scoring hooks | Gear evaluation, team scoring components (labeled HEURISTIC) |

Adding a game = adding a package under `games/<id>/` with a manifest + adapter module and
registering it in the registry map (one string entry). Core code is untouched.
`games/example_game` (game id `example`) is a deliberately different-shaped game (team size 4,
2 gear slots, different stats/skills/resources) used by the adapter-contract test suite to
prove core genericity.

ZZZ mapping (adapter-internal): Character→Agent, Equipment→W-Engine, Gear→Drive Disc,
duplication→Mindscape, special progression→Core Skill, team size 3, gear slots 1–6.

## 4. Data model (authoritative, SQLite)

All player rows carry `game_id` + `player_profile_id` (account & game isolation is tested).
Every important row has `created_at`/`updated_at`; user-verifiable rows add
`last_verified_at` and a `source` tag (`manual`, `screenshot_import`, `research`…).

Core tables (see `db/models/` for the full set):

- `player_profiles`, `player_preferences` (scope = `global` or a game id; JSON value)
- `characters` (+ `character_skills` rows keyed by adapter skill keys)
- `equipment_items` (weapon-like inventory; `equipped_character_id`)
- `gear_items` (individual gear: set, slot, main stat, substats JSON, level, lock/favorite,
  `equipped_character_id`)
- `character_builds` + `build_gear_slots` (loadout = equipment + per-slot gear references;
  `is_active` build per character drives what "my Burnice is running" returns)
- `teams` + `team_members` (unique character per team — mutual exclusion enforced in DB)
- `resources` + `resource_plan_entries` (planned per-character demand for threshold math)
- `combat_results` (immutable history w/ team + build snapshots), `training_issues`,
  `training_goals`
- `redeem_codes` + `player_code_states` (used-state is per player)
- `research_sources`, `research_claims` (typed claims + evidence), `change_records`
  (detect → review → apply workflow)
- `screenshot_imports` (candidate → diff → confirm workflow)
- `encounters`, `encounter_slots`, `recommendations`, `audit_results`

JSON columns are used only for genuinely flexible content (substat details, snapshots,
adapter-validated game extras in `characters.data`). Searchable/relational state is real
columns with FKs and uniqueness constraints. SQLite PRAGMA `foreign_keys=ON` is set per
connection; services write in transactions.

## 5. Deterministic subsystems the LLM must not improvise

- **Resource thresholds** (`core/resources/thresholds.py`): given quantity `Q`, single-character
  max target `X`, planned demand `Y` (from `resource_plan_entries`), returns one of
  `done` (Q ≥ Y) → white, `prep` (X ≤ Q < Y) → cyan/lime, `very_low` (Q ≥ low_fraction·X) →
  orange, `critically_low` (Q < low_fraction·X) → red, `unknown` (X or Y unknown) — always with
  a calculation explanation. Fractions are adapter-configurable; unknown inputs never guess.
- **Team integrity**: a character occupies at most one *active* team; team size validated
  against adapter rules.
- **Build/gear equipping**: activating a build claims its gear (a gear item can be equipped by
  at most one character's active build; conflicts are resolved deterministically by clearing
  the other slot and recording it in the response).
- **Gear evaluation, team scoring, optimizer** (later milestones): components are explicit,
  labeled `HEURISTIC`/`MEASURED`/`CONSENSUS`, with per-component reasons. No opaque single
  LLM score; no fabricated DPS.

## 6. Uncertain-data workflow (screenshots & research)

```
candidate (VLM/manual) → schema validation → diff vs current → user confirmation
                        → transactional commit (source-tagged, last_verified_at bumped)
```

Raw VLM/research output can never mutate state directly. Low-confidence fields are stored as
unknown, never guessed. Reference data changes go through `change_records` with
`pending → approved → applied` review.

## 7. LLM abstraction

`core/llm/` speaks OpenAI-compatible chat completions over `httpx` (no vendor SDK):
configurable base URL / API key / model / timeout, optional `image_url` content, and a
`extract_structured(schema, ...)` helper that validates JSON output against a Pydantic model
and retries once on invalid output. Keys come only from env/config; a logging filter and
explicit redaction keep them out of logs. Domain code receives an `LLMClient` protocol so
tests inject mocks.

## 8. Configuration & security

Env prefix `GAME_COMPANION_` (see `.env.example`): `LLM_BASE_URL`, `LLM_API_KEY` (secret —
never logged/committed), `LLM_MODEL`, `DATA_DIR` (default `~/.local/share/gacha-companion`),
`DATABASE_URL` override, `HOST` (default `127.0.0.1`), `PORT` (default `8765`), `LOG_LEVEL`,
`LOG_JSON`, `SEARXNG_BASE_URL`. The service binds localhost only unless explicitly configured.

## 9. Testing strategy

- Adapter-contract suite runs the *same* core scenarios against ZZZ and `example_game`
  (team sizes, slots, thresholds, terminology in exports) and asserts core modules never
  import game packages.
- CRUD, isolation (per-player, per-game), team mutual exclusion, threshold math, export
  regeneration, screenshot-candidate validation, LLM structured-output validation (mocked
  transport). No external API calls in the normal suite; real-endpoint tests are opt-in
  via env marker.

## 10. Decision log (smallest reversible decisions)

| Decision | Rationale / revisit when |
| --- | --- |
| UUID string PKs | Stable IDs across export/import; no cross-game id collisions |
| Sync SQLAlchemy + sync routes | Simplest correct stack for SQLite; revisit only under real perf need |
| Alembic migrations, autogenerate initial | Single source of truth = models metadata |
| `argparse` CLI | Zero extra deps; revisit if subcommands grow complex |
| Adapter registry = explicit map `game_id → module path` + `register()` API | Deterministic; supports plugins/tests without magic discovery |
| Gear `equipped_character_id` maintained by build service | One write path; tested |
| Threshold semantics `done/prep/very_low/critically_low/unknown` | Per SPEC M12; configurable fractions; documented edge cases in `core/resources/thresholds.py` |
| ZZZ static roster data ships as a clearly-marked starter dataset | Real mechanics data comes from the research layer; never fabricated |

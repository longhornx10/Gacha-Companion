# Data Model

Authoritative store: SQLite (WAL, foreign keys ON) via SQLAlchemy 2.x.
Schema changes happen only through Alembic (`game_companion/db/migrations/`).
Regenerable exports live in `<data_dir>/exports/<game>/` and are never inputs.

## Conventions

- PKs are 32-char UUID hex strings (`db/base.py::PKMixin`).
- Every table has `created_at` / `updated_at` (UTC via `UTCDateTime`).
- User-verifiable rows add `last_verified_at` + `source`
  (`manual` | `screenshot_import` | `research` | ...).
- All player rows carry `game_id` + `player_profile_id` — account **and** game
  isolation are enforced and tested.
- JSON columns only for genuinely flexible content (substat details,
  snapshots, adapter-validated extras). Searchable state = real columns.

## Tables (by domain)

**Profiles** — `player_profiles`; `player_preferences` (scope = `global` or a
game id; unique scope+key; JSON value).

**Roster** — `characters` (key unique per game+player; level,
`duplication_level` [generic Mindscape/Eidolon], favorite, notes, `data`
JSON [adapter-validated], owned); `character_skills` (skill_key from adapter
definitions; unique per character).

**Equipment** — `equipment_items` (weapon-like: key, rarity, level,
`refinement` [stars], `equipped_character_id`, locked).

**Gear** — `gear_items` (set_key, slot [adapter slot keys], rarity, level,
main_stat_key/value, `substats` JSON [{key, value, rolls}], locked, favorite,
`equipped_character_id`).

**Builds** — `character_builds` (unique name per character; `is_active`
defines "what X is running"; `equipment_item_id`); `build_gear_slots`
(unique build+slot → gear_item_id). Activating a build claims its gear;
evictions are recorded in the API response.

**Teams** — `teams` (unique name; `is_active`), `team_members` (unique
character per team, position, role). *Active*-team membership is mutually
exclusive per character (service-enforced, tested).

**Resources** — `resources` (unique key per game+player, quantity);
`resource_plan_entries` (planned per-character demand → Y in threshold math).

**History/training** — `combat_results` (team+build *snapshots*, score/stars/
cleared/clear time, retries; rows are never rewritten when builds change);
`training_issues` (category+character recurrence counting); `training_goals`.

**Codes** — `redeem_codes` (unique per game; status
active/expired/unknown/recycled, expires_at); `player_code_states`
(per-player used flag — used codes still render, struck through).

**Research** — `research_sources` (unique key per game, category, trust,
`content_hash` for change watching); `research_claims` (typed:
official_fact → speculation; evidence JSON [{url, quote, retrieved_at}];
superseded flag); `change_records` (pending → approved/rejected → applied).

**Vision imports** — `screenshot_imports` (screen_type [generic keys],
candidate JSON [schema-validated], diff, confidence, extracted/rejected
fields, status pending/applied/rejected/failed, screenshot hash).

**Misc** — `encounters` + `encounter_slots` (mode instances with constraints);
`recommendations` (kind/subject/payload/basis); `audit_results` (per-character
issue lists, checked_at).

## Integrity rules (tested)

- gear ↔ active build: one gear item equips to at most one character;
  conflicts resolved deterministically with recorded moves
- team size inside adapter `TeamRules`; no duplicate member in a team
- a character on ≥1 active teams cannot join another active team (409)
- candidate data reaches the DB only through `imports/{id}/confirm`
- DB writes are transactional per request (commit on success)

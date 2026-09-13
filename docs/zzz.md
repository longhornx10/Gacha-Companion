# ZZZ Adapter Notes

Everything ZZZ-specific lives in `game_companion/games/zzz/`. The core knows
none of these words.

## Terminology mapping

| Generic core concept | ZZZ name |
| --- | --- |
| Character | Agent |
| Equipment (weapon-like) | W-Engine |
| Gear piece | Drive Disc |
| Duplication level | Mindscape |
| Special progression | Core Skill |
| Team size | exactly 3 |

## Rules implemented

- **Gear slots** 1–6 with per-slot main-stat pools (`gear_rules.GEAR_SLOTS`).
- **Skills**: Basic Attack, Dodge, Assist, Special Attack, Chain Attack (max
  12) and Core Skill (max 7 — *starter value, verify in game*).
- **Encounter modes** (starter): Shiyu Defense (2 slots), Deadly Assault
  (3 slots — one team per squad).
- **Resources**: dennies, agent/w-engine/drive EXP, skill/core/boss/weekly
  materials. `data/resource_requirements.json` ships all `null`: threshold
  statuses return `unknown` until verified numbers are supplied (file or
  `<data_dir>/overrides/zzz/resource_requirements.json`).
- **Sources** (`sources.py`): official site/news (trust 5), HoYoLAB (4),
  Hakush.in (4), Prydwen/Game8 (3), Fandom (3). `#CODES` discovery uses the
  official keys.

## Scoring hooks (all HEURISTIC, all explainable)

- **Gear**: score = 45% main-stat fit + 55% desired-substat coverage, weighted
  by the character's archetype (attack/anomaly/stun/support/defense). With no
  target character, the disc is scored against its best-fit archetype; if that
  archetype isn't on your roster → verdict `speculative`. Verdict bands:
  strong ≥75, useful ≥55, niche ≥40, weak, likely-safe-to-discard ≤18.
- **Team**: role balance (damage + stun/anomaly setup + utility), faction pair
  heuristic (Additional Ability proxy), attribute diversity, comfort (honors
  player preferences).
- **Equipment**: rarity base + level-fraction + stars, 0–10.

## Screenshot ingestion

Generic screen keys with ZZZ-specific prompts in `prompts/`:
`character_overview` (Agent overview → `duplication_level` = Mindscape rank),
`skills`, `equipment` (W-Engine), `gear_list` (Disc loadout, informational),
`gear_detail` (single Disc → creates a gear item on confirm), `resources`.
Schemas live in `screenshot_schemas.py`; every field is nullable — the VLM is
instructed to use null over guessing, and candidates apply only after
explicit confirmation.

## Starter data honesty

`data/agents.json` (roster attributes/specialties/factions), progression caps
and set names are **hand-curated starter data**, marked as such. Correction
paths: research layer claims, or user overrides in
`<data_dir>/overrides/zzz/` (`agents.json`, `progression.json`,
`drive_disc_sets.json`, `resource_requirements.json`).

# Adding a New Game (Adapter Guide)

This guide is written so Honkai: Star Rail (or NTE, or anything similar) can be
added **without touching core code**. Read `docs/architecture.md` §3 first.

## 1. What an adapter must provide

Create `game_companion/games/hsr/` with:

```
games/hsr/
    manifest.toml          # identity + terminology metadata
    adapter.py             # HSRAdapter(GameAdapter)
    ...                    # rules/schemas/data modules as needed (any layout)
```

`manifest.toml`:

```toml
[game]
game_id = "hsr"
display_name = "Honkai: Star Rail"
version = "0.1.0"
summary = "HSR reference implementation."

[terminology]
character = "Character"
equipment = "Light Cone"
gear = "Relic"
duplication = "Eidolon"
special_progression = "Trace"
```

## 2. Required adapter methods (abstract — you must implement)

| Method | HSR example |
| --- | --- |
| `terminology()` | Character / Light Cone / Relic / Eidolon / Trace |
| `team_rules()` | `TeamRules(min_size=4, max_size=4)` |
| `gear_slots()` | Relic slots (Head, Hands, Body, Feet) + Planar slots (Sphere, Rope) |
| `stat_definitions()` | HP, ATK, DEF, SPD, CRIT Rate, CRIT DMG, Break Effect, Effect Hit Rate, Energy Regen... |
| `skill_definitions()` | Basic ATK / Skill / Ultimate / Talent (keys `basic`, `skill`, `ult`, `talent`) |
| `resource_definitions()` | Fuel, Stamina-refills, Trace materials... (`single_character_max` only if you have verified numbers) |

## 3. Optional hooks (defaults are fine to start)

- `gear_sets()` — relic set metadata (leave effects out until verified).
- `progression_rules()` — level caps/skill targets for planner + audit.
- `encounter_modes()` — e.g. Memory of Chaos (slot count per stage), Pure Fiction.
- `source_registry()` — official news, HomDGCat/Prydwen/fandom, with trust 1–5.
- `screenshot_specs()` — typed Pydantic candidates + VLM prompt per screen.
  Use the **generic screen keys** (`character_overview`, `skills`,
  `equipment`, `gear_detail`, `gear_list`, `resources`) so core apply-logic
  understands them; put game wording in the prompts (e.g. "extract the
  Eidolon rank into `duplication_level`").
- `code_config()`, `persona_flavors()`, `tutor_notes()`.
- Validation: `validate_character_data()` — whitelist game-specific extras in
  `characters.data` (HSR: `element`, `path`).
- Lookup: `character_meta()`, `resolve_character_key()`.
- Scoring: `score_gear()`, `score_team()`, `character_slot_fit()`,
  `score_equipment_for_character()` — every component must carry a label
  (`HEURISTIC`/`MEASURED`/`CONSENSUS`) and explainable detail. Never fabricate
  DPS or consensus.

## 4. Register the adapter

One line in `game_companion/core/games/registry.py`:

```python
ADAPTER_ENTRYPOINTS = {
    ...
    "hsr": "game_companion.games.hsr.adapter:HSRAdapter",
}
```

That is the only core-adjacent edit; it stores a *string*, so importing the
registry never imports your game package.

## 5. Prove it with the contract suite

Copy the pattern from `tests/game_adapter_contract/test_contract.py`: add
`"hsr"` to `ADAPTER_IDS`. The contract tests will then verify:

- team-size enforcement uses HSR's 4 (not ZZZ's 3),
- gear slot keys are HSR's,
- thresholds/evaluations work against HSR resource definitions,
- exports render HSR terminology,
- scoring hooks return labeled components.

The source-isolation tests (`test_core_isolation.py`) will fail the build if
you accidentally import your adapter from core, or leak game vocabulary
("Relic", "Light Cone", ...) into `game_companion/core/`.

## 6. Data honesty rules

- Ship curated rosters as clearly-marked *starter data* (`_note` fields), with
  runtime overrides in `<data_dir>/overrides/<game_id>/*.json`.
- Leave unknown numbers `null`: the resource evaluator reports `unknown`
  rather than guessing; the planner says when data is missing.
- Mechanics/build facts belong in the research layer (claims + evidence), not
  hardcoded in the adapter.

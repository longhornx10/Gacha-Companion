# Farm Planner (M26)

Answers: **"Given the current meta, my roster, and the actual quality of the
Drive Discs I own — which set or Area Patrol stage should I farm next?"**

Page: `/ui/farm` · API: `GET /api/games/{game_id}/farm-plan?beta=1.2&scope=mine`

## How it presents (granny-simple)

The page asks exactly two plain questions and answers with one plain verdict:

- **Plan for** — "My agents" (default: demand is restricted to the player's
  roster via `unit_keys`; falls back to the whole meta with a visible note
  when no owned agent is in the dataset) / "Everyone in the meta".
- **Spare gear to keep** — "Just what I need" (β 1.0) / "A comfortable
  margin" (β 1.2, default) / "Lots of spares" (β 1.5).

The answer is a card — *Farm this next: Words and Weapons — drops Yunkui
Tales, the set you need most here (currently: none yet)* — followed by a
plain list ("Sets you need most, in order": set / how you're doing / where to
get it) and a few runner-up stages. Coverage is expressed in words (none yet →
a good start → getting there → almost there → covered), not decimals. The
full numeric table, labels, and provenance live behind a collapsed
**"Show the details"** fold.

## How it computes (the equations)

Per gear set `s`, over the meta dataset's units (agents) and their weighted
build variants:

| Quantity | Definition | Label |
|---|---|---|
| Demand `D_s` | `Σ_units Σ_variants q_v × pieces_v(s)` — a unit asks for exactly 4 four-piece + 2 two-piece pieces in expectation, spread across its alternatives by weight | CURRENT BUILD DATA |
| Need `P_s` | number of units whose **primary** (highest-q) build uses `s` (each unit counted once per set) | CURRENT BUILD DATA |
| Target `T_s` | `⌈β × P_s⌉`, β ∈ {1.0, 1.2, 1.3, 1.5} — how many spare sets worth of pieces you should hold | HEURISTIC (your choice) |
| Effective `I_s_eff` | Σ quality credits of owned pieces of `s` | HEURISTIC grading over your inventory |
| Coverage `C_s` | `I_s_eff / T_s` | DERIVED |
| Pressure `F_s` | `demand_share_s × max(0, 1 − C_s) × B_s` | DERIVED |
| Stage pressure | `Σ_{s in stage} F_s × split` — split is an even 50/50 **ASSUMPTION** (no official drop rates) | DERIVED / ASSUMPTION |

`B_s` (scarcity, HEURISTIC): 1.0 normal · 1.2 meaningful · 1.3 severe IV/VI ·
1.5 severe V (the set's users demand elemental slot-V mains — the rarest
useful main to hit). Table lives in `games/zzz/farm.py::SCARCITY_BOOSTS`.

## Quality credits (grading)

`unusable 0.00` (main stat can't roll in that slot) · `placeholder 0.50` ·
`good 0.75` · `strong 0.90` · `finished 1.00` (S-rank, +15, right main).
Lower rarities get HEURISTIC ceilings (A 0.75, B 0.5) — exact in-game caps
unverified. A disc with no set recorded is *unranked* and counts toward
nothing rather than being guessed. Equipped discs count toward set inventory
(the equipped/unequipped split is reported separately).

## Where things live

- `game_companion/core/farm/service.py` — generic math only (no game words;
  enforced by the isolation test). Inputs are plain dicts.
- `game_companion/games/zzz/farm.py` — ZZZ glue: dataset loading, disc
  grading, scarcity, plan assembly.
- `game_companion/games/zzz/data/drive_meta.json` — 42 meta agents (T0–T1,
  Prydwen, patch 3.2) with normalized build variants, slot mains, teams, and
  a **per-agent `build_patch` stamp** (e.g. Alice's build was last touched at
  2.1 — older stamps are visible, never silently trusted).
- `game_companion/games/zzz/data/farm_stages.json` — the 12 Area Patrol
  stages (names + adding versions from the Fandom change history,
  corroborated by two further sources; stage 12 "Deceits and Bulwarks" is 2.5).
- `game_companion/games/zzz/data/drive_disc_sets.json` — all 30 current sets
  with 2pc/4pc text, `farmable`, and `farm_stage` backrefs. 24 farmable; 6
  event/shop sets (Bunny in Wonderland, Feathered Fate, Notes From the
  Chained, The Sky Ablaze, Thorned Rose, Wuthering Salon) are labeled
  `event/shop` in the Farm column instead of being recommended for farming.
- Overrides: drop `drive_meta.json` / `farm_stages.json` /
  `drive_disc_sets.json` into `<data_dir>/overrides/zzz/`.

## Weight derivation (from Prydwen's recommendation lists)

- 4pc families: Prydwen's usage percentages when given (e.g. Alice: Fanged
  Metal 100% vs Hormone Punk 88.84% → normalized 0.53/0.47); else editorial
  rank decay 0.7^rank.
- 2pc options: Prydwen ranks them without percentages, so rank decay
  1.0/0.7/0.5/0.35/0.25 normalized per agent — a **HEURISTIC**, flagged in
  the dataset's `_meta.notes`.
- Per agent, weights normalize so 4pc demand sums to exactly 4 pieces and
  2pc demand to exactly 2 (the spec's "2 pieces, not 6").

## What the MVP deliberately does not do

- No assignment solver (which owned disc goes on which agent) — the spec
  explicitly defers it; the planner operates on set/slot/main/grade/equipped.
- No drop-rate learning yet: the stage split stays an ASSUMPTION until real
  rates are sourced or measured.
- Team archetypes (15 in the dataset, w=1.0) are not yet a scoring input;
  demand iterates unique agents so nothing double-counts.

## Regenerating the meta dataset

The packaged JSONs were generated from Prydwen page data (flight payload
extraction) on 2026-09-25 at patch 3.2. To refresh after a new version:
re-fetch the tier list, disk-drives page, and per-agent pages, then re-run
the extraction + normalization (the builder script from the M26 session;
its steps are documented in `drive_meta.json._meta.notes`). Anything
unparseable is skipped, never guessed.

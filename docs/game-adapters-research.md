# Gacha Adapter Research: ZZZ / HSR / NTE

Feeds Milestone 24 (adapter workbench). Three questions answered here:

1. How do the buddy's games (ZZZ, HSR, NTE) map onto our generic ontology?
2. Where can adapter data be sourced from, programmatically and honestly?
3. What does the "source-backed bootstrap" pipeline look like?

Core principle already in the codebase: the core speaks only generic terms and
the LLM is taught the ontology **once**; each adapter carries a terminology
table so the model "applies the game-specific names after that". This document
is the evidence base for extending that table to a third game and to a proper
resource taxonomy.

---

## 1. Generic ontology (what the core already speaks)

| Generic concept | Meaning |
| --- | --- |
| `character` | Playable unit you own and level |
| `equipment` | Signature/unique weapon bound to progression |
| `gear` | Farmable set-based equipment with slots + substats (discs/relics) |
| `duplication` | Dupe system, 0–6/0–7 scale |
| `special_progression` | Character-specific skill progression track |
| roles / attributes | Combat role + element, used by synergy scoring |
| currencies | `pull_currency` (premium), `pull_ticket_*`, `money`, `stamina` |
| `encounter_mode` | Endgame modes the optimizer allocates teams across |
| banners | Limited/standard rotation (codes + "who to pull" advice) |

## 2. Terminology mapping across the three games

Verification status: **[built]** = already encoded in our ZZZ adapter and
tested; **[confirmed]** = verified against current wikis during this research;
**[verify]** = high confidence but confirm exact in-game names when the
adapter is built (NTE is young and naming may still shift).

| Generic | ZZZ [built] | HSR [confirmed] | NTE [confirmed/verify] |
| --- | --- | --- | --- |
| character | Agent | Character | Character |
| equipment | W-Engine | Light Cone | Arc |
| gear (set+substats) | Drive Disc | Relic (+ Planar Ornament) | Cartridge / Module system [verify exact split] |
| duplication | Mindscape (M0–M6) | Eidolon (E0–E6) | Awakening (A-ranks, freely chosen nodes — "Cosmic Insights") |
| special progression | Core Skill (A–F) | Traces | Skill/Module progression [verify] |
| roles | Specialty (Attack, Stun, Anomaly, Support, Defense, Rupture) | Path (Destruction, Hunt, Erudition, Harmony, Nihility, Preservation, Abundance, Remembrance) | Role (DPS/Support/… — verify exact set) |
| attributes/elements | Fire/Ice/Electric/Physical/Ether | Combat Type (7 elements) | Esper attributes with a cycle/counters system ("Esper Cycles") [verify names] |
| factions/alignment | Faction | Faction | [verify] |
| rarity | S / A | 5★ / 4★ | S/A/B ranks [verify] |
| stamina | Battery Charge | Trailblaze Power | [verify] |
| gacha banner | Signal Search | Warp | "The Fair" (board-style summoning with Dice) |
| endgame encounter modes | Shiyu Defense, Deadly Assault, Hollow Zero | Memory of Chaos, Pure Fiction, Apocalyptic Shadow, Simulated Universe | [verify — Prydwen keeps a "Game Modes" guide] |
| unique-to-game | Bangboo (companions) | — (Relic sets carry most flavor) | Vehicles (driving/cars) — out of core scope for v1 |

### Currency mapping (the Polychrome/Stellar Jade problem)

| Generic category | ZZZ | HSR | NTE |
| --- | --- | --- | --- |
| `pull_currency` (spendable, converts to tickets) | Polychrome | Stellar Jade | Annulith |
| paid premium (tops up the above) | Monochrome / real-money topups | Oneiric Shard | Riftcrystal (→ Annulith at 1:1) |
| `pull_ticket_limited` | Master Tape | Star Rail Special Pass | Tri-Key [verify banner mapping] |
| `pull_ticket_standard` | Master Tape | Star Rail Pass | Solid Dice / Fabricated Dice [verify] |
| `money` | Dennies | Credits | [verify] |

Adapter implication: the resource taxonomy gains a `category` field
(`pull_currency`, `pull_ticket_*`, `money`, `stamina`, `standard_material`).
Views and the chat model can then say "premium pull currency" across games
while displaying the game-native name. This is data in the adapter, not core
vocabulary — the core-isolation rule holds.

### Gear systems in detail (drives the `gear_type` / family design)

| | ZZZ Drive Disc | HSR Relic | HSR Planar Ornament | NTE Cartridge |
| --- | --- | --- | --- | --- |
| Pieces | 6 slots (I–III fixed flat mains, IV–VI pooled mains) | 4 slots (Head flat HP, Hands flat ATK, Body/Feet pooled) | 2 slots (Sphere, Link Rope) | piece count TBD at build |
| Set rule | 2pc/4pc **across equipped slots** | 2pc/4pc across slots | 2pc | **4-Module combo on the piece** — set identity lives on the Cartridge, not across slots (NTE inverts the other two) |
| Rarity | S/A/B | 5★/4★ | 5★/4★ | B/A/S |
| Max level | 15 | 15 | 15 | TBD |
| Substats | up to 4 | up to 4 | up to 4 | main + random substats (CRIT Rate/DMG, ATK%, "Universal DMG%", "Cosmos DMG%" element-slot equivalent) |

Sources: NTE structure confirmed via Game8 (Cartridge list/set effects,
Modules/"Rewind" upgrade system), neverness.gg (B/A/S rarities, 4-Module
combos), Mobalytics build guides (main/substat naming). NTE Modules are
obtained through the "Rewind" gacha and farming. Design consequence: the set
rule is adapter data (`set_rule: fixed_pieces | module_combo`), never a core
assumption — see standalone-design.md §4.

## 3. Data sources for bootstrapping adapter data

### Structured JSON (preferred where available)

- **HSR — [Mar-7th/StarRailRes](https://github.com/Mar-7th/StarRailRes)**
  (mirrored as [StarRailStaticAPI](https://vizualabstract.github.io/StarRailStaticAPI)):
  complete structured JSON — characters, stats, traces, eidolons, light cones,
  relics, multilanguage text. The single best source for an HSR adapter.
  Also [kel-z/HSR-Data](https://github.com/kel-z/HSR-Data) (single-file JSON
  of light cones/relics/characters).
- **ZZZ/HSR — [hakush.in](https://hakush.in)** JSON endpoints
  (`api.hakush.in/<game>/data/...`), with a maintained Python wrapper
  ([seriaati/hakushin-py](https://github.com/seriaati/hakushin-py)). Good for
  agent/light-cone data, multi-game, machine-readable.
- **ZZZ — our own starter data** (`game_companion/games/zzz/data/*.json`):
  hand-curated, honesty-marked. Remains the fallback/bootstrap seed.

### Wiki scraping (fallback + the only game-wide option for NTE today)

- **[Prydwen](https://www.prydwen.gg/neverness-to-everness)** covers all three
  games with the same site structure (Next.js; data available as JSON behind
  the pages): characters, weapons/Arcs/light cones, gear guides, tier lists,
  team guides, codes, game modes. For NTE it is currently the richest single
  source (Characters, Arcs, Cartridges, Banners, Effects Dictionary, Game
  Modes, team tier list).
- Others (Game8, Mobalytics, fandom wikis) — usable for the research layer's
  cross-checking, not as bootstrap sources.

### Ground rules (data honesty, extended to sourcing)

1. Every datum carries provenance: `source` URL + `fetched_at`.
2. Fetched data lands as **pending change records** (the M19 review flow) —
   a human approves before it replaces starter data; statuses move
   `unknown → consensus` only after review.
3. Respect the sources: cache aggressively, fetch on demand (weekly
   `check-sources` cadence), identify a User-Agent, no hammering.
4. Personal/local-use stance: community game data is used to run a private
   tool, not republished.

## 4. The bootstrap pipeline (how "the tool builds the adapter")

    game-companion bootstrap-game <game_id> --source auto|prydwen|hakush|starrailres

Steps, in order:

1. **Scaffold** the adapter package (terminology table, rules, screenshot
   specs, prompts, source registry, empty data files with honesty markers).
2. **Fetch** the source(s) → transform into our data-file shapes; every datum
   provenance-tagged.
3. **Stage** everything as pending change records; print a human-readable diff
   summary (counts per category).
4. **Review** — the M19 approve/reject UI/flow; contract tests must pass
   before activation.
5. **Stay fresh** — subsequent `check-sources` runs diff against the fetch,
   so upstream changes arrive as reviewable updates, not silent overwrites.

The terminology table is the piece that makes the LLM work across games: the
system prompt teaches the generic ontology once, then injects the adapter's
table ("equipment = Light Cone, duplication = Eidolon, pull currency = Stellar
Jade…"), and the model speaks the game's language. No per-game prompting
knowledge is hardcoded in the core.

## 5. Open items to verify at NTE-adapter build time

- Exact gear split: Cartridge vs Module vs the "Rune" naming seen in early
  guides; set equivalents and substat slots.
- Riftcrystal vs Annulith (which is premium-converts, which is earned).
- Official role and Esper-attribute name lists; faction naming.
- Endgame mode names and team-slot rules (the optimizer needs
  `encounter_mode` definitions).
- Stamina currency name; standard-banner ticket name.

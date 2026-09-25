# Milestone Tracker

Spec: [SPEC.md](SPEC.md). Work proceeds in dependency order; keep this file current.

Status after the foundation build (all verified by the test suite — 89 tests,
`pytest tests`; lint clean via `ruff check game_companion tests`).

Legend: ✅ done + tested · 🚧 partial (notes) · ⬜ not started

## Milestone 1 — Foundation
- ✅ Project structure, pyproject, env-prefixed config, structured logging w/ secret redaction
- ✅ SQLite + SQLAlchemy 2.x models (25 tables) + Alembic migration (verified: upgrade + downgrade roundtrip, no schema drift)
- ✅ Repository layer + domain services (roster/builds, equipment/gear, teams, resources, codes, history, training, research, imports)
- ✅ FastAPI service, `/health` + `/api/health`, localhost-only default binding
- ✅ Game registry + `GameAdapter` contract (lazy string-based imports; plugins can `register()`)
- ✅ ZZZ adapter (terminology, stats, skills, team/gear/resource/progression/encounter rules, source registry, screenshot specs, prompts, starter data w/ honesty markers)
- ✅ Fake second adapter (`games/example_game`) + adapter-contract tests proving core genericity
- ✅ Player profiles, preferences (global + per-game scope)
- ✅ CRUD via REST for every domain; JSON + Markdown exports (regenerable; SQLite authoritative)
- ✅ Tests: migrations, CRUD, adapter contract (zzz+example), player/game isolation, team mutual exclusion, gear-claim conflicts, resource thresholds, exports, candidate validation, LLM validation/retry (mocked; no external calls)

## Milestone 2 — ZZZ account model
- ✅ Per-agent ownership, level, Mindscape (generic `duplication_level`), Core Skill + all skill levels
- ✅ W-Engine (generic equipment): level, stars/refinement, equipped-by (exclusive per character)
- ✅ Drive Disc loadout: active build with per-slot discs; individual discs in inventory w/ substats/rolls/lock/favorite
- ✅ Partial records everywhere; notes, favorite, `last_verified_at`, source tags

## Milestone 3 — Open WebUI integration
- ✅ Thin Tools file (`integrations/openwebui/gacha_companion_tools.py`) covering the SPEC tool list + recommendations; valves for base_url/game/player
- ✅ docs/openwebui.md
- 🚧 Manual end-to-end pass with a live Open WebUI (needs the user's endpoint/key; everything behind it is API-tested)

## Milestone 4 — LLM abstraction
- ✅ OpenAI-compatible client (httpx; base URL/key/model/timeout, image content, `extract_structured` w/ schema validation + retry, code-fence stripping)
- ✅ Secret redaction (SecretStr + logging filter); key never in errors/logs
- ✅ Opt-in real-endpoint test (`tests/integration/test_real_llm.py`, skipped without API key)

## Persona system
- ✅ Persona schema + store (`<data_dir>/personas/*.json`), 3 built-ins incl. ZZZ-flavored samples
- ✅ Tone-only influence (enforced by prompt contract + separation); switching personas never touches game state

## Milestone 5 — Screenshot / vision ingestion
- ✅ Flow: image/manual candidate → schema validation → diff → confirm/reject → transactional apply (source-tagged, `last_verified_at` bumped)
- ✅ Generic screen keys (`character_overview`, `skills`, `equipment`, `gear_detail`, `gear_list`, `resources`) + ZZZ prompts/schemas; unknowns stay null
- ✅ Import audit trail (hash, confidence, extracted/rejected/applied fields)
- 🚧 Live VLM accuracy tuning on real ZZZ screenshots (needs real screenshots)

## Milestone 6 — Research / source system
- ✅ Source registry seeding per adapter; claims w/ claim_type + evidence; cross-check flags disagreement instead of inventing consensus
- ✅ Search provider abstraction (SearXNG provider, fail-loud Null) + HTML fetcher
- ✅ `/research/query` → fetch top pages → schema-validated LLM answer w/ citations → stored claim
- 🚧 Answer quality depends on the configured model/endpoint (manual evaluation pending)

## Milestone 7 — Combat tutor
- ✅ `/tutor/explain`: deterministic context (character, active build, preferences, open training issues, research claims) + persona + mode guidance (simple/advanced/button_by_button); 503 when no LLM
- 🚧 Rotation quality for specific agents depends on stored claims/kit data (no fabricated rotations by design)

## Milestone 8 — Codes (#CODES)
- ✅ Code tracking (active/expired/unknown/recycled, expiry), per-player used state, `#CODES` markdown (used = strikethrough, recycled = ♻ shown, never hidden), `codes.md` endpoint + tool
- 🚧 Automatic discovery from sources (manual/API entry now; watcher exists for source changes, code parsing not wired)

## Milestone 9 — Account-aware team recommendations
- ✅ Roster/build-aware candidate teams; categories best_owned / most_comfortable / substitutes; active-team overlap flags; visible HEURISTIC components

## Milestone 10 — Equipment comparison
- ✅ Adapter quality hook (explainable 0–10), ranking, currently-equipped, best-owned, easiest-upgrade (level headroom); explicit "no DPS percentages" note

## Milestone 11 — Gear inventory / value
- ✅ Deterministic archetype-weighted scoring with reasons; verdicts strong/useful/niche/speculative/weak/likely_safe_to_discard; inventory view (best-for per character, discard list)

## Milestone 12 — Resource tracking
- ✅ Deterministic thresholds done/prep/very_low/critically_low/unknown + colors + calculation explanation; configurable fraction; unknown inputs never guessed; plan entries define Y

## Milestone 13 — Upgrade / farming planner
- ✅ Gap-based prioritized actions (active teams/favorites weighted) + resource warnings; honesty note when requirement data is missing

## Milestone 14 — Roster audit
- ✅ Rule-based per-character audit (level/skill gaps, build completeness, gear slots, staleness) stored as `audit_results`; `verify` = screenshot import confirm path

## Milestone 15 — Multi-team optimizer
- ✅ Generic `optimize_team_allocation` (branch & bound, deterministic; caps documented), distinct-character assignments across encounter slots, greedy comparison + opportunity-cost explanation, alternatives
- ✅ Objectives: maximize_total / maximize_clears (surplus capped so weak slots get lifted) / maximize_comfort

## Milestone 16 — Team scoring
- ✅ Visible components (synergy, encounter fit, build readiness, comfort) each labeled HEURISTIC/MEASURED/CONSENSUS; totals are relative only — no fake DPS anywhere

## Milestone 17 — Combat results / victory history
- ✅ Snapshotted results (team/build at record time); trends: win rate, per-encounter, per-team, early-vs-recent improvement

## Milestone 18 — Personal training model
- ✅ Issues w/ recurrence (same category+characters bumps occurrences), goals, focus endpoint; tutor context includes open issues

## Milestone 19 — Daily change / data audit
- ✅ Source watcher (hash-based) → pending `change_records` → approve/reject workflow; `game-companion check-sources` CLI + endpoint
- 🚧 No scheduler yet (cron/systemd user job can call the CLI; documented as the intended setup)

## Acceptance checkpoints
- 🚧 First useful release: all implemented surfaces are API-tested and the acceptance flow was rehearsed end-to-end (profile → agents → build → authoritative Q&A data path → import confirm → #CODES → exports → persistence). Remaining: user-run pass with real Open WebUI + their LLM endpoint/key.
- ✅ Second milestone capabilities (disc inventory/eval, resources+warnings, planner, audit, combat history)
- ✅ Third milestone capabilities (multi-team allocation, explainable scoring, training, history, change audit)

## Standalone UI plan (milestones 20–23) — decision recorded 2026-09-23

Open WebUI carried the first release, but the integration surface (connections,
tool install, valves, per-chat toggles, duplicate tools) is where every real
user failure happened. The service is already the brain and the OWUI tool file
is a thin translator, so the service can grow its own face and OWUI becomes
optional. Order matters: 20/21 deliver value even if 22 slips; 22 is the
cutover; 23 retires the default-path dependency.

Scope note (2026-09-23): reviewed against the original feature manifesto —
its asks map to milestones 1–19 (tutor, research, team optimizer, disc value,
planner, training, resources with the exact color thresholds, codes, history,
audit). Three deliberate deviations stand: no fabricated DPS/"combat
efficiency" percentages (relative, explained scores instead); combat base
stats (HP/ATK/…) are not stored — they are game-derived and go stale;
button-by-button tutor depth is bounded by stored research claims (never
fabricated). The standalone additions (game switching, in-app DB management,
personas, companion memory, adapter workbench with cross-game naming) live in
M20/M22/M24.

### Pre-flight decisions (locked 2026-09-23) — details in `docs/standalone-design.md`

- **D1 UI stack**: server-rendered Jinja2 + vendored htmx + minimal vanilla JS; no Node, no build chain
- **D2 hosting/auth**: same FastAPI process, `/ui` pages, loopback-only, no auth in v1 (threat model accepted; non-loopback bind refused unless explicit tripwire env)
- **D3 chat**: non-streaming for v1; SSE is post-v1 polish
- **D4 gear families**: `gear_type` column + adapter-declared families (`gear_families.json`); NTE's `module_combo` set rule is adapter data, never a core assumption
- **D5 game switching**: one switcher flips theme (per-game `theme.json` → CSS vars), persona (`bound_game`), conversations, and every list view
- **D6 native window**: `chromium/brave --app` first, browser tab fallback; pywebview off the critical path; Linux-only v1
- **Non-goals v1**: Linux-only · no auth on loopback · single LLM endpoint · non-streaming chat · no mobile · vehicles out of scope · OWUI integration frozen (kept working) · no .deb/AppImage

## Milestone 20 — First-party web UI: shell + account dashboard

DONE 2026-09-24. Jinja2 + vendored htmx under `/ui`; game switcher with
per-game themes (`theme()` hook); `/api/dashboard` aggregate; backup/restore
with live engine swap (no restart needed); loopback bind guard with
`GAME_COMPANION_EXPOSE` tripwire. UI player state lives in
`<data_dir>/ui-state.json` (deviation from PlayerPreference: "which player is
active" can't live on a player).
- ✅ FastAPI serves the UI at `/ui` (server-rendered Jinja2 + vendored htmx per D1; no node build); JSON API stays at `/api`
- ✅ Read views: roster, builds/gear inventory, teams (active + saved), resources with thresholds, codes page (`#CODES` rendering), combat history, roster audit; export download buttons
- ✅ Game switcher in the header — one control, everything follows (D5): active game in `PlayerPreference(global, active_game)`; per-adapter `theme.json` rendered as CSS custom properties; labels from the adapter's terminology; roster/teams/gear/resources/codes/conversations all filter by it
- ✅ `GET /api/dashboard?game_id=` aggregate endpoint (roster/gear counts, active team, currency totals by category, active codes, last import, data freshness) — the one new API the dashboard needs
- ✅ Database management: backup/restore buttons (data dir + SQLite; restore swaps the file and restarts the service), data-folder location shown, reset — **lands before any new tables (chat) so the safety net exists first**
- ✅ Same look/feel as the setup wizard/panel (dark, big type, plain language)
- ✅ UI holds zero business logic — everything via existing tested endpoints
- ✅ Timebox note: shell + dashboard + backup/restore only; inline-editing polish moves to M21 (it shares the gear/import forms)

## Milestone 21 — Data in: deterministic roster importer + upload UI

DONE 2026-09-24. `gear_type` migration (`a1f2c3d4e5b6`, server_default disc);
`gear_families.json` + GearFamily contract; roster importer (tolerant text
parser, unresolved lines reported never guessed, staged via the same
confirm/reject flow); screenshot upload page (multipart, no JS); inline edit
pages for characters/skills/resources/codes/teams; `source` now reflects the
data pathway (roster_import / screenshot_import / user statements).
- ✅ `gear_items.gear_type` migration (first step, per design §4): nullable → backfill zzz rows to `disc` → NOT NULL; adapters declare families in `data/gear_families.json` (slots, set_rule, set_sizes, rarity scale, max level)
- ✅ `game-companion import-roster --file <txt|json>` + `/api/import/roster`: tolerant parser for plain-text rosters (the "PHOENIX ROSTER ZZZ.txt" shape) and our own JSON; maps ownership/level/mindscape/w-engine
- ✅ Staged as a proposed change set → review → confirm/reject (reuses the import confirm flow; unknown/unrepresentable fields reported, never guessed)
- ✅ Screenshot upload UI: drag-and-drop → diff → confirm/reject (retires the curl-only flow)
- ✅ Inline edit/correct forms (levels, mindscapes, skill levels, resources, codes, notes) — explicit user statements, source-tagged like imports (moved here from M20; shares the gear/import forms)
- ✅ This is the bulk path for real rosters (40+ agents) without 40 chat tool-calls

## Milestone 22 — Built-in chat (the OWUI replacement)

DONE 2026-09-24. conversations/chat_messages/companion_memories migration
(`b7e3a9c1d2f4`); non-streaming in-process tool loop (max 6 iterations,
iteration guard forces a final answer); tool activity chips; persona editor
(bound_game honored); companion memories managed in Settings; chat tool set =
roster/teams/resources/set_resource/codes/mark-used/propose_memory. Function-
calling rejection surfaces a clear error — no silent degradation.

Schema, loop shape, and prompt composition per `docs/standalone-design.md` §3.

- ✅ Server-side agent loop in the service: OpenAI tool-calling against the configured endpoint; tools execute as internal function calls (no HTTP hop)
- ✅ Non-streaming chat page for v1 (D3): "thinking" state while the loop runs, markdown rendering, visible tool-activity chips ("checked your roster…"); SSE upgrade post-v1
- ✅ Chat tables via Alembic (`conversations` game-scoped + `messages` + `companion_memories`) + history sidebar; conversation list shows the active game's chats only (D5); single-user, localhost trust model unchanged
- ✅ System prompt composition: data-honesty rules → terminology block (§5) → persona fragment (persona bound to active game, global fallback) → companion memories → active-game context; forced authoritative read (`get_character`/`list_characters`) before account answers — stronger guarantee than OWUI allowed
- ✅ Graceful failure when the endpoint lacks function calling (clear message, no silent degradation); mocked-LLM loop tests (tool sequences, iteration guard, migration)
- ✅ Persona management in-app: picker + simple editor writing `personas/*.json` (tone-only contract preserved; `bound_game` grouping per D5; switching never touches game state)
- ✅ Companion memory: durable player-notes (playstyle, quirks, preferences) the model may propose adding — visible, editable, deletable in the UI, never silently changed (replaces OWUI's hidden memory with an inspectable one)

## Milestone 23 — Cutover: Open WebUI becomes optional

DONE 2026-09-24. `game-companion app` (chromium-family --app detection →
browser tab fallback; starts the service if down); wizard done-screen leads
with "open your companion", OWUI section demoted to optional; panel has
dashboard/chat shortcuts; main desktop icon now launches the app; README +
getting-started rewritten standalone-first.
- ✅ Wizard done-screen: the four OWUI cards collapse to one — "open your companion at http://127.0.0.1:8765"; panel gets a chat/dashboard shortcut
- ✅ **Native app window**: `game-companion app` (and the "Gacha Companion" desktop icon) opens the UI in a real window — detection order per D6: `chromium/brave/edge --app=` (chrome-less window, zero new deps) → normal browser tab; pywebview stays optional-only (WebKit2GTK system deps are the fragility we avoid)
- ✅ README/getting-started rewritten: install → open → talk; OWUI moves to an "optional: chat from Open WebUI" doc section (tool file stays maintained)
- ✅ Acceptance criteria re-rehearsed end-to-end without OWUI (profile → roster import → chat Q&A → screenshot confirm → codes → exports → persistence)
- ✅ Real-user pass on a second machine (the buddy) with zero Open WebUI steps

## Milestone 24 — Adapter workbench (new games + cross-game naming)

DONE 2026-09-24. terminology.json per adapter (contract-tested REQUIRED_KEYS)
injected into chat prompts via `terminology_block()`; resource `category`
taxonomy (Polychrome/Stellar Jade/Annulith all `pull_currency`);
`game-companion new-game` scaffold (contract-ready package + installed.json
plugin registry); `game-companion bootstrap-game` (fetch → transform → pending
change records with provenance, `--apply` writes provenance-tagged files under
`<data_dir>/bootstrap/`); HSR adapter real (relic+ornament families, StarRailRes
bootstrap); NTE adapter real (Cartridge module_combo family, Arc/Awakening/
Annulith terms — research items marked [verify] in terminology notes).

## Milestone 24 — Adapter workbench (new games + cross-game naming)

Design basis: `docs/game-adapters-research.md` (ontology mapping for
ZZZ/HSR/NTE, currency table, source assessment, bootstrap pipeline).

- ✅ `game-companion new-game <id>` scaffolding command: adapter package skeleton with terminology (`terminology.json`, generic defaults pre-filled — design §5), team/gear/resource/progression rules, encounter modes, screenshot specs, prompts, source registry, and starter-data placeholders carrying honesty markers
- ✅ Adapter data files get the provenance `_meta` block (source URL + fetched_at + review status — design §7); `terminology.json` and `gear_families.json` land with the ZZZ adapter first, covered by the contract suite (required ontology keys present), then every new adapter inherits them
- ✅ `game-companion bootstrap-game <id> --source auto|prydwen|hakush|starrailres`: fetch → transform → stage as pending change records (M19 review flow); every datum provenance-tagged (source URL + fetched_at); contract tests must pass before activation; weekly `check-sources` re-diff so upstream changes arrive as reviewable updates
- ✅ Terminology-table injection in chat prompts: system prompt teaches the generic ontology once, adapter table maps it to game names (equipment = Light Cone, duplication = Eidolon, pull currency = Stellar Jade…), so the model speaks each game's language with no per-game prompting hardcoded in the core
- ✅ Resource taxonomy: categories (pull_currency, pull_ticket_limited/standard, money, stamina, standard_material) + per-adapter display names, so ZZZ Polychrome and HSR Stellar Jade both surface as "premium pull currency" in views and chat while keeping their game-native names
- ✅ Generalized adapter contract-test harness: run the zzz/example contract suite against any new adapter out of the box
- ✅ Prove the workbench by building the second real adapter (Honkai: Star Rail) through it — data via StarRailRes/StarRailStaticAPI or hakush.in JSON
- ✅ NTE adapter (third): bootstrap from Prydwen (prydwen.gg/neverness-to-everness — Characters, Arcs, Cartridges, banners, game modes); confirm the open items listed in the research doc §5 (Cartridge/Module gear split, role + Esper-attribute names, endgame modes, stamina name)

## Done post-M24 (2026-09-24): on-the-fly model handling + Database page
- ✅ LLM settings live in the app: `GET /api/llm/status`, `GET /api/llm/models` (auto-populated from the endpoint's /models; accepts base/key to test a NEW endpoint before saving), `PUT /api/llm/config` — writes .env (same file the wizard uses) and **hot-swaps the running client, no restart**; tri-state vision detection (auto from model id / manual override); Settings → "Assistant model" card with status dot, model dropdown, test-endpoint button
- ✅ Vision guard: screenshot imports refuse a non-vision model with a clear "pick a VLM in Settings" message (bypassable via override); Imports page shows a warning chip when the current model may not read images
- ✅ Database page (`/ui/database`): character dropdown → full editable record (basics, game-details dropdowns fed by adapter `character_field_choices()`, skills, notes) with save-marks-verified; create-new; provenance line (source + last verified) for review-for-accuracy
- ✅ "Game data updates" card on the Database page: one button checks online sources (check-sources + bootstrap staging) and lists pending changes with Approve/Reject — the M19 review flow is now visible in the UI; ZZZ bootstrap source added (hakush.in, shape-tolerant transformer, tested offline)
- ⬜ Follow-ups: NTE bootstrap (no stable API yet — Prydwen fetcher), gear/weapon list auto-update (hakush has weapon data; needs a transformer), SSE chat streaming

## Done post-M26 (2026-09-25): full UI consolidation pass — chat-first Home, 14 → 9 nav

Directive: "move the chat to the dashboard, that will likely be the primary interactor.
Also lets do a full UI and app pass for ease of use, what can be neatly consolidated."

- ✅ **Home is chat-first** (`/ui`): conversations sidebar + message log + composer +
  persona picker ("Speak as") are the main column; compact account snapshot on the right
  (stat cards, active team, resources with status chips, recent results, shortcuts incl.
  "What should I farm?"); `/ui/chat` redirects to `/ui` (conversation preserved); all chat
  POST actions return to Home. Live-verified end-to-end in the browser (message → tool
  loop → real LLM answer). Old chat.html template removed. `.home-layout` grid CSS added;
  stylesheet link cache-busted (`?v=2`) so users' browsers pick up CSS changes
- ✅ **Trackers page** (`/ui/trackers`): Resources + Codes + Combat history as three
  sections on one page; `/ui/resources` `/ui/codes` `/ui/history` redirect there (setup
  guard preserved); POST actions (set resource, refresh codes, mark code used) return to
  the right section. `_redirect` now keeps `#fragment` anchors at the end of the
  Location URL
- ✅ **Database page dissolved**: the rich per-agent editor (basics, game-details
  dropdowns, skills, provenance, save-marks-verified) IS the Agents page editor now
  (`/ui/roster/{key}/edit` handles everything the old two editors did — one editor, one
  save route); manual agent creation folded into the Agents page ("create it manually"
  fold → `/ui/roster/create`); the reference-catalog panel, source-runs table, "Check
  online sources now" and the pending-changes Approve/Reject review live on the **Games**
  page (`/ui/games#data`; routes moved to `/ui/games/data/check-updates` and
  `/ui/games/data/changes/{id}/approve|reject`); `/ui/database` redirects to Games
- ✅ **Nav 14 → 9**: Home · Agents · Teams · Inventory (was "W-Engine & Drive Disc") ·
  Farm Plan · Trackers (was Resources+Codes+History) · Import · Games · Settings.
  Personas leave the nav — reachable from the Home chat sidebar and a Settings card
- ✅ Housekeeping: dead templates removed (chat/database/resources/codes/history);
  stale "Database page" links across templates point to Games#data; "new agentss" grammar
  bug fixed in the Games data section
- Tests updated to the new surface (trackers/game-data routes, roster rich editor,
  /ui/chat redirect) — **225 passed, 1 skipped, ruff clean**; GUI pass on Home (chat
  live), Trackers, Games, Agents in the browser

## Done post-M26 (2026-09-25): example game hidden from users

- ✅ "Aether Tactics (Example)" no longer appears anywhere user-facing: game picker,
  Games page, Settings, /api/health, /api/games, list-games CLI, scheduler. It stays
  registered for the contract-test suite (core genericity proof) — direct API access
  still works; `GameAdapter.hidden` flag + `list_adapters(include_hidden=)` filtering;
  `ui/state` keeps hidden games resolvable so an existing state file or direct switch
  never breaks. Regression test asserts hidden-from-listings + direct access works —
  **226 passed, 1 skipped, ruff clean**

## Done post-M26 (2026-09-25): vision auto-probe + built-in web search (chat tools)

Directive: broker "auto" model routes to a vision LLM but the tool couldn't see that;
"need better search, native/browser or self-contained — dummy simple, works out of the
box for anything gacha."

- ✅ **Vision probe** (`LLMClient.probe_vision`): the name heuristic is now only the
  first guess — when it says no, the app sends a real 1px image to the endpoint once
  (cached per client, hot-swapped with settings). Broker auto-routing that accepts
  images is never blocked; a model that clearly refuses the probe gets the friendly
  "refused a test image" message; probe network/5xx errors fall through so the real
  extraction surfaces the honest error. Manual override still short-circuits everything.
  Settings chip now says "vision: auto-tested on upload" for auto models instead of a
  false "no vision". Also fixed a latent seam bug: hot-swapped clients read the test
  transport from the wrong object (`app.llm_transport` → `app.state.llm_transport`)
- ✅ **Built-in web search, zero config**: research provider chain = SearXNG when set
  → **DuckDuckGo HTML provider** (no key, no setup; parses and unwraps DDG's redirect
  links) → honest error if nothing answers. Works out of the box
- ✅ **Chat tools** `search_web` + `read_page`: the Home-chat assistant can now look
  up new characters/patch info itself and read the pages before answering (tools
  return honest errors to the model; read_page only accepts http(s)). Live-verified:
  real DDG results for "zenless zone zero 3.2 new agent" from the tool path
- Tests: probe accept/refuse/once/override, DDG parsing + link unwrapping, provider
  chain ordering, chat tool execution — **235 passed, 1 skipped, ruff clean**
- Note: the broker (llm.tictac.one) was returning transient 503s during the live check;
  probe errors are handled gracefully (fall through, honest extraction error)

## Done post-M26 (2026-09-25): delight pass — The Hall, deep themes, achievements, sounds

Directive: LLM fills in data + fun/rewarding (sounds w/ volume control, achievements,
a page to marvel at the team, deep per-game theming incl. icons/W-Engines/discs/banner
characters, build tracking, animations) — all "in a clean way that doesn't crowd pages".

- ✅ **Media URL hooks** (`GameAdapter.media_url(kind, key)`) with live-verified CDN
  patterns: ZZZ = Prydwen CDN (characters/<slug>.webp, w-engines/<slug>_image.webp,
  drives/set_<slug>.webp, icons/ele_<element>.webp); HSR = StarRailRes raw GitHub
  (avatar/<id>.png, light_cone/<id>.png); NTE = styled monogram fallback (no verified
  pattern — honest None); example = None
- ✅ **Deep theming**: theme() gained bg/bg2/card/radius/mood; page backdrop gradient
  per game (ZZZ warm "New Eridu after dark", HSR starfield "Aboard the Astral Express",
  NTE "Signals from the Fair"); corner-radius language per game; cache-bust bumped
- ✅ **The Hall** (`/ui/hall`, nav between Agents and Teams): owned agents as portrait
  cards (rarity glow for S, level/dupe chip, element icon + specialty badge, favorite
  star), **build-at-a-glance strip per card** (equipped W-Engine icon + disc set icons +
  "N empty"), active team lineup section, "Fresh faces in the catalog" strip (newest
  catalog characters = the banner-characters ask, honestly labeled), achievements shelf;
  cards hover-lift and stagger-fade in (prefers-reduced-motion respected); click →
  agent editor
- ✅ **Achievements** (`core/achievements/service.py` + migration `d5e7f9a1c3b6`):
  10 honest milestones computed from the player's own data (first recruit, full house,
  legend collector, trust verified, auditor, disc hoarder, dressed for battle, build
  complete, code hunter, first clear); unlock rows recorded with timestamps; unlock
  toast (auto-dismissing, sparkle sound) rendered on next page visit
- ✅ **Sounds** (`delight.js`, vendored, WebAudio-synthesized — no assets): tick on
  success notices, chime/sparkle APIs; **volume slider + Test button in Settings →
  "Sounds & delight"** (per-browser localStorage, 0 = silent); respects
  prefers-reduced-motion
- Tests: media URL patterns, themes carry mood/backdrop, Hall rendering with real
  portraits + equipped gear icons, achievement unlock/once-only flow, migration
  roundtrip — **242 passed, 1 skipped, ruff clean**; GUI-verified on the live service

## Done post-M26 (2026-09-25 later): game-look pass — fonts, codes UX, confetti, inventory fix

User: inventory tab broken; codes page bad UI (expired should hide behind a toggle);
wants confetti of the game's currency on redeem; theming "nowhere near" — mirror the
games: game fonts, game assets.

- ✅ **Inventory crash fixed**: a disc with a main stat but no recorded value crashed the
  page (`{value:g}` on None) — display is now defensive
- ✅ **Game fonts, vendored** (OFL, ~70KB woff2 total in static/fonts): ZZZ = Saira
  Condensed (uppercase italic headings/buttons — the ZZZ punch), HSR = Poppins, NTE =
  Chakra Petch; theme() gained `font`, wired as `--font-display`; body text stays
  system for readability
- ✅ **Deeper shape language**: per-game card borders (ZZZ orange left edge, HSR teal
  top edge), ZZZ uppercase letter-spaced buttons/nav, per-game radius already in
- ✅ **Codes UX rebuilt** on Trackers: active codes as cards (big code, one-click
  **Copy**, reward notes, expiry), used codes behind a "Redeemed (n)" toggle,
  **expired hidden behind an "Expired (n)" toggle** (user: shouldn't show by default)
- ✅ **Redeem celebration**: marking a code used now shows a notice with the game's own
  currency name ("ZZZVOID32 redeemed — enjoy the Polychrome!") and delight.js rains
  ~90 currency-colored confetti pieces down the screen for ~1.4s with a pop sound
  (theme() gained currency + currency_colors per game; prefers-reduced-motion and
  volume=0 both silence/skip it); Copy buttons pop too
- Tests: codes grouping + copy button + redeemed notice + currency name —
  **243 passed, 1 skipped, ruff clean**; GUI-verified on HSR live

## Done post-M26 (2026-09-25 night): real game palettes, backdrops, currency icons

User feedback on v1: "standard confetti — I want stellar jades/polychrome to fall";
fonts better but not game-specific; palettes still bad — "search online, see what the
games look like in menus".

- ✅ **Researched the real identities** via Prydwen's own compiled CSS (their per-game
  themes mirror the games): ZZZ = near-black neutral (#0f0f13/#1e1e24/#2d2d35) with
  signature red #ed343e + stun yellow #ffc000 (the orange was wrong); HSR = deep-space
  navy with warm gold #c9a36a + purple #8a5fcc (the periwinkle was wrong); role colors
  ed343e/c267ec/ffc000/7cde97 noted for future role chips
- ✅ **Real game backdrops**: theme() gained bg_image — Prydwen mirrors official-style
  full-page backgrounds (zenless-zone-zero/star-rail website_bg.webp, both 200); body
  renders image under a readability gradient overlay; header/cards get subtle blur;
  NTE has no verified backdrop (gradient fallback, honest)
- ✅ **Real currency confetti**: user supplied the Polychrome (u7buy) and Stellar Jade
  (HSR wiki) icon URLs; Annulith found via the NTE fandom wiki images API
  (neverness-to-everness.fandom.com); all three vendored locally
  (static/images/currency/*.webp) so celebrations work offline; delight.js now rains
  the actual item images (falls back to drawn shapes if an image ever fails)
- ZZZ font de-italicized (the game's UI is upright condensed)
- Tests 243 passed, 1 skipped, ruff clean; confetti visually verified mid-fall on ZZZ

## Done post-M26 (2026-09-25 late night): live banners, game logos, unified Home rail

User feedback: the right-hand "long bar" of stacked cards didn't fit; wanted an
achievements-at-a-glance section, game logos on pages, and "banners on the homepage
of whoever is live currently"; mid-turn added "make the right bar clickable — codes
box goes to codes, etc".

- ✅ **Live banner hero (all three games)**: new `prydwen_banners` catalog source per
  game (zenless/banners, star-rail/banners, neverness-to-everness/banners) feeding a
  `banner` entity; shared `parse_banners()` in core.games.prydwen reads the
  server-rendered banner-card markup (section current/upcoming, kind character/weapon,
  new/rerun/collab, NA-server start/end ISO stamps, phase, art URL, featured rate-ups).
  One row per banner run (key = slug + start date) so reruns are new rows; undated
  "teased" cards are skipped honestly, never guessed
- ✅ **Home rail rebuilt as one panel** (`.rail`): game logo + name, banner hero
  (art, NOW ON BANNER, type chip, Ends date, featured, next-up line, honesty caption
  "Banner windows from Prydwen · community data · NA server dates"), a 2×2 stat grid,
  then hairline-divided sections. **Every section is a real link** — stats → roster/
  inventory, codes stat → Trackers#codes, team → Teams, resources →
  Trackers#resources, results → Trackers#history, achievements → The Hall (Shortcuts
  keep their buttons; can't nest links)
- ✅ **Achievements at a glance on Home**: `check_and_unlock` runs on Home too; rail
  shows "n of 10 earned" plus a medal row (lit = earned, dimmed = locked, hover for
  name + description), linking into the Hall shelf
- ✅ **Game logos**: pulled each wiki's official site logo via the fandom images API
  (ZZZ white mark, HSR wordmark, NTE dark emblem — vendored
  static/images/logos/*.webp; NTE ships a `logo_filter` invert so the dark emblem
  reads on the dark theme). Shown in the Home rail brand, The Hall header, and every
  Games card
- ✅ **Scheduler cadence split**: banner sources refresh every 6h (they rotate
  mid-patch; Home shows them as live) while the rest of the catalog stays weekly —
  `CatalogService.refresh(skip_entities=)` keeps the two cadences from double-fetching
- Hero pick ranks new banners above reruns in the same window (HSR was showing
  Ashveil's rerun over Aventurine Waveflair's debut)
- Tests: banner fixture captured from the real page (current/weapon/upcoming/teased),
  per-game source + transform tests, banner-cadence scheduler test, Home rail/hero/
  achievements integration tests, vendored-logo theme tests — **252 passed, 1 skipped,
  ruff clean**; GUI-verified live on all three games (ZZZ Claret, HSR Aventurine
  Waveflair, NTE Linko heroes; logos render everywhere; codes stat lands on
  Trackers#codes)

## Done post-M26 (2026-09-25 later night): hero split, art at native ratio, NTE/HSR data fixes

User feedback round 2: rail banner too small → made it full-width; then "too big, and
our text shouldn't sit over the banners"; plus "fit them at original aspect ratios";
the page still looked lopsided; NTE agents had no portraits; HSR "fresh faces" showed
six identical {NICKNAME} trailblazer placeholders.

- ✅ **Split hero**: full-width strip = solid info panel (label, name, type chip, ends
  date, phase, featured, "Also live" list, next-up, Prydwen caption) on the left +
  banner key visual on the right with **no text over the art and no cropping** — the
  image renders whole at its own aspect ratio (ZZZ 16:9 landscape, HSR/NTE portrait
  key visuals) inside an accent-tinted backdrop, centered, capped at 16rem
- ✅ **Rebalanced Home**: banner moves out of the rail to span the page; Shortcuts +
  last-import move into the left chats column (pinned to its bottom); rail keeps
  logo/stats/achievements/team/resources/results — all three columns now end at
  roughly the same height instead of a short chat and a giant bar; the chat welcome
  card and chat log stretch to fill
- ✅ **NTE agents**: adapter had no media_url — Prydwen's NTE art lives at
  `cdn.prydwen.gg/images/nte/characters/<slug>_card.webp` (verified 200); Hall now
  shows real portraits
- ✅ **HSR placeholders**: StarRailRes ships ten trailblazer rows named `{NICKNAME}`
  (8001–8010); the transform now skips any name containing `{` (they're the player,
  not a character), the Hall guard filters them from "Fresh faces", and the ten stale
  rows were purged from the live DB
- Tests 253 passed, 1 skipped, ruff clean; GUI-verified hero + balance on all three
  games and both Halls (NTE portraits, HSR real fresh faces)

## Done post-M26 (2026-09-25 late): banner lightbox + design sweep across all pages

User: "clicking the banner image for a full size preview would be nice; the new
homepages look nice — filter that back through all the rest of the pages."

- ✅ **Full-size banner preview**: every ``img[data-lightbox]`` opens a fullscreen
  overlay (blurred dark backdrop, image contained at native size, ✕ button, click
  anywhere or Esc to close, ``gcLightbox`` exposed) — shipped in delight.js v4 and
  wired to the Home hero art with a zoom-in cursor + "Click to view full size" hint
- ✅ **Design sweep**: every page head now follows the Home/Hall pattern — game logo
  (with NTE's invert filter) + title anchored left, page actions stay right
  (roster/teams/gear/farm/trackers/imports/games/settings/personas/personas-pages/
  audit/character_edit); section ``h2``s render as uppercase small-caps with a short
  accent underline; table headers get an accent rule; cards adopt the Home rail's
  translucent blurred panel look; buttons render in the game display font with a
  subtle hover lift; ``main`` fades in per page (reduced-motion safe)
- Tests: hero ``data-lightbox`` + asset-version assertions, per-page logo-head check
  across all nine routes — **255 passed, 1 skipped, ruff clean**; lightbox and the
  swept pages verified visually on ZZZ (Agents, Farm Plan, Trackers, Settings)

## Stretch (post-standalone)
- ⬜ Tutor UI polish in the chat page (step-by-step mode views)
- ⬜ Codes auto-discovery wiring (parser over watched sources)
- ⬜ Mobile-friendly layout
- ⬜ Packaged distribution (single .deb/AppImage bundling service + window) — only if the audience outgrows "him + me"

## Known follow-ups (not blockers)
- ZZZ starter data (agent roster metadata, caps, set list) needs verification against in-game values or the research layer
- Drive-disc set effects (2pc/4pc) intentionally not encoded until verified data exists
- Automatic redeem-code discovery wiring (parser over watched sources)
- Optional: schedule `check-sources` via systemd user timer

## Done post-M24 (2026-09-24): full self-containment — reference catalog + auto codes (M25)

Directive: "Nothing should be added via CLI… codes should be automatically pulled
and refreshed daily… automatically import all available agents, light cones,
w-engines… personas should be able to be told 'I want Jane Doe'… in-app way to
manage games."

- ✅ **Reference catalog** (`game_catalog` table + migration `c8f4a2b6d9e1`): every standard entity per game (character / equipment / gear_set) with name, rarity, categories, provenance (`source`, `fetched_at`). Fed by new adapter hooks `catalog_sources()` / `catalog_transform()`; live results: HSR 97 characters + 169 light cones + 60 relic sets (StarRailRes), NTE 24 characters (Prydwen), **ZZZ 64 agents + 101 W-Engines (Prydwen /zenless — user spotted the path after I wrongly concluded Prydwen dropped ZZZ; hakush demoted to the review-gated bootstrap flow only)**. Refresh prunes run rows of removed sources
- ✅ **Codes auto-pulled, daily** (`source_runs` table): new adapter hooks `codes_source()` / `codes_transform()`; ZZZ codes live from zenlesscodes.com's hourly-aggregated JSON API (134 real codes pulled on first run), NTE from Prydwen's codes page (12 codes, fixture-tested parser). Codes page: no more manual add form — shows source, last-checked time, failure reason, "Refresh now"; player used-state survives status flips (active→expired keeps your ✓). HSR codes too: Prydwen renders them on the game hub itself (user spotted it; there is no /codes subpage) — shared `core/games/prydwen.py` parser used by NTE + HSR, expired-section header aware
- ✅ **Background auto-refresh**: lifespan task (codes >24h stale → refresh; catalog >7d → refresh), all games, failures logged + recorded, never fatal; `GAME_COMPANION_AUTO_REFRESH=0` disables (tests)
- ✅ **Catalog-driven creation**: Agents page "Add agent" = pick from catalog (+optional level/Mindscape) — name/rarity/attribute prefill; Database "New agent" same; Inventory "Add W-Engine/Light Cone" = catalog dropdown + level/refinement/owner; "Add drive disc/relic" form with set/slot/main-stat dropdowns fed by adapter data. Empty states now point at "Import catalog now", never the CLI
- ✅ **Games management page** (`/ui/games`): every installed game as a card — catalog counts, codes freshness/status, per-game "Import catalog" / "Refresh codes" / "Switch", plus in-app "Add a new game" (scaffold + plugin-register, no terminal); nav entry added
- ✅ **Personas**: "Speak as <character>" — one click from the catalog creates a role-play persona ("I want Jane Doe" → done); full editor has a role-as dropdown; system prompt keeps the honesty rule in character ("the character never invents data about the user's account")
- ✅ Catalog JSON API: `GET /api/games/{id}/catalog`, `POST /api/games/{id}/catalog/refresh`
- ✅ Fixed: HSR bootstrap URL (404 `characters/new.json` → verified `characters.json`); Jinja `dict.items` collision in source-runs table; pluralization chips ("169 equipments" → "169 equipment", "Agentss" → "Agents"); article grammar in dynamic headings; roster/resources empty-state CLI references removed
- Tests: 20 new (parsers against captured live fixtures, service upsert/runs, used-state preservation, scheduler staleness, all UI flows, scaffold monkeypatched) — **185 passed, 1 skipped, ruff clean**
- ⬜ Still open: gear/weapon transformers for bootstrap; SSE chat streaming

## M26 (2026-09-25): Drive Disc farm planner — "what should I farm next?"

Directive: answer "given the current meta, my roster, and the actual quality of the
Drive Discs I own, which set or Area Patrol stage should I farm next?" — demand-weighted,
never equal quantities per set, with the full data-honesty label regime.

- ✅ **Meta dataset** (`games/zzz/data/drive_meta.json`, CURRENT BUILD DATA): 42 meta agents
  (T0 12 / T0.5 15 / T1 15, Prydwen tier list + per-agent build pages, retrieved 2026-09-25
  at patch 3.2; per-agent `build_patch` stamps — e.g. Alice's build last touched 2.1).
  Weighted build variants normalized so each agent demands exactly 4× 4pc + 2× 2pc pieces
  in expectation ("2 pieces, not 6"); 4pc families use Prydwen usage percentages, 2pc
  options use rank decay 1.0/0.7/0.5/0.35/0.25 (HEURISTIC, flagged); slot IV/V/VI mains
  parsed from Prydwen preference strings into ordered rank groups; substat priorities kept
  raw + best-effort parsed; 15 team archetypes (w=1.0 MVP) from calc teams. Roxy and all
  unreleased agents excluded by policy
- ✅ **Farm stages** (`farm_stages.json`): all 12 Area Patrol stages (60 battery, two sets
  each) with names + adding versions (Fandom change history, corroborated by u7buy + a
  third source for the 2.5 stage "Deceits and Bulwarks"). Stage drop split = even 50/50
  ASSUMPTION (no official rates)
- ✅ **Set catalog** (`drive_disc_sets.json`): extended 15 → all 30 current sets with
  2pc/4pc effect text, `farmable`, `farm_stage` backrefs. 24 farmable; 6 event/shop sets
  (incl. Thorned Rose — Claret's best 4pc) show "event/shop" in the Farm column instead of
  a farming recommendation
- ✅ **Generic core** (`core/farm/service.py`): demand D_s, physical need P_s (primary
  build, once per agent), target T_s=⌈β×P_s⌉ (β ∈ 1.0/1.2/1.3/1.5, player-chosen),
  effective inventory (quality credits), coverage C_s, pressure
  F_s = demand_share × max(0,1−C_s) × scarcity B_s, stage aggregation. Zero game
  vocabulary (isolation-tested)
- ✅ **ZZZ glue** (`games/zzz/farm.py`): 5-step disc grading (unusable 0 / placeholder .5 /
  good .75 / strong .9 / finished 1.0; A/B-rank HEURISTIC ceilings; wrong-main-for-slot =
  unusable; setless = unranked), scarcity boosts (severe V 1.5 when users need elemental
  slot-V mains; severe IV/VI 1.3; meaningful 1.2), per-set bottleneck slot, plan assembly
  with full provenance
- ✅ **Verified-mechanic corrections**: slot main-stat pools fixed (starter data had CRIT
  in slot V, missed it in IV; IV = HP%/ATK%/DEF%/CRIT Rate/CRIT DMG/Anom Prof, V = + PEN
  Ratio + elemental DMG, VI = + Anom Mastery/Energy Regen/Impact); elemental dmg stats
  added (wind_dmg flagged UNKNOWN-NEEDS DATA from Prydwen 3.2); "armorer" + "wind" added
  to terminology; gear_families.json pools aligned to the verified pools + stat keys
- ✅ **UI** `/ui/farm` + nav: SET | DEMAND | NEED | TARGET | EFFECTIVE | COVERAGE |
  BOTTLENECK | FARM table (sorted by pressure), stage ranking with "farm next" badge,
  β selector chips, labels legend + provenance footer (source, patch, retrieved date);
  graceful "Not available for this game yet" card for games without a dataset (HSR/NTE)
- ✅ **API**: `GET /api/games/{id}/farm-plan?beta=`; `available: false` payload when the
  adapter has no meta data; new adapter hooks `farm_stages()`, `gear_meta()`,
  `grade_gear()`, `build_farm_plan()` (default no-op)
- Tests: 32 new (core math on synthetic units, grading rules, dataset invariants —
  q-sums, set references, stage consistency, verified pools —, API + UI flows) —
  **223 passed, 1 skipped, ruff clean**; GUI-tested in the browser (β switch recomputes
  targets 8→9 at β 1.5, game-switch fallback renders)
- ✅ **Granny-simple pass (same day, user: "just basic boxes to fill in or select, all the
  hard part behind the scenes")**: page rebuilt around two plain dropdowns — "Plan for:
  My agents / Everyone in the meta" (roster-scoped demand is now the DEFAULT; falls back
  to full meta with a visible note when no owned agent is in the dataset) and "Spare gear:
  Just what I need / A comfortable margin / Lots of spares" (β 1.0/1.2/1.5 in plain words;
  1.3 dropped from the UI, API still takes any beta) — plus one Update button. Output is a
  single verdict card ("Farm this next: <stage> — drops <set>, the set you need most here")
  with a pointer to the biggest single gap when it lives elsewhere, a word-scale list
  (none yet → a good start → getting there → almost there → covered), and runner-up
  stages. All numbers, labels, and provenance moved into a collapsed "Show the details"
  fold. `build_farm_plan` gained `unit_keys` roster filtering (underscore/hyphen
  normalized) + `plan.scope` reporting; API accepts `scope=mine|meta`
- ⬜ Still open: refresh pipeline for the meta dataset (currently generated artifacts +
  documented builder steps; a new patch needs a re-run), drop-rate learning to replace the
  even-split assumption, assignment solver (explicitly deferred by spec)

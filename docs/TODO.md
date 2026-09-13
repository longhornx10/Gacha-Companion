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

## Known follow-ups (not blockers)
- ZZZ starter data (agent roster metadata, caps, set list) needs verification against in-game values or the research layer
- Drive-disc set effects (2pc/4pc) intentionally not encoded until verified data exists
- Automatic redeem-code discovery wiring (parser over watched sources)
- Optional: schedule `check-sources` via systemd user timer

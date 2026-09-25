# Standalone UI — Design (Milestones 20–24)

Design decisions locked with nick on 2026-09-23. This document is the
implementation contract for M20–M24; the TODO carries the checkboxes, this
carries the "how" and the "why". Companion research lives in
`docs/game-adapters-research.md`.

---

## 0. Decisions (locked)

| # | Decision | Choice |
| --- | --- | --- |
| D1 | UI stack | Server-rendered **Jinja2 + htmx** (vendored, offline) + minimal vanilla JS. No Node, no build chain. |
| D2 | Hosting & auth | Same FastAPI process; pages under `/ui`; 127.0.0.1-only, **no auth for v1**. Threat model: any local process can read/modify the DB — explicitly accepted for a personal tool. Wizard/panel keep their token guards. |
| D3 | Chat streaming | **Non-streaming for v1** (request → tool loop → full reply). SSE is post-v1 polish. |
| D4 | Gear families | Add `gear_type` to gear items; families declared per adapter. Research covers ZZZ/HSR/NTE (§4). |
| D5 | Game switching | Switching game switches **everything**: theme, persona, conversations, and every list view (§2). |
| D6 | Native window | `chromium/brave --app` detection → plain browser tab fallback. pywebview dropped from the critical path (avoids GTK/WebKit system deps). **Linux-only for v1.** |

## 1. UI architecture

- One process: the existing service serves both `/api/*` (JSON, unchanged —
  stays for programmatic use and tests) and `/ui/*` (HTML pages + fragments).
- Templates: `game_companion/ui/templates/` (Jinja2, new dependency — small,
  pure-Python). Fragments live next to their page template.
- Interactivity: vendored `htmx.min.js` (single static file, no CDN — the app
  must work offline). Vanilla JS only where htmx doesn't fit (clipboard copy
  buttons, report builder — pattern already proven in setup-gui).
- Static assets: `game_companion/ui/static/` (css, htmx, per-game art if any).
- Page inventory (M20 builds the shell + dashboard only):

    /ui                  dashboard
    /ui/roster           list + detail (+ build editor, M21+)
    /ui/teams            teams, activation, gap advice
    /ui/gear             gear list + filters (family-aware, §4)
    /ui/resources        counters + plan thresholds
    /ui/codes            codes with strikethrough/status
    /ui/imports          screenshot upload + import review (M21)
    /ui/chat             conversations (M22)
    /ui/settings         players, personas, sources/provenance, backups, updates

- No auth (D2); the app refuses non-loopback binds (`--host` abuse rejected)
  unless an explicit `GAME_COMPANION_EXPOSE=1` env is set, which also forces a
  token requirement — a tripwire, not a feature.

## 2. Game switching — "switch everything" (D5)

- **Active game** is stored per profile: `PlayerPreference(scope="global",
  key="active_game", value="zzz")`. Default `zzz`. All `/ui` pages read it;
  every list filters by it (the DB is already fully game-scoped).
- **Theme**: each adapter ships `theme.json` — `{name, accent, accent2, bg?}`.
  The base layout renders it as CSS custom properties (`--accent` etc.), so
  switching to HSR re-colors every page. Theme swap = plain redirect (htmx
  boosting can come later).
- **Persona**: `PersonaConfig.bound_game` already exists. The persona editor
  groups by game; the chat system prompt picks the persona bound to the active
  game, falling back to the global default. Switching games switches persona.
- **Conversations**: `conversations.game_id` — the chat page lists only the
  active game's conversations.
- **Switcher**: a top-bar select on the base layout → `POST /ui/active-game` →
  redirect back. One control, everything follows.

## 3. Chat (M22)

**Tables** (Alembic migration, after M20's backup/restore exists):

    conversations: id, player_profile_id FK, game_id, title, persona_id,
                   created_at, updated_at
    messages:      id, conversation_id FK, role(user|assistant|tool),
                   content TEXT, tool_calls JSON, tool_call_id,
                   created_at
    companion_memories: id, player_profile_id FK, game_id (nullable = all
                   games), content, source(manual|auto), active BOOL,
                   created_at

**Tool loop** — server-side, in-process, non-streaming (D3):

1. Insert user message.
2. Loop (max 6 iterations): build messages (system block, then history) →
   `LLMClient.complete()` with tool schemas → if tool calls: **execute against
   core services directly in-process** (never HTTP-calling our own API) →
   append `tool` messages → repeat.
3. Persist every step (including tool calls/results) for auditability.
4. Final assistant message returned whole (D3); the UI shows a "thinking"
   state while the loop runs.

**System prompt composition** (in order): data-honesty rules → terminology
block (§5) → persona fragment (game-bound persona) → companion memories
(active, matching game or global) → current active-game context.

**Chat tools v1** = the operations the OWUI tool exposed, as direct service
calls: roster lookup, team advice, resource status, codes, exports, research
query, screenshot import confirm.

Context trimming: last 20 messages + one summary line of what came before.
Honesty rules unchanged: tool results are the only source of account facts.

## 4. Gear families (D4) — migration before M21's UI

**Migration** (M21, first step): `gear_items.gear_type` String(40) nullable →
backfill existing ZZZ rows to `'disc'` → `NOT NULL` in a follow-up revision.
Existing slot/substat/set columns stay as-is — they fit every family below.

**Adapters declare families** in `games/<id>/data/gear_families.json`:

    { "key": "disc", "display": "Drive Disc", "slot_count": 6,
      "slots": [{"key": "1", "display": "I", "main_stat_pool": ["hp"]}, ...],
      "set_rule": "fixed_pieces",      // fixed_pieces | module_combo
      "set_sizes": [2, 4],
      "rarity_scale": "SAB",           // SAB | stars5
      "max_level": 15, "max_substats": 4 }

The three games, per research:

| | ZZZ **Drive Disc** | HSR **Relic** | HSR **Planar Ornament** | NTE **Cartridge** |
| --- | --- | --- | --- | --- |
| slots | 6 (I–III fixed mains: flat HP/ATK/DEF; IV–VI pooled) | 4 (Head=flat HP, Hands=flat ATK, Body/Feet pooled) | 2 (Sphere, Link Rope) | piece count TBD at build |
| set rule | `fixed_pieces`, sizes [2, 4] | `fixed_pieces`, sizes [2, 4] | `fixed_pieces`, sizes [2] | **`module_combo`** — the set bonus comes from a 4-Module combo on the piece, not across slots |
| rarity | S/A/B | 5★/4★ | 5★/4★ | B/A/S |
| max level | 15 | 15 | 15 | TBD |

NTE's `module_combo` rule is why `set_rule` is adapter data rather than a core
assumption: NTE inverts ZZZ/HSR (set identity lives on the piece via Modules,
not across equipped pieces). Modules for v1 live inside `GearItem.data` JSON
(list of 4 module entries); a separate `module` gear family is added only if
module *inventory* tracking becomes a real need. Set/scoring logic stays in
the adapter, where it already lives.

## 5. Terminology — the cross-game spine

`games/<id>/terminology.json` maps generic ontology keys to game vocabulary:

    { "character":  {"display": "Agent", "gloss": "Playable unit you own"},
      "equipment":  {"display": "W-Engine", "gloss": "Signature weapon"},
      "gear":       {"display": "Drive Disc", "gloss": "Set-based gear with substats"},
      "duplication": {"display": "Mindscape", "gloss": "Dupe system, M0–M6"},
      "pull_currency": {"display": "Polychrome", "gloss": "Premium pull currency"},
      ... one entry per ontology key + currency category ... }

- Loader builds a `terminology_block(adapter)` — the "speak this game's
  language" prompt text. `PersonaConfig.system_prompt_fragment()` already
  accepts a `terminology_line`; the chat system prompt includes the block.
- Contract test: every required ontology key present per adapter (add to the
  existing adapter contract suite).
- M24's `new-game` scaffold emits a skeleton terminology.json with the
  generic defaults pre-filled, so a new game starts speakable.

## 6. Resource taxonomy

No DB change: `Resource.resource_key` plus an adapter data file
`resources.json`: `{resource_key: {display, category, thresholds?}}`.

- `category` ∈ `pull_currency | pull_ticket_limited | pull_ticket_standard |
  money | stamina | standard_material` — this is how ZZZ Polychrome and HSR
  Stellar Jade both surface as "premium pull currency" (see
  game-adapters-research.md for the full three-game currency table).
- `thresholds` powers the manifesto's EXACT color rules on the dashboard
  resource card: critically-low = red, very-low (225–234) = orange,
  done = white, prep = cyan-lime — as *data*, evaluated deterministically
  (same rule as the existing resource-status endpoint, never LLM-guessed).

## 7. Provenance on data files

Every adapter data file gains a `_meta` block:

    "_meta": {"source": "https://...", "fetched_at": "2026-09-23T...",
              "review": "hand_curated" | "machine_staged" | "verified"}

Per-datum `source` overrides where needed. `bootstrap-game` writes `_meta` and
stages everything as pending change records (M19 review flow); weekly
`check-sources` diffs produce reviewable updates. The settings page shows
per-file provenance, so "where did this number come from" is always
answerable.

## 8. Dashboard & endpoint gaps

Existing `/api` covers the CRUD (players, roster+builds, teams, resources+plan,
codes, imports, claims/sources/changes, exports). Gaps the UI needs:

- `GET /api/dashboard?game_id=` → `{roster_count, gear_count, active_team,
  currency_totals (by category), codes_active, last_import, freshness}` —
  one aggregate the dashboard renders.
- `GET /api/games/{id}/terminology` and theme exposure via the games endpoint.
- Chat endpoints (M22): conversations CRUD + `POST …/messages`.
- `/ui/*` fragment routes per page (declared at build time, smoke-tested).

## 9. Non-goals (v1 — write these down to prevent drift)

Linux-only · no auth on loopback · single LLM endpoint config · non-streaming
chat · no mobile layout · vehicles (NTE) out of scope · OWUI integration
frozen (kept working, no new features) · no .deb/AppImage packaging.

## 10. Build order

1. **M20** — thin shell: base layout, switcher, theme plumbing, dashboard
   (with the aggregate endpoint), DB backup/restore. Timeboxed; inline-editing
   polish deferred.
2. **M21** — `gear_type` migration → deterministic roster importer → screenshot
   upload + import review UI. This is what gets the buddy out of pasting
   rosters into chat.
3. **M22** — chat: tables, tool loop, persona editor UI, companion memories.
4. **M23** — native window: `chromium --app` detection → browser tab fallback;
   desktop icon re-target; buddy cutover (OWUI → standalone).
5. **M24** — terminology.json + gear_families.json land with the ZZZ adapter
   first, then the workbench: `new-game`, `bootstrap-game`, HSR proof, NTE
   after its §5 open items resolve.

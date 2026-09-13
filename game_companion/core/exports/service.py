"""Export service: regenerable JSON + human-readable Markdown from SQLite.

Exports are write-only snapshots for the user (SQLite stays authoritative).
Used by the CLI (``game-companion export``) and the API (``/exports``).
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from game_companion.config import Settings
from game_companion.core.games.base import GameAdapter
from game_companion.core.resources.service import ResourceService
from game_companion.db.repositories import (
    BuildRepository,
    CharacterRepository,
    CodeRepository,
    EquipmentRepository,
    GearRepository,
    GoalRepository,
    HistoryRepository,
    ResearchRepository,
    TeamRepository,
    TrainingRepository,
)
from game_companion.utils import to_iso, utcnow


class ExportService:
    def __init__(self, session: Session, adapter: GameAdapter, settings: Settings) -> None:
        self.session = session
        self.adapter = adapter
        self.settings = settings
        self.characters = CharacterRepository(session)
        self.builds = BuildRepository(session)
        self.equipment = EquipmentRepository(session)
        self.gear = GearRepository(session)
        self.teams = TeamRepository(session)
        self.codes = CodeRepository(session)
        self.history = HistoryRepository(session)
        self.training = TrainingRepository(session)
        self.goals = GoalRepository(session)
        self.research = ResearchRepository(session)

    # ------------------------------------------------------------------ JSON

    def collect(self, game_id: str, player_id: str) -> dict:
        characters = self.characters.search(game_id, player_id)
        builds = [b for c in characters for b in self.builds.for_character(c.id)]
        active_by_char = {b.character_id: b.id for b in builds if b.is_active}
        return {
            "game": {
                "game_id": self.adapter.game_id,
                "display_name": self.adapter.display_name,
                "version": self.adapter.version,
            },
            "exported_at": to_iso(utcnow()),
            "characters": [self._character_dict(c, active_by_char) for c in characters],
            "builds": [self._build_dict(b) for b in builds],
            "equipment": [
                self._simple(i) for i in self.equipment.search(game_id, player_id)
            ],
            "gear": [
                self._simple(g)
                for g in self.gear.search(game_id, player_id)
            ],
            "teams": [self._team_dict(t) for t in self.teams.list_all(game_id=game_id, player_profile_id=player_id)],
            "resources": ResourceService(self.session, self.adapter).list_with_status(game_id, player_id),
            "codes": self._codes_list(game_id, player_id),
            "combat_results": [self._simple(r) for r in self.history.results(game_id, player_id)],
            "training_issues": [self._simple(i) for i in self.training.issues(game_id, player_id)],
            "training_goals": [self._simple(g) for g in self.goals.goals(game_id, player_id)],
            "sources": [self._simple(s) for s in self.research.list_all(game_id=game_id)],
        }

    def write_exports(self, game_id: str, player_id: str) -> list[Path]:
        out_dir = self.settings.exports_dir / game_id
        out_dir.mkdir(parents=True, exist_ok=True)
        data = self.collect(game_id, player_id)
        written = [out_dir / "account.json"]
        (out_dir / "account.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )
        markdown = self.render_markdown(game_id, player_id)
        for filename, content in markdown.items():
            path = out_dir / filename
            path.write_text(content, encoding="utf-8")
            written.append(path)
        return written

    # -------------------------------------------------------------- Markdown

    def render_markdown(self, game_id: str, player_id: str) -> dict[str, str]:
        characters = self.characters.search(game_id, player_id)
        char_ids = {c.id for c in characters}
        builds = {b.id: b for c in characters for b in self.builds.for_character(c.id)}
        term = self.adapter.terminology()
        docs: dict[str, str] = {}
        docs["roster.md"] = self._render_roster(game_id, player_id, characters, builds, term.character)
        docs["teams.md"] = self._render_teams(game_id, player_id, characters)
        docs["resources.md"] = self._render_resources(game_id, player_id)
        docs["codes.md"] = self.render_codes(game_id, player_id)
        docs["gear.md"] = self._render_gear(game_id, player_id, characters, term.gear)
        docs["training.md"] = self._render_training(game_id, player_id)
        docs["history.md"] = self._render_history(game_id, player_id, characters, char_ids)
        return {name: content for name, content in docs.items() if content.strip()}

    def _render_roster(self, game_id, player_id, characters, builds, character_noun) -> str:
        lines = [f"# {character_noun} Roster — {self.adapter.display_name}", ""]
        for char in characters:
            lines.append(f"## {char.display_name} (`{char.key}`)")
            meta = [f"Level {char.level}" if char.level else None,
                    f"{self.adapter.terminology().duplication} {char.duplication_level}"
                    if char.duplication_level else None,
                    "favorite ★" if char.favorite else None,
                    f"source: {char.source}",
                    f"last verified: {to_iso(char.last_verified_at) or 'never'}"]
            lines.append("- " + " · ".join(m for m in meta if m))
            skills = {s.skill_key: s.level for s in char.skills}
            if skills:
                names = {d.key: d.name for d in self.adapter.skill_definitions()}
                lines.append(
                    "- Skills: "
                    + ", ".join(f"{names.get(k, k)} {v if v is not None else '?'}" for k, v in sorted(skills.items()))
                )
            build = builds.get(
                next((b.id for b in self.builds.for_character(char.id) if b.is_active), None)
            )
            if build is not None:
                equipment = self.equipment.get(build.equipment_item_id) if build.equipment_item_id else None
                lines.append(f"- Active build `{build.name}`: "
                             + (f"{equipment.display_name} (lv {equipment.level})" if equipment else "no equipment"))
                gear_desc = []
                for row in sorted(build.gear_slots, key=lambda r: r.slot):
                    if row.gear_item_id:
                        g = self.gear.get(row.gear_item_id)
                        if g:
                            gear_desc.append(f"slot {row.slot}: {g.set_key or '?'} "
                                             f"{g.main_stat_key or '?'} (lv {g.level if g.level is not None else '?'})")
                if gear_desc:
                    lines.append("  - Gear: " + "; ".join(gear_desc))
            if char.notes:
                lines.append(f"- Notes: {char.notes}")
            lines.append("")
        return "\n".join(lines)

    def _render_teams(self, game_id, player_id, characters) -> str:
        by_id = {c.id: c for c in characters}
        lines = [f"# Teams — {self.adapter.display_name}", ""]
        for team in self.teams.list_all(game_id=game_id, player_profile_id=player_id):
            flag = " (active)" if team.is_active else ""
            lines.append(f"## {team.name}{flag}")
            for m in team.members:
                char = by_id.get(m.character_id)
                name = char.display_name if char else m.character_id
                role = f" — {m.role}" if m.role else ""
                lines.append(f"- {name}{role}")
            if team.notes:
                lines.append(f"- Notes: {team.notes}")
            lines.append("")
        return "\n".join(lines)

    def _render_resources(self, game_id, player_id) -> str:
        rows = ResourceService(self.session, self.adapter).list_with_status(game_id, player_id)
        lines = [f"# Resources — {self.adapter.display_name}", "",
                 "| Resource | Have | Status | Why |", "| --- | --- | --- | --- |"]
        for r in rows:
            lines.append(f"| {r['name']} | {r['quantity']} | {r['status']} ({r['color']}) | {r['explanation']} |")
        if len(rows) == 0:
            lines.append("_No resources tracked yet._")
        return "\n".join(lines) + "\n"

    def render_codes(self, game_id: str, player_id: str) -> str:
        """#CODES output: active codes, used struck through, recycled flagged."""
        codes = self.codes.list_all(game_id=game_id)
        lines = [f"# Redeem Codes — {self.adapter.display_name}", ""]
        active, used, other = [], [], []
        for code in codes:
            state = self.codes.player_state(code.id, player_id)
            if state and state.used:
                used.append(code)
            elif code.status in ("active", "recycled"):
                active.append(code)
            else:
                other.append(code)
        if active:
            lines.append("## Active")
            for code in active:
                suffix = " ♻ reactivated" if code.status == "recycled" else ""
                if code.expires_at:
                    lines.append(f"- `{code.code}` — expires {to_iso(code.expires_at)}{suffix}")
                else:
                    lines.append(f"- `{code.code}`{suffix}")
        if used:
            lines.append("\n## Used")
            for code in used:
                lines.append(f"- ~~`{code.code}`~~")
        if other:
            lines.append("\n## Expired / unknown")
            for code in other:
                lines.append(f"- `{code.code}` ({code.status})")
        if not codes:
            lines.append("_No codes tracked yet._")
        return "\n".join(lines) + "\n"

    def _render_gear(self, game_id, player_id, characters, gear_noun) -> str:
        by_id = {c.id: c.display_name for c in characters}
        items = self.gear.search(game_id, player_id)
        lines = [f"# {gear_noun} Inventory — {self.adapter.display_name}", ""]
        for g in items:
            holder = by_id.get(g.equipped_character_id or "", "unequipped")
            flags = ("🔒" if g.locked else "") + ("★" if g.favorite else "")
            subs = ", ".join(
                f"{s.get('key')} {s.get('value')}" + (f" x{s['rolls']}" if s.get("rolls") else "")
                for s in (g.substats or [])
            )
            lines.append(
                f"- **slot {g.slot or '?'}** {g.set_key or '?'} · {g.main_stat_key or '?'} "
                f"{g.main_stat_value or ''} · lv {g.level if g.level is not None else '?'} · "
                f"{holder} {flags} — subs: {subs or '—'}"
            )
        if not items:
            lines.append("_No gear recorded yet._")
        return "\n".join(lines) + "\n"

    def _render_training(self, game_id, player_id) -> str:
        lines = ["# Training", ""]
        issues = self.training.issues(game_id, player_id)
        if issues:
            lines.append("## Issues")
            for i in issues:
                chars = ", ".join(i.character_keys) if i.character_keys else "general"
                lines.append(
                    f"- [{i.status}] {i.category} ({chars}) x{i.occurrences} — {i.description}"
                )
        goals = self.goals.goals(game_id, player_id)
        if goals:
            lines.append("\n## Goals")
            for g in goals:
                lines.append(f"- [{g.status}] {g.description}")
        if not issues and not goals:
            lines.append("_No training issues or goals recorded._")
        return "\n".join(lines) + "\n"

    def _render_history(self, game_id, player_id, characters, char_ids) -> str:
        lines = ["# Combat History", ""]
        results = self.history.results(game_id, player_id)
        for r in results:
            outcome = "clear" if r.cleared else ("fail" if r.cleared is False else "n/a")
            team_names = ", ".join(
                m.get("display_name", "?") for m in (r.team_snapshot or {}).get("members", [])
            )
            score = f" score {r.score:g}" if r.score is not None else ""
            stars = f" {'★' * r.stars}" if r.stars else ""
            lines.append(
                f"- {to_iso(r.played_at)} — {r.encounter_key}"
                + (f" slot {r.encounter_slot}" if r.encounter_slot else "")
                + f" — {outcome}{stars}{score} — {team_names or 'ad-hoc team'}"
            )
        if not results:
            lines.append("_No combat results recorded._")
        return "\n".join(lines) + "\n"

    # ---------------------------------------------------------------- helpers

    def _character_dict(self, char, active_by_char: dict) -> dict:
        return {
            "key": char.key,
            "display_name": char.display_name,
            "rarity": char.rarity,
            "owned": char.owned,
            "level": char.level,
            "duplication_level": char.duplication_level,
            "favorite": char.favorite,
            "notes": char.notes,
            "data": char.data,
            "source": char.source,
            "last_verified_at": to_iso(char.last_verified_at),
            "skills": {s.skill_key: s.level for s in char.skills},
            "active_build": active_by_char.get(char.id),
        }

    def _build_dict(self, build) -> dict:
        gear_slots = {row.slot: row.gear_item_id for row in build.gear_slots}
        return {
            "id": build.id,
            "character_id": build.character_id,
            "name": build.name,
            "is_active": build.is_active,
            "equipment_item_id": build.equipment_item_id,
            "gear_slots": gear_slots,
            "notes": build.notes,
        }

    def _team_dict(self, team) -> dict:
        return {
            "id": team.id,
            "name": team.name,
            "is_active": team.is_active,
            "notes": team.notes,
            "members": [
                {"character_id": m.character_id, "position": m.position, "role": m.role}
                for m in team.members
            ],
        }

    def _codes_list(self, game_id: str, player_id: str) -> list[dict]:
        out = []
        for code in self.codes.list_all(game_id=game_id):
            state = self.codes.player_state(code.id, player_id)
            out.append(
                {
                    "code": code.code,
                    "status": code.status,
                    "expires_at": to_iso(code.expires_at),
                    "discovered_at": to_iso(code.discovered_at),
                    "used_by_player": bool(state and state.used),
                    "notes": code.notes,
                }
            )
        return out

    def _simple(self, obj) -> dict:
        return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

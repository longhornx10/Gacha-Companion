"""Combat history (M17): recording with snapshots + deterministic trends."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from game_companion.db.models import Character, CombatResult
from game_companion.db.repositories import HistoryRepository, TeamRepository
from game_companion.utils import utcnow


class CombatService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.history = HistoryRepository(session)
        self.teams = TeamRepository(session)

    def record(self, game_id: str, player_id: str, payload: dict[str, Any]) -> CombatResult:
        team_snapshot: dict = {}
        team_id = payload.get("team_id")
        if team_id:
            team = self.teams.get(team_id)
            if team is not None and team.game_id == game_id and team.player_profile_id == player_id:
                members = []
                for m in team.members:
                    char = self.session.get(Character, m.character_id)
                    members.append({
                        "key": char.key if char else None,
                        "display_name": char.display_name if char else None,
                        "level": char.level if char else None,
                        "duplication_level": char.duplication_level if char else None,
                    })
                team_snapshot = {"team_id": team.id, "name": team.name, "members": members}
        played_at = payload.get("played_at")
        if isinstance(played_at, str):
            try:
                played_at = datetime.fromisoformat(played_at.replace("Z", "+00:00"))
            except ValueError:
                played_at = None
        result = self.history.add(
            CombatResult(
                game_id=game_id,
                player_profile_id=player_id,
                encounter_key=payload["encounter_key"],
                encounter_slot=payload.get("encounter_slot"),
                played_at=played_at or utcnow(),
                team_id=team_id,
                team_snapshot=team_snapshot,
                score=payload.get("score"),
                rank=payload.get("rank"),
                stars=payload.get("stars"),
                cleared=payload.get("cleared"),
                clear_time_seconds=payload.get("clear_time_seconds"),
                retries=payload.get("retries"),
                difficulty=payload.get("difficulty"),
                notes=payload.get("notes"),
            )
        )
        return result

    def trends(self, game_id: str, player_id: str, encounter_key: str | None = None) -> dict:
        results = self.history.results(game_id, player_id, encounter_key)
        decided = [r for r in results if r.cleared is not None]
        scored = [r for r in results if r.score is not None]

        def _mean(values: list[float]) -> float | None:
            return round(sum(values) / len(values), 3) if values else None

        by_encounter: dict[str, dict] = {}
        by_team: dict[str, dict] = {}
        for r in results:
            bucket = by_encounter.setdefault(r.encounter_key, {"attempts": 0, "clears": 0, "scores": []})
            bucket["attempts"] += 1
            if r.cleared:
                bucket["clears"] += 1
            if r.score is not None:
                bucket["scores"].append(r.score)
            team_name = (r.team_snapshot or {}).get("name") or (
                "+".join(sorted(m.get("key") or "?" for m in (r.team_snapshot or {}).get("members", [])))
            )
            if team_name:
                tb = by_team.setdefault(team_name, {"attempts": 0, "clears": 0, "scores": []})
                tb["attempts"] += 1
                if r.cleared:
                    tb["clears"] += 1
                if r.score is not None:
                    tb["scores"].append(r.score)

        improvement: dict[str, Any] = {}
        if len(scored) >= 4:
            ordered = sorted(scored, key=lambda r: r.played_at)
            half = len(ordered) // 2
            early = _mean([r.score for r in ordered[:half]])
            late = _mean([r.score for r in ordered[half:]])
            improvement = {
                "early_average_score": early,
                "recent_average_score": late,
                "delta": round((late or 0) - (early or 0), 3),
                "note": "compares first half vs second half of scored attempts",
            }

        for bucket in list(by_encounter.values()) + list(by_team.values()):
            bucket["average_score"] = _mean(bucket.pop("scores"))
            bucket["win_rate"] = round(bucket["clears"] / bucket["attempts"], 3) if bucket["attempts"] else None

        return {
            "total_attempts": len(results),
            "win_rate": round(sum(1 for r in decided if r.cleared) / len(decided), 3) if decided else None,
            "by_encounter": by_encounter,
            "by_team": by_team,
            "improvement": improvement,
        }

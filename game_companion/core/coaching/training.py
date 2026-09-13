"""Training model (M18): issues with recurrence tracking + goals."""

from __future__ import annotations

from sqlalchemy.orm import Session

from game_companion.db.repositories import GoalRepository, TrainingRepository
from game_companion.errors import ValidationError
from game_companion.utils import utcnow


class TrainingService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.issues = TrainingRepository(session)
        self.goals = GoalRepository(session)

    def record_issue(
        self,
        game_id: str,
        player_id: str,
        category: str,
        description: str,
        character_keys: list[str],
        severity: str = "medium",
        notes: str | None = None,
    ) -> dict:
        from game_companion.db.models import TrainingIssue

        character_keys = sorted(set(character_keys))
        existing = self.issues.find_similar(game_id, player_id, category, character_keys)
        if existing is not None and existing.status != "resolved":
            existing.occurrences += 1
            existing.last_seen_at = utcnow()
            if severity:
                existing.severity = severity
            if notes:
                existing.notes = notes
            self.session.flush()
            return {"issue_id": existing.id, "recurred": True, "occurrences": existing.occurrences}
        issue = self.issues.add(
            TrainingIssue(
                game_id=game_id,
                player_profile_id=player_id,
                category=category,
                description=description,
                severity=severity,
                character_keys=character_keys,
                first_seen_at=utcnow(),
                last_seen_at=utcnow(),
                notes=notes,
            )
        )
        return {"issue_id": issue.id, "recurred": False, "occurrences": 1}

    def update_issue(self, issue_id: str, payload: dict):
        issue = self.issues.get_or_raise(issue_id, "training issue")
        for attr in ("status", "severity", "description", "notes"):
            if payload.get(attr) is not None:
                setattr(issue, attr, payload[attr])
        self.session.flush()
        return issue

    def open_issues(self, game_id: str, player_id: str, character_key: str | None = None):
        issues = self.issues.issues(game_id, player_id, status="open")
        if character_key:
            issues = [i for i in issues if not i.character_keys or character_key in i.character_keys]
        return issues

    def add_goal(self, game_id: str, player_id: str, description: str, target: dict | None):
        from game_companion.db.models import TrainingGoal

        return self.goals.add(
            TrainingGoal(
                game_id=game_id,
                player_profile_id=player_id,
                description=description,
                target=target,
            )
        )

    def update_goal(self, goal_id: str, payload: dict):
        goal = self.goals.get_or_raise(goal_id, "training goal")
        if payload.get("status") is not None:
            if payload["status"] not in ("active", "done", "dropped"):
                raise ValidationError("goal status must be active|done|dropped")
            goal.status = payload["status"]
        if payload.get("progress_notes") is not None:
            goal.progress_notes = payload["progress_notes"]
        self.session.flush()
        return goal

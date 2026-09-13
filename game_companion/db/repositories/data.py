"""Repositories for resources, codes, history/training, research and misc."""

from __future__ import annotations

from sqlalchemy import select

from game_companion.db.models import (
    AuditResult,
    ChangeRecord,
    CombatResult,
    Encounter,
    PlayerCodeState,
    Recommendation,
    RedeemCode,
    ResearchClaim,
    ResearchSource,
    Resource,
    ResourcePlanEntry,
    ScreenshotImport,
    TrainingGoal,
    TrainingIssue,
)
from game_companion.db.repositories.base import BaseRepository


class ResourceRepository(BaseRepository[Resource]):
    model = Resource

    def find_by_key(self, game_id: str, player_id: str, resource_key: str) -> Resource | None:
        return self.session.scalars(
            select(Resource).where(
                Resource.game_id == game_id,
                Resource.player_profile_id == player_id,
                Resource.resource_key == resource_key,
            )
        ).first()

    def upsert(self, game_id: str, player_id: str, resource_key: str, quantity: int) -> Resource:
        row = self.find_by_key(game_id, player_id, resource_key)
        if row is None:
            row = Resource(game_id=game_id, player_profile_id=player_id, resource_key=resource_key)
            self.session.add(row)
        row.quantity = quantity
        self.session.flush()
        return row

    # plan entries ------------------------------------------------------------

    def plan_entries(self, game_id: str, player_id: str, resource_key: str | None = None):
        stmt = select(ResourcePlanEntry).where(
            ResourcePlanEntry.game_id == game_id,
            ResourcePlanEntry.player_profile_id == player_id,
        )
        if resource_key is not None:
            stmt = stmt.where(ResourcePlanEntry.resource_key == resource_key)
        return list(self.session.scalars(stmt))

    def set_plan_entry(
        self, game_id: str, player_id: str, resource_key: str, character_id: str | None, amount: int
    ) -> ResourcePlanEntry:
        stmt = select(ResourcePlanEntry).where(
            ResourcePlanEntry.game_id == game_id,
            ResourcePlanEntry.player_profile_id == player_id,
            ResourcePlanEntry.resource_key == resource_key,
            ResourcePlanEntry.character_id == character_id,
        )
        row = self.session.scalars(stmt).first()
        if row is None:
            row = ResourcePlanEntry(
                game_id=game_id,
                player_profile_id=player_id,
                resource_key=resource_key,
                character_id=character_id,
            )
            self.session.add(row)
        row.amount = amount
        self.session.flush()
        return row

    def clear_plan(self, game_id: str, player_id: str, resource_key: str) -> None:
        for row in self.plan_entries(game_id, player_id, resource_key):
            self.session.delete(row)
        self.session.flush()


class CodeRepository(BaseRepository[RedeemCode]):
    model = RedeemCode

    def find_by_code(self, game_id: str, code: str) -> RedeemCode | None:
        return self.session.scalars(
            select(RedeemCode).where(RedeemCode.game_id == game_id, RedeemCode.code == code)
        ).first()

    def player_state(self, code_id: str, player_id: str) -> PlayerCodeState | None:
        return self.session.scalars(
            select(PlayerCodeState).where(
                PlayerCodeState.code_id == code_id,
                PlayerCodeState.player_profile_id == player_id,
            )
        ).first()

    def set_player_state(self, code_id: str, player_id: str, used: bool) -> PlayerCodeState:
        state = self.player_state(code_id, player_id)
        if state is None:
            state = PlayerCodeState(code_id=code_id, player_profile_id=player_id)
            self.session.add(state)
        state.used = used
        from game_companion.utils import utcnow

        state.used_at = utcnow() if used else None
        self.session.flush()
        return state


class HistoryRepository(BaseRepository[CombatResult]):
    model = CombatResult

    def results(self, game_id: str, player_id: str, encounter_key: str | None = None):
        stmt = (
            select(CombatResult)
            .where(
                CombatResult.game_id == game_id,
                CombatResult.player_profile_id == player_id,
            )
            .order_by(CombatResult.played_at)
        )
        if encounter_key:
            stmt = stmt.where(CombatResult.encounter_key == encounter_key)
        return list(self.session.scalars(stmt))


class TrainingRepository(BaseRepository[TrainingIssue]):
    model = TrainingIssue

    def issues(self, game_id: str, player_id: str, status: str | None = None):
        stmt = (
            select(TrainingIssue)
            .where(
                TrainingIssue.game_id == game_id,
                TrainingIssue.player_profile_id == player_id,
            )
            .order_by(TrainingIssue.last_seen_at.desc())
        )
        if status:
            stmt = stmt.where(TrainingIssue.status == status)
        return list(self.session.scalars(stmt))

    def find_similar(
        self, game_id: str, player_id: str, category: str, character_keys: list[str]
    ) -> TrainingIssue | None:
        """Same category + same character set = recurring issue."""
        for issue in self.issues(game_id, player_id, status=None):
            if issue.category == category and sorted(issue.character_keys or []) == sorted(
                character_keys
            ):
                return issue
        return None


class GoalRepository(BaseRepository[TrainingGoal]):
    model = TrainingGoal

    def goals(self, game_id: str, player_id: str, status: str | None = None):
        stmt = select(TrainingGoal).where(
            TrainingGoal.game_id == game_id, TrainingGoal.player_profile_id == player_id
        )
        if status:
            stmt = stmt.where(TrainingGoal.status == status)
        return list(self.session.scalars(stmt))


class ResearchRepository(BaseRepository[ResearchSource]):
    model = ResearchSource

    def find_by_key(self, game_id: str, key: str) -> ResearchSource | None:
        return self.session.scalars(
            select(ResearchSource).where(
                ResearchSource.game_id == game_id, ResearchSource.key == key
            )
        ).first()

    def upsert_source(self, **kwargs) -> ResearchSource:
        row = self.find_by_key(kwargs["game_id"], kwargs["key"])
        if row is None:
            row = ResearchSource(**kwargs)
            self.session.add(row)
        else:
            for attr in ("name", "url", "category", "trust", "notes"):
                if attr in kwargs and kwargs[attr] is not None:
                    setattr(row, attr, kwargs[attr])
        self.session.flush()
        return row

    # claims -----------------------------------------------------------------

    def add_claim(self, **kwargs) -> ResearchClaim:
        claim = ResearchClaim(**kwargs)
        self.session.add(claim)
        self.session.flush()
        return claim

    def claims(self, game_id: str, subject: str | None = None, claim_type: str | None = None):
        stmt = (
            select(ResearchClaim)
            .where(ResearchClaim.game_id == game_id, ResearchClaim.superseded.is_(False))
            .order_by(ResearchClaim.retrieved_at.desc())
        )
        if subject:
            stmt = stmt.where(ResearchClaim.subject == subject)
        if claim_type:
            stmt = stmt.where(ResearchClaim.claim_type == claim_type)
        return list(self.session.scalars(stmt))

    # change records -----------------------------------------------------------

    def add_change(self, **kwargs) -> ChangeRecord:
        row = ChangeRecord(**kwargs)
        self.session.add(row)
        self.session.flush()
        return row

    def changes(self, game_id: str, review_status: str | None = None):
        stmt = (
            select(ChangeRecord)
            .where(ChangeRecord.game_id == game_id)
            .order_by(ChangeRecord.detected_at.desc())
        )
        if review_status:
            stmt = stmt.where(ChangeRecord.review_status == review_status)
        return list(self.session.scalars(stmt))


class ImportRepository(BaseRepository[ScreenshotImport]):
    model = ScreenshotImport


class EncounterRepository(BaseRepository[Encounter]):
    model = Encounter

    def find_by_key(self, game_id: str, key: str) -> Encounter | None:
        return self.session.scalars(
            select(Encounter).where(Encounter.game_id == game_id, Encounter.key == key)
        ).first()


class RecommendationRepository(BaseRepository[Recommendation]):
    model = Recommendation


class AuditRepository(BaseRepository[AuditResult]):
    model = AuditResult

"""Resource inventory service: quantities + deterministic threshold statuses."""

from __future__ import annotations

from sqlalchemy.orm import Session

from game_companion.core.games.base import GameAdapter
from game_companion.core.resources.thresholds import evaluate_resource_status
from game_companion.db.repositories import CharacterRepository, ResourceRepository


class ResourceService:
    def __init__(self, session: Session, adapter: GameAdapter) -> None:
        self.session = session
        self.adapter = adapter
        self.resources = ResourceRepository(session)
        self.characters = CharacterRepository(session)

    def _definitions(self) -> dict[str, object]:
        return {d.key: d for d in self.adapter.resource_definitions()}

    def list_with_status(self, game_id: str, player_id: str) -> list[dict]:
        definitions = self._definitions()
        config = self.adapter.threshold_config()
        out: list[dict] = []
        for row in self.resources.list_all(game_id=game_id, player_profile_id=player_id):
            definition = definitions.get(row.resource_key)
            single_max = getattr(definition, "single_character_max", None) if definition else None
            plan = self.resources.plan_entries(game_id, player_id, row.resource_key)
            planned_total = sum(e.amount for e in plan) if plan else None
            status = evaluate_resource_status(
                row.quantity, single_max=single_max, planned_total=planned_total, config=config
            )
            out.append(
                {
                    "resource_key": row.resource_key,
                    "name": getattr(definition, "name", row.resource_key),
                    "quantity": row.quantity,
                    "notes": row.notes,
                    "planned_characters": [e.character_id for e in plan],
                    **status.as_dict(),
                }
            )
        out.sort(key=lambda r: r["resource_key"])
        return out

    def evaluate_key(
        self, game_id: str, player_id: str, resource_key: str, quantity: int | None = None
    ) -> dict:
        """Evaluate status for a key even if no inventory row exists yet."""
        definitions = self._definitions()
        definition = definitions.get(resource_key)
        row = self.resources.find_by_key(game_id, player_id, resource_key)
        if quantity is None:
            quantity = row.quantity if row else 0
        single_max = getattr(definition, "single_character_max", None) if definition else None
        plan = self.resources.plan_entries(game_id, player_id, resource_key)
        planned_total = sum(e.amount for e in plan) if plan else None
        status = evaluate_resource_status(
            quantity,
            single_max=single_max,
            planned_total=planned_total,
            config=self.adapter.threshold_config(),
        )
        return {
            "resource_key": resource_key,
            "name": getattr(definition, "name", resource_key),
            "known_to_adapter": definition is not None,
            **status.as_dict(),
        }

"""Deterministic resource-status thresholds (SPEC Milestone 12).

Semantics (documented, tested, configurable via the adapter):

- ``X`` = single-character max target: the amount one character needs to reach
  the respective max (adapter ``ResourceDefinition.single_character_max``).
- ``Y`` = planned total: what the player's planned characters collectively
  need (``resource_plan_entries``). When no plan entries exist, ``Y`` defaults
  to ``X`` (the "max out one character" target).
- ``Q`` = current quantity.

Status (returning also the color the user asked for):

- ``done``            (white)      Q >= Y
- ``prep``            (cyan/lime)  X <= Q < Y            (can fully max one, working toward the rest)
- ``very_low``        (orange)     low_fraction*X <= Q < X
- ``critically_low``  (red)        Q < low_fraction*X
- ``unknown``         (gray)       X unknown and Q < Y (or everything unknown) — never guessed

Edge cases (also encoded in tests):
- Y given but X unknown: Q >= Y -> done; below -> very_low with an explanation
  that critically_low vs very_low cannot be distinguished without X.
- low_fraction is configurable per adapter (default 0.25).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from game_companion.core.games.base import ResourceThresholdConfig


class ResourceStatus(str, Enum):
    DONE = "done"
    PREP = "prep"
    VERY_LOW = "very_low"
    CRITICALLY_LOW = "critically_low"
    UNKNOWN = "unknown"


STATUS_COLORS: dict[str, str] = {
    ResourceStatus.DONE.value: "white",
    ResourceStatus.PREP.value: "cyan/lime",
    ResourceStatus.VERY_LOW.value: "orange",
    ResourceStatus.CRITICALLY_LOW.value: "red",
    ResourceStatus.UNKNOWN.value: "gray",
}


@dataclass(frozen=True)
class ResourceStatusResult:
    status: ResourceStatus
    color: str
    quantity: int
    single_max: int | None
    planned_total: int | None
    explanation: str

    def as_dict(self) -> dict:
        return {
            "status": self.status.value,
            "color": self.color,
            "quantity": self.quantity,
            "single_character_max": self.single_max,
            "planned_total": self.planned_total,
            "explanation": self.explanation,
        }


def evaluate_resource_status(
    quantity: int,
    single_max: int | None = None,
    planned_total: int | None = None,
    config: ResourceThresholdConfig | None = None,
) -> ResourceStatusResult:
    config = config or ResourceThresholdConfig()
    effective_plan = planned_total if planned_total is not None else single_max

    def result(status: ResourceStatus, explanation: str) -> ResourceStatusResult:
        return ResourceStatusResult(
            status=status,
            color=STATUS_COLORS[status.value],
            quantity=quantity,
            single_max=single_max,
            planned_total=planned_total,
            explanation=explanation,
        )

    if quantity < 0:
        quantity = 0

    if effective_plan is None and single_max is None:
        return result(
            ResourceStatus.UNKNOWN,
            "No single-character max target (X) and no planned demand (Y) are known for this "
            "resource; refusing to guess a status. Provide plan entries or adapter data.",
        )

    if effective_plan is not None and quantity >= effective_plan:
        return result(
            ResourceStatus.DONE,
            f"{quantity} >= planned need {effective_plan} — covers all planned targets.",
        )

    if single_max is None:
        return result(
            ResourceStatus.VERY_LOW,
            f"{quantity} < planned need {effective_plan}; single-character max unknown, so "
            "very_low/critically_low cannot be distinguished (reported as very_low).",
        )

    low_line = config.low_fraction * single_max
    if single_max <= quantity and effective_plan is not None and effective_plan > quantity:
        return result(
            ResourceStatus.PREP,
            f"{quantity} covers one full single-character max (X={single_max}) but not the "
            f"planned total (Y={effective_plan}).",
        )
    if quantity >= single_max:
        return result(
            ResourceStatus.DONE,
            f"{quantity} >= single-character max (X={single_max}); no larger plan recorded.",
        )
    if quantity >= low_line:
        return result(
            ResourceStatus.VERY_LOW,
            f"{quantity} is between {config.low_fraction:.0%} of X ({low_line:g}) and X "
            f"({single_max}) — enough to make progress, not enough to finish one character.",
        )
    return result(
        ResourceStatus.CRITICALLY_LOW,
        f"{quantity} is below {config.low_fraction:.0%} of the single-character max "
        f"({low_line:g} of X={single_max}) — stockpile before planning upgrades.",
    )

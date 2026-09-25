"""The GameAdapter contract.

Adapters supply every game-specific fact: terminology, team size, gear slots,
stat/skill definitions, resources, encounters, sources, screenshot schemas, and
scoring hooks. Core code calls these hooks and *never* imports game packages
(enforced by a test). Scoring hooks return labeled, explainable components —
never opaque numbers or fabricated DPS.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

# --------------------------------------------------------------------------- #
# Contract data types
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Terminology:
    """How generic core nouns are called in this game."""

    character: str
    character_plural: str
    equipment: str
    equipment_plural: str
    gear: str
    gear_plural: str
    duplication: str  # duplication-rank naming, e.g. what the game calls copies of a character
    special_progression: str  # e.g. the game's special per-character progression system
    build: str = "Build"
    team: str = "Team"


@dataclass(frozen=True)
class StatDefinition:
    key: str
    name: str
    kind: str  # "percent" | "flat"
    short: str | None = None


@dataclass(frozen=True)
class SkillDefinition:
    key: str
    name: str
    max_level: int
    # Starter-data honesty marker: set when max_level comes from unverified data.
    max_level_note: str | None = None


@dataclass(frozen=True)
class GearSlotDefinition:
    key: str
    name: str
    main_stat_pool: tuple[str, ...] = ()


@dataclass(frozen=True)
class TeamRules:
    min_size: int
    max_size: int


@dataclass(frozen=True)
class ResourceDefinition:
    key: str
    name: str
    # Max amount needed to fully max ONE character ("X" in threshold math).
    # None = unknown: threshold status becomes "unknown" instead of guessing.
    single_character_max: int | None = None
    # Cross-game taxonomy (M24): pull_currency | pull_ticket_limited |
    # pull_ticket_standard | money | stamina | standard_material | None.
    category: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ResourceThresholdConfig:
    """Deterministic resource-status thresholds (see core/resources/thresholds.py).

    done:            quantity >= planned total (Y)
    prep:            single_max (X) <= quantity < Y
    very_low:        low_fraction * X <= quantity < X
    critically_low:  quantity < low_fraction * X
    unknown:         X or Y unavailable — never guessed
    """

    low_fraction: float = 0.25


@dataclass(frozen=True)
class GearFamily:
    """A family of set-based gear, declared entirely by the adapter.

    ``set_rule`` is adapter data, never a core assumption: ``fixed_pieces``
    (set bonuses counted across equipped slots) vs ``module_combo`` (set
    identity lives on the piece via its module loadout).
    """

    key: str
    display: str
    slot_count: int
    set_rule: str  # fixed_pieces | module_combo
    set_sizes: tuple[int, ...]
    rarity_scale: str  # "SAB" | "stars5"
    max_level: int | None = None
    max_substats: int | None = None
    starter_data: bool = False
    slots: tuple[GearSlotDefinition, ...] = ()


@dataclass(frozen=True)
class EncounterModeDefinition:
    key: str
    name: str
    slot_count: int
    team_size: int | None = None  # defaults to team_rules.max_size
    description: str = ""


@dataclass(frozen=True)
class SourceDefinition:
    key: str
    name: str
    url: str
    category: str  # official|announcements|database|build_guide|wiki|community
    trust: int  # 1..5
    notes: str = ""


@dataclass(frozen=True)
class ScreenshotSpec:
    key: str
    description: str
    prompt: str  # extraction instruction fragment for the VLM
    schema: type[BaseModel]  # candidate payloads must satisfy this model


# Scoring -------------------------------------------------------------------

LABEL_MEASURED = "MEASURED"
LABEL_HEURISTIC = "HEURISTIC"
LABEL_CONSENSUS = "CONSENSUS"

GEAR_VERDICTS = (
    "strong",
    "useful",
    "niche",
    "speculative",
    "weak",
    "likely_safe_to_discard",
)


@dataclass(frozen=True)
class ScoreComponent:
    name: str
    value: float
    max_value: float
    label: str  # MEASURED | HEURISTIC | CONSENSUS
    detail: str = ""


@dataclass(frozen=True)
class GearEvaluation:
    verdict: str  # one of GEAR_VERDICTS
    score: float  # 0..100, HEURISTIC
    reasons: list[str]
    components: list[ScoreComponent] = field(default_factory=list)
    label: str = LABEL_HEURISTIC


# --------------------------------------------------------------------------- #
# Adapter interface
# --------------------------------------------------------------------------- #

class GameAdapter(ABC):
    """Contract every game adapter must satisfy. See docs/game-adapter.md."""

    #: unique, stable identifier used in URLs, DB rows and CLI ("zzz", ...)
    game_id: str = ""
    display_name: str = ""
    version: str = "0"
    #: internal adapters (the genericity example) stay reachable directly but
    #: are hidden from every user-facing list, picker and health output.
    hidden: bool = False

    @abstractmethod
    def terminology(self) -> Terminology: ...

    @abstractmethod
    def team_rules(self) -> TeamRules: ...

    @abstractmethod
    def gear_slots(self) -> list[GearSlotDefinition]: ...

    def terminology_table(self) -> list[dict[str, Any]]:
        """Ontology -> game vocabulary rows (terminology.json when shipped)."""
        from game_companion.core.games.terminology import load_terminology_table

        package = type(self).__module__.split(".")[2]
        return load_terminology_table(package)

    def gear_families(self) -> list[GearFamily]:
        """Gear families declared by the adapter (M21). Empty by default;
        contract tests require slot coverage when a family declares slots."""
        return []

    def bootstrap_sources(self) -> dict[str, Any]:
        """Fetchable data sources for `bootstrap-game` (M24). Empty by default."""
        return {}

    def bootstrap_transform(self, source_key: str, payload: Any) -> list[dict[str, Any]]:
        """Normalize a bootstrap payload into rows with a stable ``key``."""
        return []

    def catalog_sources(self) -> dict[str, Any]:
        """Fetchable reference-catalog sources (M25): {key: {name, url, kind,
        entity, notes}}. ``kind`` is ``json`` or ``html``; ``entity`` is the
        CatalogEntry entity_type the source feeds. Empty by default."""
        return {}

    def catalog_transform(self, source_key: str, payload: Any) -> list[dict[str, Any]]:
        """Normalize a catalog payload into rows: {key, name, rarity?, meta?}."""
        return []

    def codes_source(self) -> dict[str, Any] | None:
        """Auto-fetchable redeem-code source: {key, name, url, kind}.
        None when the game has no dependable machine-readable source."""
        return None

    def codes_transform(self, payload: Any) -> list[dict[str, Any]]:
        """Normalize a codes payload into rows: {code, rewards?, status?,
        discovered_at?}. status is active|expired|unknown."""
        return []

    def farm_stages(self) -> list[dict[str, Any]]:
        """Stages that drop set-based gear, for the farm planner (M26):
        {key, name, order?, sets: [set_key, ...], battery_cost?, since_version?}.
        Empty by default (game has no machine-readable stage data)."""
        return []

    def gear_meta(self) -> dict[str, Any]:
        """Meta-demand dataset for the farm planner (M26):
        {_meta, archetypes, units: [{key, build_variants: [{four_piece,
        two_piece?, q}]}]}. Empty dict by default (planner unavailable)."""
        return {}

    def grade_gear(self, gear: Mapping[str, Any]) -> dict[str, Any]:
        """Simple quality grade for the farm planner (M26):
        {grade: str, credit: float, reason: str}. Raises NotImplementedError
        when the adapter has no grading model."""
        raise NotImplementedError(f"{type(self).__name__} does not implement gear grading")

    def build_farm_plan(
        self,
        gear_rows: Sequence[Mapping],
        beta: float = 1.2,
        unit_keys: Sequence[str] | None = None,
    ) -> dict[str, Any] | None:
        """Full labeled farm plan for the player's gear rows (M26), or None
        when the game has no meta dataset (planner stays unavailable).
        ``unit_keys`` restricts demand to the player's own roster."""
        return None


    @abstractmethod
    def stat_definitions(self) -> list[StatDefinition]: ...

    @abstractmethod
    def skill_definitions(self) -> list[SkillDefinition]: ...

    @abstractmethod
    def resource_definitions(self) -> list[ResourceDefinition]: ...

    # --- hooks with sensible defaults (adapters override when relevant) -----

    def threshold_config(self) -> ResourceThresholdConfig:
        return ResourceThresholdConfig()

    def gear_sets(self) -> list[dict[str, Any]]:
        """Starter metadata about gear sets; adapters keep this honest (marked
        as starter data if unverified). Empty by default."""
        return []

    def equipment_rules(self) -> dict[str, Any]:
        """Semantics of weapon-like equipment (refinement naming, notes)."""
        return {}

    def progression_rules(self) -> dict[str, Any]:
        """Level caps / ascension stages used by the planner and audit."""
        return {}

    def encounter_modes(self) -> list[EncounterModeDefinition]:
        return []

    def source_registry(self) -> list[SourceDefinition]:
        return []

    def screenshot_specs(self) -> dict[str, ScreenshotSpec]:
        return {}

    def code_config(self) -> dict[str, Any]:
        return {}

    def persona_flavors(self) -> list[dict[str, Any]]:
        """Optional persona flavor descriptions shipped with the game."""
        return []

    def theme(self) -> dict[str, str]:
        """UI accent colors for the active-game theming (D5). Overridable —
        adapters may add: bg / bg2 (page backdrop gradient stops), card
        (panel tint), radius (corner language), mood (short vibe label)."""
        return {"accent": "#8b93ff", "accent2": "#3fd0c9"}

    def media_url(self, kind: str, key: str, meta: Mapping[str, Any] | None = None) -> str | None:
        """Public CDN URL for a portrait/icon: kind is ``character``,
        ``equipment``, ``gear_set`` or ``element`` (key = the element/stat
        key for the last one). None when this game has no known URL pattern
        — the UI falls back to a local monogram/icon."""
        return None

    def tutor_notes(self) -> dict[str, Any]:
        """Game-specific tutoring hints (e.g. control naming for rotations)."""
        return {}

    # --- validation / lookup hooks ------------------------------------------

    def validate_character_data(self, data: Mapping[str, Any]) -> dict[str, Any]:
        """Validate game-specific extras stored in ``characters.data``.
        Returns the normalized dict or raises ValidationError."""
        return dict(data)

    def character_field_choices(self) -> dict[str, list[str]]:
        """Allowed values for character ``data`` fields, for UI dropdowns.

        Empty by default (fields render as free text). Keys must match the
        adapter's ``validate_character_data`` allowlist.
        """
        return {}

    def character_meta(self, key: str) -> dict[str, Any] | None:  # noqa: B027 - optional hook
        """Roster metadata (attribute/specialty/faction/rarity...) for a
        character key, if the adapter's (starter) data knows it."""

    def resolve_character_key(self, name: str) -> str | None:  # noqa: B027 - optional hook
        """Resolve a user-supplied character name to the adapter's canonical key."""

    # --- scoring hooks (all explainable, labeled) ----------------------------

    def score_gear(
        self, gear: Mapping[str, Any], context: Mapping[str, Any]
    ) -> GearEvaluation:
        raise NotImplementedError(f"{type(self).__name__} does not implement gear scoring")

    def score_team(
        self,
        member_keys: Sequence[str],
        context: Mapping[str, Any],
    ) -> list[ScoreComponent]:
        """Heuristic synergy/role components for a set of member keys."""
        raise NotImplementedError(f"{type(self).__name__} does not implement team scoring")

    def character_slot_fit(
        self, character_key: str, encounter_constraints: Mapping[str, Any]
    ) -> float:
        """Individual 0..10 fit of a character for one encounter slot."""
        return 5.0

    def score_equipment_for_character(
        self, character_key: str, equipment: Mapping[str, Any]
    ) -> ScoreComponent:
        raise NotImplementedError(
            f"{type(self).__name__} does not implement equipment comparison"
        )

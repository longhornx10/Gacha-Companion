"""Typed request bodies (Pydantic). Responses are serialized dicts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlayerCreate(BaseModel):
    display_name: str
    notes: str | None = None


class PlayerUpdate(BaseModel):
    display_name: str | None = None
    notes: str | None = None


class PreferencePut(BaseModel):
    value: Any


class CharacterCreate(BaseModel):
    key: str
    display_name: str | None = None
    rarity: int | str | None = None
    owned: bool = True
    level: int | None = None
    duplication_level: int | None = None
    favorite: bool = False
    notes: str | None = None
    data: dict = Field(default_factory=dict)
    source: str | None = None
    verified: bool = False


class CharacterUpdate(BaseModel):
    display_name: str | None = None
    rarity: int | str | None = None
    owned: bool | None = None
    level: int | None = None
    duplication_level: int | None = None
    favorite: bool | None = None
    notes: str | None = None
    data: dict | None = None
    verified: bool = False


class SkillsPut(BaseModel):
    skills: dict[str, int | None]


class BuildCreate(BaseModel):
    name: str = "default"
    notes: str | None = None
    set_active: bool = False


class BuildUpdate(BaseModel):
    notes: str | None = None
    equipment_item_id: str | None = None
    unset_equipment: bool = False


class BuildSlotPut(BaseModel):
    slot: str
    gear_item_id: str | None = None


class EquipmentCreate(BaseModel):
    key: str
    display_name: str
    rarity: int | str | None = None
    level: int | None = None
    refinement: int | None = None
    character: str | None = None
    locked: bool = False
    notes: str | None = None
    data: dict = Field(default_factory=dict)
    source: str | None = None
    verified: bool = False


class EquipmentUpdate(BaseModel):
    display_name: str | None = None
    rarity: int | str | None = None
    level: int | None = None
    refinement: int | None = None
    character: str | None = None
    unset_character: bool = False
    locked: bool | None = None
    notes: str | None = None
    data: dict | None = None
    verified: bool = False


class GearCreate(BaseModel):
    set_key: str | None = None
    slot: str | None = None
    rarity: int | str | None = None
    level: int | None = None
    main_stat_key: str | None = None
    main_stat_value: float | None = None
    substats: list[dict] = Field(default_factory=list)
    character: str | None = None
    locked: bool = False
    favorite: bool = False
    notes: str | None = None
    data: dict = Field(default_factory=dict)
    source: str | None = None
    verified: bool = False


class GearUpdate(BaseModel):
    set_key: str | None = None
    slot: str | None = None
    rarity: int | str | None = None
    level: int | None = None
    main_stat_key: str | None = None
    main_stat_value: float | None = None
    substats: list[dict] | None = None
    character: str | None = None
    unset_character: bool = False
    locked: bool | None = None
    favorite: bool | None = None
    notes: str | None = None
    data: dict | None = None
    verified: bool = False


class TeamSave(BaseModel):
    name: str
    members: list[dict]
    notes: str | None = None
    is_active: bool | None = None


class TeamUpdate(BaseModel):
    name: str | None = None
    members: list[dict] | None = None
    notes: str | None = None
    is_active: bool | None = None


class ResourcePut(BaseModel):
    quantity: int
    notes: str | None = None


class PlanPut(BaseModel):
    entries: list[dict]  # [{character: id-or-key, amount: int}]


class CodeCreate(BaseModel):
    code: str
    status: str = "active"
    expires_at: str | None = None
    source_key: str | None = None
    notes: str | None = None


class CodeUpdate(BaseModel):
    status: str | None = None
    expires_at: str | None = None
    notes: str | None = None


class CombatResultCreate(BaseModel):
    encounter_key: str
    encounter_slot: str | None = None
    played_at: str | None = None
    team_id: str | None = None
    score: float | None = None
    rank: str | None = None
    stars: int | None = None
    cleared: bool | None = None
    clear_time_seconds: float | None = None
    retries: int | None = None
    difficulty: str | None = None
    notes: str | None = None


class TrainingIssueCreate(BaseModel):
    category: str
    description: str
    severity: str = "medium"
    character_keys: list[str] = Field(default_factory=list)
    notes: str | None = None


class TrainingIssueUpdate(BaseModel):
    status: str | None = None
    severity: str | None = None
    description: str | None = None
    notes: str | None = None


class TrainingGoalCreate(BaseModel):
    description: str
    target: dict | None = None


class TrainingGoalUpdate(BaseModel):
    status: str | None = None
    progress_notes: str | None = None


class SourceSeed(BaseModel):
    seed_defaults: bool = False
    key: str | None = None
    name: str | None = None
    url: str | None = None
    category: str = "wiki"
    trust: int = 3
    notes: str | None = None


class ClaimCreate(BaseModel):
    subject: str
    claim_type: str
    content: str
    source_key: str | None = None
    confidence: float | None = None
    evidence: list[dict] = Field(default_factory=list)


class ResearchQuery(BaseModel):
    question: str
    subject: str | None = None


class ImportCreate(BaseModel):
    screen_type: str
    image_base64: str | None = None
    screenshot_name: str | None = None
    character_hint: str | None = None
    # Manual candidate (no LLM): validated against the adapter schema.
    candidate: dict | None = None


class TeamRecommendationRequest(BaseModel):
    encounter: str | None = None
    count: int = 5
    respect_active_teams: bool = True


class OptimizeRequest(BaseModel):
    encounter_key: str
    objective: str = "maximize_total"  # maximize_total|maximize_clears|maximize_comfort
    comfort_weight: float = 0.0


class GearEvaluateRequest(BaseModel):
    character: str | None = None


class EquipmentCompareRequest(BaseModel):
    character: str
    item_ids: list[str] | None = None


class TutorRequest(BaseModel):
    character: str
    topic: str = "kit"  # kit|rotation|team_rotation|mechanic
    mode: str = "simple"  # simple|advanced|button_by_button
    persona_id: str | None = None


class PersonaCreate(BaseModel):
    persona: dict

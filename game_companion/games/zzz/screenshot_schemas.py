"""ZZZ screenshot extraction schemas (typed candidates for vision ingestion).

Every field is optional: the VLM must use null for anything it cannot read
confidently rather than guessing. Validation rejects impossible values.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class _Confidence(BaseModel):
    extraction_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class AgentOverviewCandidate(_Confidence):
    # Generic keys (core vocabulary); ZZZ prompts map screen labels onto them,
    # e.g. the Mindscape rank is extracted into ``duplication_level``.
    character_name: str | None = None
    character_key: str | None = None
    level: int | None = Field(default=None, ge=1, le=60)
    duplication_level: int | None = Field(default=None, ge=0, le=6)
    attribute: str | None = None
    specialty: str | None = None
    faction: str | None = None


class SkillEntry(BaseModel):
    key: str | None = None
    name: str | None = None
    level: int | None = Field(default=None, ge=0, le=12)


class SkillsCandidate(_Confidence):
    character_name: str | None = None
    skills: list[SkillEntry] = Field(default_factory=list)


class WEngineCandidate(_Confidence):
    character_name: str | None = None
    equipment_name: str | None = None
    equipment_key: str | None = None
    level: int | None = Field(default=None, ge=1, le=60)
    refinement: int | None = Field(default=None, ge=1, le=5)


class DriveDiscBrief(BaseModel):
    slot: str | None = None
    set_name: str | None = None
    rarity: str | None = None
    level: int | None = Field(default=None, ge=0, le=15)
    main_stat_key: str | None = None
    main_stat_value: float | None = None


class DriveDiscListCandidate(_Confidence):
    character_name: str | None = None
    discs: list[DriveDiscBrief] = Field(default_factory=list)


class DiscSubstat(BaseModel):
    key: str | None = None
    value: float | None = None
    rolls: int | None = Field(default=None, ge=1, le=6)


class DriveDiscDetailCandidate(_Confidence):
    slot: str | None = None
    set_name: str | None = None
    set_key: str | None = None
    rarity: str | None = None
    level: int | None = Field(default=None, ge=0, le=15)
    main_stat_key: str | None = None
    main_stat_value: float | None = None
    substats: list[DiscSubstat] = Field(default_factory=list)

    @field_validator("substats")
    @classmethod
    def _max_substats(cls, v: list[DiscSubstat]) -> list[DiscSubstat]:
        if len(v) > 4:
            raise ValueError("a Drive Disc has at most 4 substats")
        return v


class ResourceEntry(BaseModel):
    key: str | None = None
    name: str | None = None
    quantity: int | None = Field(default=None, ge=0)


class ResourcesCandidate(_Confidence):
    resources: list[ResourceEntry] = Field(default_factory=list)

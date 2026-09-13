"""Research layer storage: sources, claims with evidence, change records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from game_companion.db.base import Base, PKMixin, TimestampMixin, UTCDateTime

# Claim types, ordered by decreasing authority.
CLAIM_OFFICIAL_FACT = "official_fact"
CLAIM_MECHANICS = "mechanics"
CLAIM_BUILD_RECOMMENDATION = "build_recommendation"
CLAIM_CONSENSUS = "community_consensus"
CLAIM_SPECULATION = "speculation"
CLAIM_TYPES = (
    CLAIM_OFFICIAL_FACT,
    CLAIM_MECHANICS,
    CLAIM_BUILD_RECOMMENDATION,
    CLAIM_CONSENSUS,
    CLAIM_SPECULATION,
)

# Review workflow for detected changes.
CHANGE_PENDING = "pending"
CHANGE_APPROVED = "approved"
CHANGE_REJECTED = "rejected"
CHANGE_APPLIED = "applied"


class ResearchSource(PKMixin, TimestampMixin, Base):
    __tablename__ = "research_sources"
    __table_args__ = (UniqueConstraint("game_id", "key", name="uq_source_key"),)

    game_id: Mapped[str] = mapped_column(String(40), index=True)  # may be "global"
    key: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(160))
    url: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(40))  # official|announcements|database|build_guide|wiki|community
    trust: Mapped[int] = mapped_column(Integer, default=3)  # 1..5, higher = more trusted
    last_accessed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)
    content_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)


class ResearchClaim(PKMixin, TimestampMixin, Base):
    __tablename__ = "research_claims"

    game_id: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_sources.id", ondelete="SET NULL"), default=None
    )
    subject: Mapped[str] = mapped_column(String(120), index=True)  # entity key or "global"
    claim_type: Mapped[str] = mapped_column(String(40))
    content: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float, default=None)
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=None)
    # List of {"url", "quote", "retrieved_at"} evidence items backing the claim.
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)


class ChangeRecord(PKMixin, TimestampMixin, Base):
    """A detected difference vs. known state, awaiting review (M19 workflow:
    detect -> report -> review/confirm -> update; never silent mutation)."""

    __tablename__ = "change_records"

    game_id: Mapped[str] = mapped_column(String(40), index=True)
    entity_type: Mapped[str] = mapped_column(String(60))  # e.g. "character", "source_fact", "code"
    entity_key: Mapped[str] = mapped_column(String(120))
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=None)
    previous_value: Mapped[dict | None] = mapped_column(JSON, default=None)
    proposed_value: Mapped[dict] = mapped_column(JSON, default=dict)
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_sources.id", ondelete="SET NULL"), default=None
    )
    evidence: Mapped[list | None] = mapped_column(JSON, default=None)
    confidence: Mapped[float | None] = mapped_column(Float, default=None)
    review_status: Mapped[str] = mapped_column(String(20), default=CHANGE_PENDING, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)
    applied_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)

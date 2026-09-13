"""Teams and team members.

A character may appear in any number of *saved* teams, but at most one *active*
team (mutual exclusion for simultaneous endgame allocation is enforced in the
TeamService and exercised by the optimizer).
"""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from game_companion.db.base import Base, PKMixin, TimestampMixin


class Team(PKMixin, TimestampMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("game_id", "player_profile_id", "name", name="uq_team_name"),)

    game_id: Mapped[str] = mapped_column(String(40), index=True)
    player_profile_id: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    data: Mapped[dict] = mapped_column(JSON, default=dict)

    members: Mapped[list[TeamMember]] = relationship(
        back_populates="team", cascade="all, delete-orphan", lazy="selectin",
        order_by="TeamMember.position",
    )


class TeamMember(PKMixin, Base):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "character_id", name="uq_team_member"),)

    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[str] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    role: Mapped[str | None] = mapped_column(String(40), default=None)
    data: Mapped[dict] = mapped_column(JSON, default=dict)

    team: Mapped[Team] = relationship(back_populates="members")

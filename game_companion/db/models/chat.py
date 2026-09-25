"""Built-in chat (M22): conversations, messages, companion memories.

Messages use an integer autoincrement PK so transcript ordering is stable;
everything else uses the standard string PK convention.
"""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from game_companion.db.base import Base, PKMixin, TimestampMixin


class Conversation(PKMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    game_id: Mapped[str] = mapped_column(String(40), index=True)
    player_profile_id: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="New chat")
    persona_id: Mapped[str | None] = mapped_column(String(80), default=None)

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="ChatMessage.id"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # user | assistant | tool
    content: Mapped[str] = mapped_column(Text, default="")
    # assistant: raw tool_calls payload; tool: which call this row answers.
    tool_calls: Mapped[dict | None] = mapped_column(JSON, default=None)
    tool_call_id: Mapped[str | None] = mapped_column(String(80), default=None)
    tool_name: Mapped[str | None] = mapped_column(String(80), default=None)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class CompanionMemory(PKMixin, TimestampMixin, Base):
    """Durable player notes the model may propose and the user always controls."""

    __tablename__ = "companion_memories"

    player_profile_id: Mapped[str] = mapped_column(
        ForeignKey("player_profiles.id", ondelete="CASCADE"), index=True
    )
    game_id: Mapped[str | None] = mapped_column(String(40), default=None)  # null = all games
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | assistant
    active: Mapped[bool] = mapped_column(Boolean, default=True)

"""Redeem-code service (M8): tracking + #CODES markdown rendering."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from game_companion.core.games.base import GameAdapter
from game_companion.db.repositories import CodeRepository
from game_companion.errors import ValidationError


class CodeService:
    def __init__(self, session: Session, adapter: GameAdapter) -> None:
        self.session = session
        self.adapter = adapter
        self.codes = CodeRepository(session)

    def add_code(
        self,
        code: str,
        *,
        status: str = "active",
        expires_at: str | None = None,
        notes: str | None = None,
    ):
        from game_companion.db.models import RedeemCode

        if self.codes.find_by_code(self.adapter.game_id, code):
            raise ValidationError(f"code '{code}' already tracked")
        parsed_expiry = None
        if expires_at:
            try:
                parsed_expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValidationError(f"invalid expires_at: {exc}") from exc
        from game_companion.utils import utcnow

        return self.codes.add(
            RedeemCode(
                game_id=self.adapter.game_id,
                code=code,
                status=status,
                expires_at=parsed_expiry,
                discovered_at=utcnow(),
                notes=notes,
            )
        )

    def list_codes(self, player_id: str) -> list[tuple]:
        out = []
        for code_row in self.codes.list_all(game_id=self.adapter.game_id):
            state = self.codes.player_state(code_row.id, player_id)
            out.append((code_row, state))
        return out

    def mark_used(self, code_id: str, player_id: str, used: bool):
        return self.codes.set_player_state(code_id, player_id, used)

    def render_codes_markdown(self, player_id: str) -> str:
        """#CODES output. Used codes are struck through but NOT hidden forever:
        recycled codes come back marked with ♻."""
        active, used, other = [], [], []
        for code_row, state in self.list_codes(player_id):
            entry = (code_row.code, code_row.expires_at, code_row.status, code_row.notes)
            if state and state.used:
                used.append(entry)
            elif code_row.status in ("active", "recycled"):
                active.append(entry)
            else:
                other.append(entry)

        lines = [f"# Redeem codes — {self.adapter.display_name}", ""]
        if active:
            lines.append("**Active / reactivated:**")
            for code, expires_at, status, _notes in sorted(active):
                suffix = " ♻ reactivated" if status == "recycled" else ""
                when = f" — expires {expires_at:%Y-%m-%d}" if expires_at else ""
                lines.append(f"- `{code}`{when}{suffix}")
        else:
            lines.append("_No active codes tracked._")
        if used:
            lines.append("")
            lines.append("**Already used:**")
            for code, _e, status, _n in sorted(used):
                recycled = " (code may be recycled later — watch official channels)" if status == "recycled" else ""
                lines.append(f"- ~~`{code}`~~{recycled}")
        if other:
            lines.append("")
            lines.append("**Expired / unknown:**")
            for code, _e, status, _n in sorted(other):
                lines.append(f"- `{code}` ({status})")
        lines.append("")
        lines.append(f"_Sources: {', '.join(self.adapter.code_config().get('discovery_source_keys', [])) or 'n/a'}_")
        return "\n".join(lines)

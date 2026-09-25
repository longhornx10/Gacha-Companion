"""Built-in chat agent loop (M22).

Server-side, non-streaming, in-process: the loop calls core services directly
(never HTTP-calls its own API), persists every step including tool calls, and
treats tool results as the only source of account facts. The persona shapes
tone only. The model may PROPOSE a companion memory via a tool — it can never
silently change stored data.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from game_companion.api.serialize import build_dict, character_dict
from game_companion.core.codes.service import CodeService
from game_companion.core.games.base import GameAdapter
from game_companion.core.roster.service import RosterService
from game_companion.db.models import ChatMessage, CompanionMemory, Conversation
from game_companion.db.repositories import (
    CharacterRepository,
    ResourceRepository,
    TeamRepository,
)
from game_companion.errors import LLMError, NotFoundError, ValidationError

MAX_ITERATIONS = 6
HONESTY_RULES = (
    "You are a gacha companion with access to tools that read the player's "
    "authoritative account data from a local database.\n"
    "Rules:\n"
    "- For ANY question about the player's own account (roster, gear, teams, "
    "resources, codes), FIRST call the relevant tool to fetch current state. "
    "Never answer account questions from memory or assumption.\n"
    "- Unknown data stays unknown: say what is not recorded rather than "
    "guessing numbers.\n"
    "- Scores and ratings you see are labeled heuristics, not measured DPS.\n"
    "- Use the game's own terms as given in the terminology section.\n"
    "- You may propose saving a lasting player preference with propose_memory; "
    "it is stored visibly and the player can edit or delete it."
)


class ChatService:
    def __init__(self, session: Session, adapter: GameAdapter, player_id: str, llm: Any) -> None:
        self.session = session
        self.adapter = adapter
        self.player_id = player_id
        self.llm = llm

    # -- conversations ---------------------------------------------------------

    def list_conversations(self) -> list[Conversation]:
        from sqlalchemy import select

        stmt = (
            select(Conversation)
            .where(
                Conversation.game_id == self.adapter.game_id,
                Conversation.player_profile_id == self.player_id,
            )
            .order_by(Conversation.updated_at.desc())
        )
        return list(self.session.scalars(stmt))

    def create_conversation(self, persona_id: str | None = None, title: str = "New chat") -> Conversation:
        conv = Conversation(
            game_id=self.adapter.game_id,
            player_profile_id=self.player_id,
            title=title,
            persona_id=persona_id,
        )
        self.session.add(conv)
        self.session.flush()
        return conv

    def get_conversation(self, conversation_id: str) -> Conversation:
        conv = self.session.get(Conversation, conversation_id)
        if conv is None or conv.player_profile_id != self.player_id:
            raise NotFoundError("conversation not found")
        return conv

    def rename_conversation(self, conversation_id: str, title: str) -> Conversation:
        conv = self.get_conversation(conversation_id)
        if title.strip():
            conv.title = title.strip()[:200]
        self.session.flush()
        return conv

    def delete_conversation(self, conversation_id: str) -> None:
        self.session.delete(self.get_conversation(conversation_id))
        self.session.flush()

    # -- memories ---------------------------------------------------------------

    def memories(self, include_inactive: bool = False) -> list[CompanionMemory]:
        from sqlalchemy import select

        stmt = select(CompanionMemory).where(
            CompanionMemory.player_profile_id == self.player_id
        )
        if not include_inactive:
            stmt = stmt.where(CompanionMemory.active.is_(True))
        return list(self.session.scalars(stmt.order_by(CompanionMemory.created_at)))

    def add_memory(self, content: str, source: str = "manual", game_id: str | None = None) -> CompanionMemory:
        if not content.strip():
            raise ValidationError("memory content is empty")
        row = CompanionMemory(
            player_profile_id=self.player_id,
            game_id=game_id if game_id else self.adapter.game_id,
            content=content.strip(),
            source=source,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def update_memory(self, memory_id: str, *, content: str | None = None, active: bool | None = None) -> CompanionMemory:
        row = self.session.get(CompanionMemory, memory_id)
        if row is None or row.player_profile_id != self.player_id:
            raise NotFoundError("memory not found")
        if content is not None and content.strip():
            row.content = content.strip()
        if active is not None:
            row.active = active
        self.session.flush()
        return row

    def delete_memory(self, memory_id: str) -> None:
        row = self.session.get(CompanionMemory, memory_id)
        if row is None or row.player_profile_id != self.player_id:
            raise NotFoundError("memory not found")
        self.session.delete(row)
        self.session.flush()

    # -- the loop ----------------------------------------------------------------

    def send(self, conversation_id: str, user_text: str) -> dict:
        conv = self.get_conversation(conversation_id)
        if not user_text.strip():
            raise ValidationError("message is empty")
        if not getattr(self.llm, "configured", False):
            raise LLMError(
                "no LLM endpoint configured — set GAME_COMPANION_LLM_* in .env to chat"
            )

        user_row = ChatMessage(conversation_id=conv.id, role="user", content=user_text.strip())
        self.session.add(user_row)
        if conv.title == "New chat":
            conv.title = user_text.strip()[:60]
        self.session.flush()

        messages = [self._system_prompt(conv), *self._history(conv)]
        tools = self._tool_schemas()
        iterations = 0
        while iterations < MAX_ITERATIONS:
            iterations += 1
            try:
                assistant = self.llm.chat_with_tools(messages, tools=tools)
            except LLMError as exc:
                self.session.add(
                    ChatMessage(
                        conversation_id=conv.id,
                        role="assistant",
                        content=f"(chat failed: {exc})",
                    )
                )
                self.session.flush()
                self.session.expire(conv, ["messages"])
                raise
            tool_calls = assistant.get("tool_calls") or []
            self.session.add(
                ChatMessage(
                    conversation_id=conv.id,
                    role="assistant",
                    content=assistant.get("content") or "",
                    tool_calls=tool_calls or None,
                )
            )
            self.session.flush()
            if not tool_calls:
                self.session.flush()
                self.session.expire(conv, ["messages"])
                return {"conversation_id": conv.id, "iterations": iterations, "done": True}
            messages = messages + [assistant]
            for call in tool_calls:
                function = call.get("function", {})
                name = function.get("name", "")
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                result = self._execute_tool(name, arguments)
                self.session.add(
                    ChatMessage(
                        conversation_id=conv.id,
                        role="tool",
                        content=result,
                        tool_call_id=call.get("id"),
                        tool_name=name,
                    )
                )
                self.session.flush()
                messages = messages + [
                    {"role": "tool", "tool_call_id": call.get("id"), "content": result}
                ]
        # iteration guard: force a final answer without tools
        final = self.llm.chat_with_tools(messages, tools=None)
        self.session.add(
            ChatMessage(conversation_id=conv.id, role="assistant", content=final.get("content") or "")
        )
        self.session.flush()
        self.session.expire(conv, ["messages"])
        return {"conversation_id": conv.id, "iterations": iterations, "done": True}

    def _system_prompt(self, conv: Conversation) -> dict:
        from game_companion.config import get_settings
        from game_companion.core.games.terminology import terminology_block
        from game_companion.core.persona.store import PersonaStore

        terminology = terminology_block(
            self.adapter.display_name, self.adapter.terminology_table()
        )
        persona_id = conv.persona_id
        persona_fragment = ""
        if persona_id:
            try:
                persona = PersonaStore(get_settings()).get(persona_id)
                persona_fragment = persona.system_prompt_fragment()
            except NotFoundError:
                persona_fragment = ""
        memories = [
            m.content
            for m in self.memories()
            if m.active and (m.game_id is None or m.game_id == self.adapter.game_id)
        ]
        memory_block = (
            "Lasting player preferences (from the player, editable in Settings):\n"
            + "\n".join(f"- {m}" for m in memories)
            if memories
            else ""
        )
        parts = [HONESTY_RULES, terminology]
        if persona_fragment:
            parts.append(persona_fragment)
        if memory_block:
            parts.append(memory_block)
        return {"role": "system", "content": "\n\n".join(parts)}

    def _history(self, conv: Conversation, limit: int = 40) -> list[dict]:
        rows = list(conv.messages[-limit:])
        out = []
        for row in rows:
            if row.role == "tool":
                out.append(
                    {"role": "tool", "tool_call_id": row.tool_call_id, "content": row.content}
                )
            elif row.role == "assistant" and row.tool_calls:
                message = {"role": "assistant", "content": row.content or ""}
                message["tool_calls"] = row.tool_calls
                out.append(message)
            else:
                out.append({"role": row.role, "content": row.content})
        return out

    # -- tools (in-process service calls) -----------------------------------------

    def _tool_schemas(self) -> list[dict]:
        term = self.adapter.terminology()
        return [
            {
                "type": "function",
                "function": {
                    "name": "list_characters",
                    "description": f"List the player's owned {term.character_plural.lower()} with level and {term.duplication.lower()}.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_character",
                    "description": f"Full detail for one {term.character.lower()}: skills, builds, equipment, gear.",
                    "parameters": {
                        "type": "object",
                        "properties": {"ref": {"type": "string", "description": f"{term.character} key or name"}},
                        "required": ["ref"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_teams",
                    "description": "List saved teams and which one is active.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_resources",
                    "description": "Resource counters with deterministic plan-based statuses.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_resource",
                    "description": "Record a resource quantity the player states in chat.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "resource_key": {"type": "string"},
                            "quantity": {"type": "integer"},
                        },
                        "required": ["resource_key", "quantity"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_codes",
                    "description": "Redeem codes with status and which are used.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "mark_code_used",
                    "description": "Mark a redeem code as used by the player.",
                    "parameters": {
                        "type": "object",
                        "properties": {"code": {"type": "string"}},
                        "required": ["code"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "propose_memory",
                    "description": "Save a lasting player preference (e.g. 'prefers burst DPS', 'skips tower modes'). Visible to the player, who can edit or delete it.",
                    "parameters": {
                        "type": "object",
                        "properties": {"content": {"type": "string"}},
                        "required": ["content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Web search for anything you don't know (new characters, patch changes, meta opinions). Prefer gacha wikis and official sources in follow-up reading.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_page",
                    "description": "Read the text content of a web page (usually a search_web hit) before answering from it.",
                    "parameters": {
                        "type": "object",
                        "properties": {"url": {"type": "string"}},
                        "required": ["url"],
                    },
                },
            },
        ]

    def _execute_tool(self, name: str, args: dict) -> str:
        try:
            return json.dumps(self._dispatch(name, args), ensure_ascii=False)
        except Exception as exc:  # tool errors go back to the model, honestly
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

    def _dispatch(self, name: str, args: dict) -> Any:
        game_id = self.adapter.game_id
        if name == "list_characters":
            chars = CharacterRepository(self.session).search(game_id, self.player_id, owned=True)
            term = self.adapter.terminology()
            return [
                {
                    "key": c.key,
                    "name": c.display_name,
                    "level": c.level,
                    term.duplication.lower(): c.duplication_level,
                }
                for c in chars
            ]
        if name == "get_character":
            roster = RosterService(self.session, self.adapter)
            char = roster.resolve_character(game_id, self.player_id, str(args.get("ref", "")))
            out = character_dict(char)
            out["builds"] = [build_dict(b) for b in roster.builds.for_character(char.id)]
            return out
        if name == "list_teams":
            by_id = {c.id: c for c in CharacterRepository(self.session).search(game_id, self.player_id)}
            return [
                {
                    "name": t.name,
                    "is_active": t.is_active,
                    "members": [by_id[m.character_id].key if m.character_id in by_id else "?" for m in t.members],
                }
                for t in TeamRepository(self.session).list_all(game_id=game_id, player_profile_id=self.player_id)
            ]
        if name == "get_resources":
            from game_companion.core.resources.service import ResourceService

            return ResourceService(self.session, self.adapter).list_with_status(game_id, self.player_id)
        if name == "set_resource":
            resource_key = str(args.get("resource_key", "")).strip()
            if not resource_key:
                raise ValidationError("resource_key is required to track a resource")
            quantity = int(args.get("quantity", 0))
            if quantity < 0:
                raise ValidationError("quantity cannot be negative")
            row = ResourceRepository(self.session).upsert(
                game_id, self.player_id, resource_key, quantity
            )
            return {"resource_key": row.resource_key, "quantity": row.quantity}
        if name == "list_codes":
            return [
                {"code": c.code, "status": c.status, "used": bool(s and s.used)}
                for c, s in CodeService(self.session, self.adapter).list_codes(self.player_id)
            ]
        if name == "mark_code_used":
            from game_companion.db.repositories import CodeRepository

            repo = CodeRepository(self.session)
            wanted = str(args.get("code", "")).strip().upper()
            for row in repo.list_all(game_id=game_id):
                if row.code.upper() == wanted:
                    state = CodeService(self.session, self.adapter).mark_used(row.id, self.player_id, True)
                    return {"code": row.code, "used": True, "used_at": str(state.used_at)}
            return {"error": f"no known code '{wanted}'"}
        if name == "propose_memory":
            row = self.add_memory(str(args.get("content", "")), source="assistant")
            return {"saved": True, "id": row.id, "content": row.content, "note": "player can edit/delete in Settings"}
        if name == "search_web":
            from game_companion.config import get_settings
            from game_companion.core.research.service import provider_from_settings

            hits = provider_from_settings(get_settings()).search(
                str(args.get("query", "")), limit=5
            )
            return [
                {"title": h.title, "url": h.url, "snippet": h.snippet} for h in hits
            ]
        if name == "read_page":
            from game_companion.core.research.service import fetch_text

            url = str(args.get("url", ""))
            if not url.lower().startswith(("http://", "https://")):
                raise ValidationError("read_page needs an http(s) URL")
            return {"url": url, "text": fetch_text(url)}
        raise ValidationError(f"unknown tool '{name}'")

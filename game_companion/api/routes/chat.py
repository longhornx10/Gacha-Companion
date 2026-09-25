"""Chat API (M22): conversations, messages, companion memories."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from game_companion.api.deps import adapter_for, get_db, resolve_player
from game_companion.core.chat.service import ChatService

router = APIRouter(prefix="/games/{game_id}")


def _service(request: Request, session: Session, game_id: str, player_id: str) -> ChatService:
    return ChatService(session, adapter_for(game_id), player_id, request.app.state.llm)


class ConversationCreate(BaseModel):
    persona_id: str | None = None
    title: str = "New chat"


class MessageSend(BaseModel):
    text: str


class ConversationPatch(BaseModel):
    title: str | None = None
    persona_id: str | None = None


class MemoryCreate(BaseModel):
    content: str
    game_id: str | None = None


class MemoryPatch(BaseModel):
    content: str | None = None
    active: bool | None = None


def _conversation_dict(conv) -> dict:
    return {
        "id": conv.id,
        "game_id": conv.game_id,
        "title": conv.title,
        "persona_id": conv.persona_id,
        "created_at": str(conv.created_at),
        "updated_at": str(conv.updated_at),
    }


def _message_dict(m) -> dict:
    out = {"id": m.id, "role": m.role, "content": m.content}
    if m.tool_calls:
        out["tool_calls"] = [
            call.get("function", {}).get("name") for call in m.tool_calls if isinstance(call, dict)
        ]
    if m.tool_name:
        out["tool_name"] = m.tool_name
    return out


@router.get("/chat/conversations")
def list_conversations(game_id: str, request: Request, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = _service(request, session, game_id, player.id)
    return {"conversations": [_conversation_dict(c) for c in service.list_conversations()]}


@router.post("/chat/conversations", status_code=201)
def create_conversation(game_id: str, payload: ConversationCreate, request: Request, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = _service(request, session, game_id, player.id)
    conv = service.create_conversation(persona_id=payload.persona_id, title=payload.title)
    return _conversation_dict(conv)


@router.get("/chat/conversations/{conversation_id}")
def get_conversation(game_id: str, conversation_id: str, request: Request, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = _service(request, session, game_id, player.id)
    conv = service.get_conversation(conversation_id)
    out = _conversation_dict(conv)
    out["messages"] = [_message_dict(m) for m in conv.messages]
    return out


@router.patch("/chat/conversations/{conversation_id}")
def patch_conversation(game_id: str, conversation_id: str, payload: ConversationPatch, request: Request, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = _service(request, session, game_id, player.id)
    conv = service.get_conversation(conversation_id)
    if payload.title is not None:
        service.rename_conversation(conversation_id, payload.title)
    if payload.persona_id is not None:
        conv.persona_id = payload.persona_id or None
    session.flush()
    return _conversation_dict(conv)


@router.delete("/chat/conversations/{conversation_id}")
def delete_conversation(game_id: str, conversation_id: str, request: Request, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = _service(request, session, game_id, player.id)
    service.delete_conversation(conversation_id)
    return {"deleted": conversation_id}


@router.post("/chat/conversations/{conversation_id}/messages")
def send_message(game_id: str, conversation_id: str, payload: MessageSend, request: Request, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = _service(request, session, game_id, player.id)
    result = service.send(conversation_id, payload.text)
    conv = service.get_conversation(conversation_id)
    result["messages"] = [_message_dict(m) for m in conv.messages]
    return result


# -- companion memories -------------------------------------------------------------


@router.get("/chat/memories")
def list_memories(game_id: str, request: Request, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = _service(request, session, game_id, player.id)
    return {
        "memories": [
            {"id": m.id, "content": m.content, "source": m.source, "active": m.active,
             "game_id": m.game_id}
            for m in service.memories(include_inactive=True)
        ]
    }


@router.post("/chat/memories", status_code=201)
def add_memory(game_id: str, payload: MemoryCreate, request: Request, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = _service(request, session, game_id, player.id)
    row = service.add_memory(payload.content, source="manual", game_id=payload.game_id)
    return {"id": row.id, "content": row.content, "source": row.source, "active": row.active}


@router.patch("/chat/memories/{memory_id}")
def patch_memory(game_id: str, memory_id: str, payload: MemoryPatch, request: Request, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = _service(request, session, game_id, player.id)
    row = service.update_memory(memory_id, content=payload.content, active=payload.active)
    return {"id": row.id, "content": row.content, "source": row.source, "active": row.active}


@router.delete("/chat/memories/{memory_id}")
def delete_memory(game_id: str, memory_id: str, request: Request, session: Session = Depends(get_db), player=Depends(resolve_player)):
    service = _service(request, session, game_id, player.id)
    service.delete_memory(memory_id)
    return {"deleted": memory_id}

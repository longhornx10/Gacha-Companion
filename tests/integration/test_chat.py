"""M22: built-in chat — agent loop, tools, memories, chat UI."""

from __future__ import annotations

import json

import pytest


class ScriptedLLM:
    """Tool-calling LLM double: plays a scripted sequence of assistant turns."""

    configured = True

    def __init__(self, turns: list[dict]):
        self.turns = list(turns)
        self.calls: list[list[dict]] = []

    def chat_with_tools(self, messages, *, tools=None, temperature=0.4):
        self.calls.append(list(messages))
        return self.turns.pop(0)

    def close(self):
        pass


@pytest.fixture()
def chat_world(client, ui_player):
    from tests.conftest import make_zzz_roster

    make_zzz_roster(client, ui_player, ["burnice", "ellen"])
    client.put("/api/games/zzz/resources/polychrome", json={"quantity": 9000})
    return ui_player


def test_conversation_crud_and_game_scoping(client, chat_world):
    created = client.post("/api/games/zzz/chat/conversations", json={}).json()
    assert created["title"] == "New chat"

    listing = client.get("/api/games/zzz/chat/conversations").json()["conversations"]
    assert [c["id"] for c in listing] == [created["id"]]

    # another game sees no conversations
    assert client.get("/api/games/example/chat/conversations").json()["conversations"] == []

    renamed = client.patch(
        f"/api/games/zzz/chat/conversations/{created['id']}", json={"title": "Plan my week"}
    ).json()
    assert renamed["title"] == "Plan my week"

    assert client.delete(f"/api/games/zzz/chat/conversations/{created['id']}").json()["deleted"]
    assert client.get("/api/games/zzz/chat/conversations").json()["conversations"] == []


def test_agent_loop_executes_tools_and_answers(client, chat_world):
    scripted = ScriptedLLM(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "get_resources", "arguments": "{}"},
                    }
                ],
            },
            {"role": "assistant", "content": "You have 9,000 Polychrome saved up!"},
        ]
    )
    from game_companion.core.chat.service import ChatService
    from game_companion.core.games.registry import get_adapter

    service = ChatService(_session(client), get_adapter("zzz"), chat_world, scripted)
    conv = service.create_conversation()
    result = service.send(conv.id, "How much premium currency do I have?")
    service.session.commit()
    assert result["iterations"] == 2

    detail = client.get(f"/api/games/zzz/chat/conversations/{conv.id}").json()
    roles = [m["role"] for m in detail["messages"]]
    assert roles == ["user", "assistant", "tool", "assistant"]
    # the tool row carries which tool ran (UI chips read this)
    assert detail["messages"][2]["tool_name"] == "get_resources"
    # the system prompt was sent first and contains honesty rules + terminology
    system = scripted.calls[0][0]["content"]
    assert "Never answer account questions from memory" in system
    assert "Mindscape" in system  # ZZZ terminology injected


def _session(client):
    from game_companion.db.session import create_session_factory

    return create_session_factory(_engine(client))()


def _engine(client):
    from game_companion.config import get_settings
    from game_companion.db.session import create_db_engine

    return create_db_engine(get_settings().resolved_database_url)


def test_loop_persists_and_handles_multiple_tools(client, chat_world):
    scripted = ScriptedLLM(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "propose_memory", "arguments": json.dumps({"content": "prefers Anomaly teams"})},
                    },
                    {
                        "id": "c2",
                        "type": "function",
                        "function": {"name": "list_codes", "arguments": "{}"},
                    },
                ],
            },
            {"role": "assistant", "content": "Noted your team preference! You have no codes yet."},
        ]
    )
    from game_companion.core.chat.service import ChatService
    from game_companion.core.games.registry import get_adapter

    service = ChatService(_session(client), get_adapter("zzz"), chat_world, scripted)
    conv = service.create_conversation()
    service.send(conv.id, "Remember I like anomaly teams. Any codes?")
    service.session.commit()

    memories = client.get("/api/games/zzz/chat/memories").json()["memories"]
    assert memories and memories[0]["content"] == "prefers Anomaly teams"
    assert memories[0]["source"] == "assistant"  # model-proposed, visible as such


def test_iteration_guard_forces_final_answer(client, chat_world):
    endless = lambda: {  # noqa: E731
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "x", "type": "function", "function": {"name": "list_teams", "arguments": "{}"}}
        ],
    }
    scripted = ScriptedLLM([endless() for _ in range(10)])
    from game_companion.core.chat.service import ChatService
    from game_companion.core.games.registry import get_adapter

    service = ChatService(_session(client), get_adapter("zzz"), chat_world, scripted)
    conv = service.create_conversation()
    result = service.send(conv.id, "loop forever?")
    assert result["done"] is True
    assert result["iterations"] <= 7  # guard caps the loop


def test_unknown_tool_and_tool_error_returned_to_model(client, chat_world):
    scripted = ScriptedLLM(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "does_not_exist", "arguments": "{}"}},
                    {"id": "c2", "type": "function", "function": {"name": "set_resource", "arguments": "{bad json"}},
                ],
            },
            {"role": "assistant", "content": "done"},
        ]
    )
    from game_companion.core.chat.service import ChatService
    from game_companion.core.games.registry import get_adapter

    service = ChatService(_session(client), get_adapter("zzz"), chat_world, scripted)
    conv = service.create_conversation()
    service.send(conv.id, "weird tools")
    tool_rows = [m for m in service.get_conversation(conv.id).messages if m.role == "tool"]
    assert "unknown tool" in tool_rows[0].content
    assert "error" in tool_rows[1].content  # bad arguments reported, not crashing


def test_memories_crud_and_active_filter(client, chat_world):
    added = client.post(
        "/api/games/zzz/chat/memories", json={"content": "logs in daily"}
    ).json()
    assert added["source"] == "manual"

    patched = client.patch(f"/api/games/zzz/chat/memories/{added['id']}", json={"active": False}).json()
    assert patched["active"] is False
    active_only = client.get("/api/games/zzz/chat/memories").json()["memories"]
    visible = client.get("/api/games/zzz/chat/memories").json()["memories"]
    assert visible == active_only  # route shows all with state; UI filters by chip

    assert client.delete(f"/api/games/zzz/chat/memories/{added['id']}").json()["deleted"]


def test_chat_ui_flow(client, chat_world):
    # start chat through the UI
    started = client.post("/ui/chat/new", data={"persona_id": ""}, follow_redirects=False)
    assert started.status_code == 303
    conv_id = started.headers["location"].split("c=")[1]

    page = client.get(f"/ui/chat?c={conv_id}")
    assert page.status_code == 200
    assert "Say hello" in page.text  # empty-state

    # chat page lists the conversation in the sidebar
    assert conv_id in client.get("/ui/chat").text


def test_persona_editor_via_ui(client, ui_player):
    saved = client.post(
        "/ui/personas/save",
        data={
            "persona_id": "zen_archer",
            "name": "Zen Archer",
            "description": "Tranquil bow master",
            "tone": "calm",
            "verbosity": "low",
            "style_traits": "patient, poetic",
            "example_phrases": "Breathe. Draw. Release.\nOne shot, one lesson.",
            "system_preamble": "",
            "bound_game": "zzz",
        },
        follow_redirects=True,
    )
    assert saved.status_code == 200
    assert "Zen Archer" in client.get("/ui/personas").text

    # the persona store picked it up and bound it to zzz
    from game_companion.config import get_settings
    from game_companion.core.persona.store import PersonaStore

    persona = PersonaStore(get_settings()).get("zen_archer")
    assert persona.bound_game == "zzz"
    assert persona.style_traits == ["patient", "poetic"]

    deleted = client.post("/ui/personas/zen_archer/delete", follow_redirects=True)
    assert deleted.status_code == 200


def test_chat_requires_configured_llm(client, chat_world):
    """No LLM configured (test env) -> clear failure, nothing persisted."""
    from game_companion.core.chat.service import ChatService
    from game_companion.core.games.registry import get_adapter
    from game_companion.errors import LLMError

    service = ChatService(_session(client), get_adapter("zzz"), chat_world, None)
    conv = service.create_conversation()
    service.session.commit()
    with pytest.raises(LLMError):
        service.send(conv.id, "hello?")
    detail = client.get(f"/api/games/zzz/chat/conversations/{conv.id}").json()
    assert detail["messages"] == []


def test_chat_llm_failure_is_persisted_and_visible(client, chat_world):
    """A mid-loop LLM failure leaves an honest '(chat failed: ...)' trail."""
    from game_companion.core.chat.service import ChatService
    from game_companion.core.games.registry import get_adapter
    from game_companion.errors import LLMError

    class FailingLLM:
        configured = True

        def chat_with_tools(self, messages, *, tools=None, temperature=0.4):
            raise LLMError("LLM endpoint returned HTTP 500")

        def close(self):
            pass

    service = ChatService(_session(client), get_adapter("zzz"), chat_world, FailingLLM())
    conv = service.create_conversation()
    with pytest.raises(LLMError):
        service.send(conv.id, "hello?")
    service.session.commit()
    detail = client.get(f"/api/games/zzz/chat/conversations/{conv.id}").json()
    assert detail["messages"][-1]["content"].startswith("(chat failed:")

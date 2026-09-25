"""Vision probe (broker 'auto' routing) + built-in web search."""

from __future__ import annotations

import json

import httpx
import pytest

from game_companion.core.chat.service import ChatService
from game_companion.core.games.registry import get_adapter
from game_companion.core.llm.client import LLMClient
from game_companion.core.research.service import (
    DuckDuckGoProvider,
    provider_from_settings,
)
from game_companion.errors import SearchNotConfiguredError

DDG_HTML = """
<html><body>
<div class="result results_links">
  <h2 class="result__title"><a rel="nofollow" class="result__a"
     href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.prydwen.gg%2Fzenless%2Fcharacters%2Froxy&amp;rut=abc">
     Roxy build guide</a></h2>
  <a class="result__snippet" href="#">Roxy is a 3.2 Fire Attacker. Her best set is...</a>
</div>
<div class="result">
  <h2 class="result__title"><a class="result__a" href="https://example.com/page">Plain link</a></h2>
  <a class="result__snippet" href="#">Second result snippet text.</a>
</div>
</body></html>
"""


def _settings(searxng: str | None = None):
    class S:
        searxng_base_url = searxng

    return S()


# ---------------------------------------------------------------- vision probe

def _llm(handler) -> LLMClient:
    settings = type("S", (), {})()
    settings.llm_base_url = "https://broker.example/v1"
    settings.llm_api_key_plain = lambda: "k"
    settings.llm_model = "auto"  # broker auto-routing: name tells nothing
    settings.llm_timeout_seconds = 5
    settings.llm_vision_model = None
    return LLMClient(settings, transport=httpx.MockTransport(handler))


def test_probe_vision_true_when_endpoint_accepts_image():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content.decode()))
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    llm = _llm(handler)
    assert llm.probe_vision() is True
    assert llm.vision_capable is True  # cached: auto-routing now visible
    # the probe really sent an image part
    content = calls[0]["messages"][0]["content"]
    assert any(part["type"] == "image_url" for part in content)


def test_probe_vision_false_when_endpoint_refuses_image():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "model does not support image"}})

    llm = _llm(handler)
    assert llm.probe_vision() is False
    assert llm.vision_capable is False


def test_probe_runs_only_once():
    count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        count["n"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    llm = _llm(handler)
    llm.probe_vision()
    llm.probe_vision()
    assert count["n"] == 1


def test_manual_override_still_wins():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    settings = type("S", (), {})()
    settings.llm_base_url = "https://broker.example/v1"
    settings.llm_api_key_plain = lambda: "k"
    settings.llm_model = "anything"
    settings.llm_timeout_seconds = 5
    settings.llm_vision_model = False  # explicit override: never vision
    llm = LLMClient(settings, transport=httpx.MockTransport(handler))
    assert llm.vision_capable is False
    # the override short-circuits before any probing happens
    assert calls["n"] == 0


# ------------------------------------------------------------- built-in search

def test_ddg_provider_parses_results_and_unwraps_links(monkeypatch):
    captured = {}

    def fake_post(url, data=None, timeout=None, headers=None):
        captured["url"] = url
        captured["q"] = data["q"]
        return httpx.Response(200, text=DDG_HTML, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    hits = DuckDuckGoProvider().search("roxy zzz build", limit=5)
    assert captured["url"].startswith("https://html.duckduckgo.com")
    assert captured["q"] == "roxy zzz build"
    assert hits[0].url == "https://www.prydwen.gg/zenless/characters/roxy"
    assert hits[0].title == "Roxy build guide"
    assert "Fire Attacker" in hits[0].snippet
    assert hits[1].url == "https://example.com/page"


def test_ddg_provider_raises_honestly_when_blocked(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(
        200, text="<html>no results here</html>", request=httpx.Request("POST", "https://x")
    ))
    with pytest.raises(SearchNotConfiguredError):
        DuckDuckGoProvider().search("query")


def test_provider_chain_works_with_zero_configuration():
    provider = provider_from_settings(_settings(None))
    assert isinstance(provider._providers[0], DuckDuckGoProvider)


def test_provider_chain_prefers_searxng_and_falls_back(monkeypatch):
    calls = []

    class Failing:
        def search(self, q, *, limit=5):
            calls.append("searxng")
            raise RuntimeError("down")

    provider = provider_from_settings(_settings("http://localhost:8888"))
    monkeypatch.setattr(provider._providers[0], "search", Failing().search)
    monkeypatch.setattr(
        provider._providers[1], "search",
        lambda q, *, limit=5: (calls.append("ddg"), [type("H", (), {"title": "t", "url": "u", "snippet": ""})()])[1],
    )
    hits = provider.search("anything")
    assert calls == ["searxng", "ddg"]
    assert hits[0].title == "t"


# ------------------------------------------------------------------ chat tools

def test_chat_search_web_and_read_page_tools(monkeypatch):
    """The Home-chat assistant can look things up end to end (mocked network).

    Neither tool touches the DB, so a bare service (session=None) exercises
    exactly the model-facing tool path.
    """

    def ddg(url, data=None, timeout=None, headers=None):
        return httpx.Response(200, text=DDG_HTML, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", ddg)
    monkeypatch.setattr(
        "game_companion.core.research.service.httpx.get",
        lambda url, **k: httpx.Response(
            200, text="<html><body>Roxy is a Fire Attacker released in 3.2</body></html>",
            request=httpx.Request("GET", url),
        ),
    )

    service = ChatService(None, get_adapter("zzz"), "player", _llm_stub())
    parsed = json.loads(service._execute_tool("search_web", {"query": "roxy zzz"}))
    assert parsed[0]["url"] == "https://www.prydwen.gg/zenless/characters/roxy"
    page = json.loads(service._execute_tool("read_page", {"url": "https://example.com/x"}))
    assert "Fire Attacker" in page["text"]
    bad = json.loads(service._execute_tool("read_page", {"url": "ftp://nope"}))
    assert "error" in bad


def _llm_stub():
    class L:
        configured = False
        model = "stub"

    return L()

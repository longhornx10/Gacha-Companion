"""LLM abstraction (M4): transport-mocked client, validation, retry, redaction."""

import json

import httpx
import pytest
from pydantic import BaseModel

from game_companion.config import Settings
from game_companion.core.llm.client import LLMClient, _strip_code_fences, image_content_part
from game_companion.errors import LLMError


class Answer(BaseModel):
    summary: str
    level: int | None = None


def _settings_with_key() -> Settings:
    return Settings(llm_api_key="super-secret-key", llm_model="test-model")


def _transport(responses: list[dict | Exception]) -> httpx.MockTransport:
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return httpx.Response(200, json=item)

    return httpx.MockTransport(handler)


def _completion(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def test_complete_returns_content():
    client = LLMClient(
        _settings_with_key(),
        transport=_transport([_completion("hello")]),
    )
    assert client.complete([{"role": "user", "content": "hi"}]) == "hello"


def test_api_key_sent_but_never_in_errors():
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        return httpx.Response(500, json={"error": "boom"})

    client = LLMClient(_settings_with_key(), transport=httpx.MockTransport(handler))
    with pytest.raises(LLMError) as excinfo:
        client.complete([{"role": "user", "content": "hi"}])
    assert seen_headers.get("authorization") == "Bearer super-secret-key"
    assert "super-secret-key" not in str(excinfo.value)
    assert "500" in str(excinfo.value)


def test_extract_structured_validates_and_retries():
    good = _completion(json.dumps({"summary": "ok", "level": 60}))
    bad = _completion("here is your answer: not json at all")
    client = LLMClient(
        _settings_with_key(), transport=_transport([bad, good])
    )
    result = client.extract_structured(Answer, "extract it")
    assert result.summary == "ok"
    assert result.level == 60


def test_extract_structured_gives_up_after_retries():
    client = LLMClient(
        _settings_with_key(),
        transport=_transport([_completion("garbage"), _completion("more garbage")]),
    )
    with pytest.raises(LLMError):
        client.extract_structured(Answer, "extract it", retries=1)


def test_code_fence_stripping_and_image_part():
    assert _strip_code_fences("```json\n{\"a\": 1}\n```") == '{"a": 1}'
    part = image_content_part(b"\x89PNG fake")
    assert part["type"] == "image_url"
    assert part["image_url"]["url"].startswith("data:image/png;base64,")


def test_unconfigured_client_raises_clean_error():
    from game_companion.errors import LLMNotConfiguredError

    client = LLMClient(Settings(llm_base_url="", llm_model=""))
    with pytest.raises(LLMNotConfiguredError):
        client.complete([{"role": "user", "content": "hi"}])

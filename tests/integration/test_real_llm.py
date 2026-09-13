"""Opt-in integration test against the configured real LLM endpoint.

Skipped unless GAME_COMPANION_LLM_API_KEY is set. Never runs in CI / the
normal suite (no paid/external API calls by default).

    GAME_COMPANION_LLM_API_KEY=... .venv/bin/pytest tests/integration/test_real_llm.py -m real_llm
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("GAME_COMPANION_LLM_API_KEY"),
    reason="opt-in: set GAME_COMPANION_LLM_API_KEY to run against the real endpoint",
)


def test_real_endpoint_structured_extraction(settings):
    from pydantic import BaseModel

    from game_companion.core.llm.client import LLMClient

    class Reply(BaseModel):
        summary: str
        confidence: float

    client = LLMClient(settings)
    result = client.extract_structured(
        Reply,
        "Summarize in one short sentence what a 'gacha game companion' is and give "
        "a confidence between 0 and 1.",
    )
    assert result.summary
    assert 0.0 <= result.confidence <= 1.0

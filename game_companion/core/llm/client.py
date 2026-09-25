"""OpenAI-compatible LLM client.

Speaks plain chat-completions JSON over httpx (no vendor SDK), supports image
content, and offers ``extract_structured`` for schema-validated extraction.
The API key never appears in logs or exceptions raised to users.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

import httpx
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from game_companion.config import Settings
from game_companion.errors import LLMError, LLMNotConfiguredError

logger = logging.getLogger(__name__)


class LLMClientProtocol(Protocol):
    def complete(self, messages: list[dict], *, temperature: float = 0.4) -> str: ...


def image_content_part(image: str | Path | bytes) -> dict:
    """Build an OpenAI-style ``image_url`` content part from a path/bytes/data-URL."""
    if isinstance(image, (str, Path)) and str(image).startswith("data:"):
        data_url = str(image)
    else:
        if isinstance(image, (str, Path)):
            path = Path(image)
            mime = mimetypes.guess_type(path.name)[0] or "image/png"
            raw = path.read_bytes()
        else:
            raw = image
            mime = "image/png"
        data_url = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
    return {"type": "image_url", "image_url": {"url": data_url}}


_VISION_RE = re.compile(r"(?i)vlm|vision|multimodal|-vl|gpt-4o|claude|gemini|glimmer|omni|qvq|internvl")

# 1x1 transparent PNG — the smallest valid image, used for the live probe.
_PROBE_PNG = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c626001000000ffff03000006000557bfabd400000000"
        "49454e44ae426082"
    )
).decode()


class LLMClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self._base_url = settings.llm_base_url.rstrip("/")
        self._api_key = settings.llm_api_key_plain()
        self._model = settings.llm_model
        self._timeout = settings.llm_timeout_seconds
        self._vision_override = settings.llm_vision_model
        self._transport = transport  # test seam
        self._client: httpx.Client | None = None
        self._vision_probe: bool | None = None  # live-test result, per model

    @property
    def configured(self) -> bool:
        return bool(self._base_url and self._model)

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def vision_capable(self) -> bool:
        """Best-effort vision flag: manual override wins, else a live probe,
        else the model-id heuristic (see :meth:`probe_vision`)."""
        if self._vision_override is not None:
            return self._vision_override
        if self._vision_probe is not None:
            return self._vision_probe
        return bool(_VISION_RE.search(self._model or ""))

    def probe_vision(self) -> bool:
        """Actually ask the endpoint whether images work (one tiny request).

        Brokers with an "auto" model route to whichever backend fits the
        request, so the model id alone can't tell us — sending a 1x1 PNG and
        seeing whether the call succeeds is the only honest test. The result
        is cached for the life of this client (hot-swapped on settings
        changes). Returns False only when the endpoint clearly rejects the
        image; network/other errors raise LLMError as usual.
        """
        if self._vision_probe is not None:
            return self._vision_probe
        try:
            response = self._http().post(
                f"{self._base_url}/chat/completions",
                json={
                    "model": self._model,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Reply with the single word OK."},
                            {"type": "image_url", "image_url": {
                                "url": f"data:image/png;base64,{_PROBE_PNG}"
                            }},
                        ],
                    }],
                    "max_tokens": 5,
                },
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM request failed: {type(exc).__name__}") from exc
        if response.status_code in (400, 404, 413, 415, 422):
            # the endpoint refused a 1px image: it can't take screenshots
            self._vision_probe = False
            return False
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"LLM endpoint returned HTTP {exc.response.status_code}") from exc
        self._vision_probe = True
        return True

    def _http(self) -> httpx.Client:
        if self._client is None:
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.Client(timeout=self._timeout, headers=headers, transport=self._transport)
        return self._client

    def complete(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.4,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        if not self.configured:
            raise LLMNotConfiguredError()
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            response = self._http().post(f"{self._base_url}/chat/completions", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Never include request headers (auth) in the error text.
            raise LLMError(f"LLM endpoint returned HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM request failed: {type(exc).__name__}") from exc
        try:
            return response.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMError("LLM endpoint returned an unexpected response shape") from exc

    def chat_with_tools(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        temperature: float = 0.4,
    ) -> dict:
        """One chat-completions call that may return tool_calls.

        Returns the raw assistant message dict (role/content/tool_calls) so the
        agent loop can append it verbatim and execute any requested tools.
        """
        if not self.configured:
            raise LLMNotConfiguredError()
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
        try:
            response = self._http().post(f"{self._base_url}/chat/completions", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (400, 404, 422) and tools:
                raise LLMError(
                    f"LLM endpoint rejected the request (HTTP {status}). If your endpoint or "
                    "model does not support function calling, pick a tool-capable model — "
                    "chat needs it and will not degrade silently."
                ) from exc
            raise LLMError(f"LLM endpoint returned HTTP {status}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM request failed: {type(exc).__name__}") from exc
        try:
            message = response.json()["choices"][0]["message"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMError("LLM endpoint returned an unexpected response shape") from exc
        return {
            "role": "assistant",
            "content": message.get("content") or "",
            "tool_calls": message.get("tool_calls"),
        }

    def extract_structured(
        self,
        schema: type[BaseModel],
        instruction: str,
        *,
        images: Sequence[str | Path | bytes] = (),
        context: str = "",
        temperature: float = 0.0,
        retries: int = 1,
    ) -> BaseModel:
        """Ask the model for JSON conforming to ``schema``; validate + retry once."""
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        system = (
            "You extract structured data. Reply with ONLY a JSON object that validates "
            "against the given JSON schema. Use null for anything you cannot read "
            "confidently. NEVER guess values.\n\nJSON schema:\n" + schema_json
        )
        content: list[dict] = [{"type": "text", "text": instruction}]
        if context:
            content.append({"type": "text", "text": context})
        for image in images:
            content.append(image_content_part(image))
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ]
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            raw = self.complete(messages, temperature=temperature, json_mode=True)
            raw = _strip_code_fences(raw)
            try:
                data = json.loads(raw)
                return schema.model_validate(data)
            except (json.JSONDecodeError, PydanticValidationError) as exc:
                last_error = exc
                logger.warning("structured extraction attempt %d failed validation", attempt + 1)
                messages = messages[:2] + [
                    messages[1],
                    {"role": "assistant", "content": raw[:4000]},
                    {
                        "role": "user",
                        "content": (
                            "That JSON failed validation:\n"
                            f"{str(exc)[:2000]}\nReturn corrected JSON only."
                        ),
                    },
                ]
        raise LLMError(f"structured extraction failed validation: {last_error}")

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()

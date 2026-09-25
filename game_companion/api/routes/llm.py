"""LLM settings API: status, live model list, on-the-fly config changes.

`PUT /api/llm/config` writes .env (the same file the wizard/auto-update use),
then hot-swaps the running LLM client — model changes apply immediately
without a restart.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from game_companion.config import Settings, get_settings
from game_companion.core.appsettings import update_env
from game_companion.core.llm.client import LLMClient
from game_companion.errors import LLMError

router = APIRouter(prefix="/llm")


def _probe_client(settings: Settings, transport) -> LLMClient:
    return LLMClient(settings, transport=transport)


def _probe_models(settings: Settings, transport) -> list[str]:
    client = _probe_client(settings, transport)
    if not client.configured:
        raise LLMError("no endpoint configured — set the base URL first")
    try:
        import httpx

        response = client._http().get(f"{client.base_url}/models")
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise LLMError(f"endpoint returned HTTP {exc.response.status_code} for /models") from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"could not reach endpoint: {type(exc).__name__}") from exc
    models = []
    for row in payload.get("data", []):
        model_id = row.get("id") if isinstance(row, dict) else str(row)
        if model_id:
            models.append(model_id)
    return sorted(models)


@router.get("/status")
def llm_status(request: Request):
    settings: Settings = request.app.state.settings
    client: LLMClient = request.app.state.llm
    return {
        "configured": client.configured,
        "base_url": client.base_url,
        "model": client.model,
        "vision_capable": client.vision_capable,
        "vision_source": ("override" if settings.llm_vision_model is not None else "auto"),
        "timeout_seconds": settings.llm_timeout_seconds,
        "searxng_configured": bool(settings.searxng_base_url),
    }


class ModelsProbe(BaseModel):
    llm_base_url: str | None = None
    llm_api_key: str | None = None


@router.post("/models")
def llm_models(request: Request, payload: ModelsProbe | None = None):
    """Live model list. Pass base/key to test a NEW endpoint before saving.

    A POST with the key in the body, deliberately: a GET query parameter would
    land the key verbatim in serve.log via the access log. An empty body
    probes the currently stored endpoint.
    """
    payload = payload or ModelsProbe()
    settings: Settings = request.app.state.settings
    probe_settings = settings
    if payload.llm_base_url or payload.llm_api_key:
        from pydantic import SecretStr

        probe_settings = settings.model_copy(
            update={
                "llm_base_url": payload.llm_base_url or settings.llm_base_url,
                "llm_api_key": SecretStr(payload.llm_api_key) if payload.llm_api_key else settings.llm_api_key,
            }
        )
    transport = getattr(request.app.state, "llm_transport", None)
    models = _probe_models(probe_settings, transport)
    return {"models": models, "count": len(models)}


class LlmConfigUpdate(BaseModel):
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float | None = None
    # tri-state: None = leave as-is; "auto"/"yes"/"no" set the override
    vision_override: str | None = None
    searxng_base_url: str | None = None


def _apply_llm_config(app, changes: dict) -> dict:
    """Shared writer: .env merge + settings cache clear + hot client swap."""
    written = update_env(app.state.settings, changes)
    get_settings.cache_clear()
    fresh = Settings()
    old_client: LLMClient = app.state.llm
    old_client.close()
    app.state.llm = LLMClient(fresh, transport=getattr(app.state, "llm_transport", None))
    app.state.settings = fresh
    return written


@router.put("/config")
def llm_config(payload: LlmConfigUpdate, request: Request):
    changes: dict = {}
    if payload.llm_base_url is not None:
        changes["llm_base_url"] = payload.llm_base_url.strip()
    if payload.llm_api_key is not None:
        changes["llm_api_key"] = payload.llm_api_key.strip()
    if payload.llm_model is not None:
        changes["llm_model"] = payload.llm_model.strip()
    if payload.llm_timeout_seconds is not None:
        if payload.llm_timeout_seconds < 5 or payload.llm_timeout_seconds > 600:
            from game_companion.errors import ValidationError

            raise ValidationError("timeout must be between 5 and 600 seconds")
        changes["llm_timeout_seconds"] = payload.llm_timeout_seconds
    if payload.vision_override is not None:
        if payload.vision_override not in ("auto", "yes", "no"):
            from game_companion.errors import ValidationError

            raise ValidationError("vision_override must be auto|yes|no")
        changes["llm_vision_model"] = (
            "" if payload.vision_override == "auto"
            else ("true" if payload.vision_override == "yes" else "false")
        )
    if payload.searxng_base_url is not None:
        changes["searxng_base_url"] = payload.searxng_base_url.strip()

    if not changes:
        from game_companion.errors import ValidationError

        raise ValidationError("nothing to update")

    written = _apply_llm_config(request.app, changes)
    return {
        "saved": sorted(written),
        "applied_live": True,
        "status": llm_status(request),
    }

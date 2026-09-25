"""Domain errors mapped to HTTP status codes by the API layer."""

from __future__ import annotations


class DomainError(Exception):
    status_code = 400
    detail = "domain error"

    def __init__(self, detail: str | None = None) -> None:
        if detail:
            self.detail = detail
        super().__init__(self.detail)


class NotFoundError(DomainError):
    status_code = 404
    detail = "not found"


class ConflictError(DomainError):
    status_code = 409
    detail = "conflict"


class ValidationError(DomainError):
    status_code = 422
    detail = "validation error"


class AdapterError(DomainError):
    status_code = 400
    detail = "game adapter error"


class LLMNotConfiguredError(DomainError):
    status_code = 503
    detail = "LLM endpoint is not configured (set GAME_COMPANION_LLM_* variables)"


class LLMError(DomainError):
    status_code = 502
    detail = "LLM request failed"


class SearchNotConfiguredError(DomainError):
    status_code = 503
    detail = "no search provider answered (built-in DuckDuckGo + optional SearXNG)"

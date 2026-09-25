"""Application configuration.

All values come from environment variables prefixed with ``GAME_COMPANION_``
(optionally a local ``.env`` file). API keys are stored as ``SecretStr`` so they
never leak through repr/logging.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GAME_COMPANION_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # LLM (OpenAI-compatible endpoint)
    llm_base_url: str = "https://llm.tictac.one/v1"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "muse-glimmer-30b-vlm-128k"
    llm_timeout_seconds: float = 120.0
    # Vision capability: None = auto-detect from the model id; True/False =
    # manual override set in Settings (guards screenshot imports).
    llm_vision_model: bool | None = None

    # Local data
    data_dir: Path | None = None
    database_url: str | None = None

    # Local service binding — localhost only unless explicitly changed.
    # D2 threat model: the UI/API is unauthenticated; binding a non-loopback
    # host requires GAME_COMPANION_EXPOSE=1 as an explicit tripwire.
    host: str = "127.0.0.1"
    port: int = 8765
    expose: bool = False

    # Logging
    log_level: str = "INFO"
    log_json: bool = False

    # Research / search
    searxng_base_url: str | None = None

    # Background auto-refresh (codes daily, catalog weekly). Off in tests.
    auto_refresh: bool = True

    @property
    def resolved_data_dir(self) -> Path:
        if self.data_dir:
            return Path(self.data_dir).expanduser()
        return Path.home() / ".local" / "share" / "gacha-companion"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.resolved_data_dir / 'gacha_companion.db'}"

    @property
    def exports_dir(self) -> Path:
        return self.resolved_data_dir / "exports"

    @property
    def personas_dir(self) -> Path:
        return self.resolved_data_dir / "personas"

    def llm_api_key_plain(self) -> str:
        return self.llm_api_key.get_secret_value()

    def secret_values_for_redaction(self) -> list[str]:
        key = self.llm_api_key_plain()
        return [key] if key else []


@lru_cache
def get_settings() -> Settings:
    return Settings()

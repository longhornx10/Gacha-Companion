"""Runtime-updatable app settings: write .env atomically, preserving unknown lines.

The .env file stays the single source of truth for LLM/search config (same file
the wizard and auto-update use); the service hot-swaps its LLM client after a
write so changes apply without a restart.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from game_companion.errors import ValidationError

# Keys the service may manage (uppercase .env names). Unknown lines survive.
MANAGED_KEYS = {
    "llm_base_url": "GAME_COMPANION_LLM_BASE_URL",
    "llm_api_key": "GAME_COMPANION_LLM_API_KEY",
    "llm_model": "GAME_COMPANION_LLM_MODEL",
    "llm_timeout_seconds": "GAME_COMPANION_LLM_TIMEOUT_SECONDS",
    "llm_vision_model": "GAME_COMPANION_LLM_VISION_MODEL",
    "searxng_base_url": "GAME_COMPANION_SEARXNG_BASE_URL",
}

_LINE_RE = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$")


def env_path(settings) -> Path:
    # pydantic-settings reads env_file relative to the process CWD; match it.
    return Path.cwd() / ".env"


def format_env_value(key: str, value) -> str:
    if value is None:
        return ""
    text = str(value)
    if key == "llm_api_key" and text:
        # quote keys defensively; they can contain special characters
        return text if re.fullmatch(r"[A-Za-z0-9_\-\.]+", text) else "'" + text.replace("'", "") + "'"
    return text


def update_env(settings, changes: dict) -> dict:
    """Merge ``changes`` ({config_name: value}) into .env. Returns what was written.

    Unknown keys raise; empty string deletes a managed line back to default
    (the line is removed so pydantic falls back to its default).
    """
    unknown = set(changes) - set(MANAGED_KEYS)
    if unknown:
        raise ValidationError(f"unknown settings keys: {sorted(unknown)}")

    path = env_path(settings)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    wanted = {MANAGED_KEYS[k]: v for k, v in changes.items()}

    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        match = _LINE_RE.match(line.strip())
        name = match.group("name") if match else None
        if name in wanted:
            value = wanted[name]
            if value == "" or value is None:
                continue  # drop the line entirely -> default applies
            out.append(f"{name}={format_env_value(name, value)}")
            seen.add(name)
        else:
            out.append(line)
    for name, value in wanted.items():
        if name in seen or value == "" or value is None:
            continue
        out.append(f"{name}={format_env_value(name, value)}")

    # never leave the file world-readable when it may now hold the key
    tmp = path.with_suffix(".env.tmp")
    tmp.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
    os.replace(tmp, path)
    try:
        path.chmod(0o600)
    except OSError:  # pragma: no cover - filesystems without chmod
        pass

    # Hot-apply: env vars outrank the .env file in pydantic-settings, so the
    # live process env must reflect the change too (deletes restore defaults).
    for config_name, value in changes.items():
        env_name = MANAGED_KEYS[config_name]
        if value == "" or value is None:
            os.environ.pop(env_name, None)
        else:
            os.environ[env_name] = str(value)
    return dict(changes)

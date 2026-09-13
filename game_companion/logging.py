"""Structured logging with secret redaction.

The API key must never appear in logs; a filter scrubs configured secret values
from every record before emission.
"""

from __future__ import annotations

import json
import logging
import sys

from game_companion.config import Settings

_REDACTED = "***REDACTED***"


class SecretRedactingFilter(logging.Filter):
    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        self._secrets = [s for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        if self._secrets:
            try:
                message = record.getMessage()
            except Exception:
                return True
            redacted = message
            for secret in self._secrets:
                redacted = redacted.replace(secret, _REDACTED)
            if redacted != message:
                record.msg = redacted
                record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(settings: Settings) -> None:
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if settings.log_json else logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    ))
    handler.addFilter(SecretRedactingFilter(settings.secret_values_for_redaction()))
    root.addHandler(handler)

    if settings.log_level.upper() == "DEBUG":
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
    # Third-party noise
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

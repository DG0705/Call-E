"""Structured logging configuration."""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_context: ContextVar[str | None] = ContextVar(
    "request_id", default=None
)


class JSONFormatter(logging.Formatter):
    """Render log records as compact structured JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_context.get(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(*, level: str, logger_name: str = "call_e") -> logging.Logger:
    """Configure and return an idempotent structured logger."""
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)

    return logger

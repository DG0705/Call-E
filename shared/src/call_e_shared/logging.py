"""Structured logging configuration."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from call_e_shared.constants import DEFAULT_LOG_LEVEL
from call_e_shared.request_id import get_request_id


class JSONFormatter(logging.Formatter):
    """Render log records as compact structured JSON."""

    def __init__(self, *, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "service": self.service_name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(
    *, service_name: str, level: str = DEFAULT_LOG_LEVEL
) -> logging.Logger:
    """Configure and return an idempotent structured logger."""
    logger = logging.getLogger(f"call_e.{service_name}")
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter(service_name=service_name))
        logger.addHandler(handler)

    return logger

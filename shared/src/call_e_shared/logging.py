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
    # Set the root level so named event loggers (for example voice_service.*,
    # agent_service.*) that emit INFO lifecycle observability events inherit it
    # instead of falling back to the WARNING default.
    logging.getLogger().setLevel(level)
    logger = logging.getLogger(f"call_e.{service_name}")
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter(service_name=service_name))
        logger.addHandler(handler)

    # Namespaced event loggers (voice_service.*, agent_service.*, ...) emit
    # through `logger.info(...)` and propagate to the root logger, which has
    # no handler by default — without this, every structured lifecycle event
    # is silently dropped in production. Attach the JSON handler to root once.
    root_logger = logging.getLogger()
    if not any(
        isinstance(handler.formatter, JSONFormatter)
        for handler in root_logger.handlers
    ):
        root_handler = logging.StreamHandler()
        root_handler.setFormatter(JSONFormatter(service_name=service_name))
        root_logger.addHandler(root_handler)

    return logger

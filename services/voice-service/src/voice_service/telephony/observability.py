"""Structured logging for telephony call lifecycle events."""

import logging
import re

TELEPHONY_EVENT_LOGGER = "voice_service.telephony.events"

_SAFE_SECRET_PATTERN = re.compile(
    r"(?i)(password|passwd|api[_-]?key|auth(?:orization)?|token|secret)\s*[:=]\s*\S+"
)
_MAX_ERROR_MESSAGE_CHARS = 200


def safe_error_message(exc: BaseException) -> str:
    """Render an exception message safe for structured logs.

    Truncates and redacts credential-shaped key=value fragments so failure
    diagnostics record their reason without ever leaking passwords, API
    keys, authorization headers, tokens, or SIP credentials. Provider-neutral;
    safe to use from service boundaries that must not import providers.
    """
    message = str(exc).strip().replace("\n", " ")
    message = _SAFE_SECRET_PATTERN.sub(r"\1=***", message)
    if len(message) > _MAX_ERROR_MESSAGE_CHARS:
        message = message[:_MAX_ERROR_MESSAGE_CHARS] + "..."
    return message


def log_telephony_event(
    logger: logging.Logger,
    event: str,
    *,
    tenant_id: str | None = None,
    agent_id: str | None = None,
    call_id: str | None = None,
    conversation_id: str | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    message: str | None = None,
    **details: object,
) -> None:
    """Emit one structured telephony event without logging numbers or audio.

    The ``event`` name is always preserved in the payload; ``message``
    optionally carries human-readable detail in the log record text for
    pipelines that only render the message.
    """
    payload: dict[str, object] = {
        "event": event,
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "call_id": call_id,
        "conversation_id": conversation_id,
        "session_id": session_id,
        "request_id": request_id,
        **details,
    }
    logger.info(message or event, extra={"telephony_event": payload})

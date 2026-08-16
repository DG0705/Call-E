"""Structured logging for telephony call lifecycle events."""

import logging

TELEPHONY_EVENT_LOGGER = "voice_service.telephony.events"


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
    **details: object,
) -> None:
    """Emit one structured telephony event without logging numbers or audio."""
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
    logger.info(event, extra={"telephony_event": payload})

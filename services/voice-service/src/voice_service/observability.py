"""Structured logging for voice session lifecycle events."""

import logging

VOICE_EVENT_LOGGER = "voice_service.events"


def log_voice_event(
    logger: logging.Logger,
    event: str,
    *,
    tenant_id: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    conversation_id: str | None = None,
    request_id: str | None = None,
    **details: object,
) -> None:
    """Emit one structured event without logging audio or transcripts."""
    payload: dict[str, object] = {
        "event": event,
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "session_id": session_id,
        "conversation_id": conversation_id,
        "request_id": request_id,
        **details,
    }
    logger.info(event, extra={"voice_event": payload})

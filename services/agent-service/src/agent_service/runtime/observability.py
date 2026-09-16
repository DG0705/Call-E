"""Structured logging for agent runtime lifecycle events."""

import logging

AGENT_EVENT_LOGGER = "agent_service.runtime.events"


def log_agent_event(
    logger: logging.Logger,
    event: str,
    *,
    tenant_id: str | None = None,
    agent_id: str | None = None,
    conversation_id: str | None = None,
    **details: object,
) -> None:
    """Emit one structured agent event without logging secrets or tool payloads."""
    payload: dict[str, object] = {
        "event": event,
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "conversation_id": conversation_id,
        **details,
    }
    logger.info(event, extra={"agent_event": payload})

"""Normalized telephony lifecycle events."""

import logging
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from call_e_shared.events import event_name

CALL_CREATED = event_name(domain="call", action="created")
CALL_RINGING = event_name(domain="call", action="ringing")
CALL_ANSWERED = event_name(domain="call", action="answered")
CALL_STARTED = event_name(domain="call", action="started")
CALL_ENDED = event_name(domain="call", action="ended")
CALL_FAILED = event_name(domain="call", action="failed")

TELEPHONY_EVENT_LOGGER = "voice_service.telephony.events"


class TelephonyEvent(BaseModel):
    """Versioned, normalized event for one call lifecycle transition."""

    name: str
    call_id: str
    tenant_id: str
    agent_id: str
    conversation_id: str | None = None
    session_id: str | None = None
    request_id: str | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class EventPublisher(Protocol):
    """Boundary for emitting normalized lifecycle events."""

    async def publish(self, event: TelephonyEvent) -> None: ...


class LoggingEventPublisher:
    """Publish events to structured logs.

    RabbitMQ is the intended asynchronous transport; the logging publisher is
    the safe, dependency-free default for local development.
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(TELEPHONY_EVENT_LOGGER)

    async def publish(self, event: TelephonyEvent) -> None:
        self._logger.info(
            event.name, extra={"telephony_event": event.model_dump(mode="json")}
        )

"""ARI event parsing for the Call-E Stasis application.

Asterisk delivers call lifecycle events (``StasisStart``, ``StasisEnd``,
``ChannelHangupRequest``, ``ChannelDestroyed``, ...) as JSON objects over the
ARI WebSocket event stream. This module owns that Asterisk-specific wire
format and normalizes the events the live-call runner cares about. It never
performs I/O and never logs credentials.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _as_dict(payload: object) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


@dataclass(frozen=True)
class AriChannelSnapshot:
    """The channel fields the runner needs from an ARI event."""

    id: str
    name: str = ""
    state: str = ""
    caller_number: str = ""
    caller_name: str = ""
    dialplan_context: str = ""
    dialplan_exten: str = ""

    @staticmethod
    def from_payload(payload: object) -> "AriChannelSnapshot | None":
        """Build a snapshot, or return None when no usable channel is present."""
        data = _as_dict(payload)
        channel_id = data.get("id")
        if not isinstance(channel_id, str) or not channel_id:
            return None
        caller = _as_dict(data.get("caller"))
        dialplan = _as_dict(data.get("dialplan"))

        def _text(value: object) -> str:
            return value if isinstance(value, str) else ""

        return AriChannelSnapshot(
            id=channel_id,
            name=_text(data.get("name")),
            state=_text(data.get("state")),
            caller_number=_text(caller.get("number")),
            caller_name=_text(caller.get("name")),
            dialplan_context=_text(dialplan.get("context")),
            dialplan_exten=_text(dialplan.get("exten")),
        )


@dataclass(frozen=True)
class AriEvent:
    """One normalized ARI event."""

    type: str
    application: str = ""
    timestamp: str = ""
    channel: AriChannelSnapshot | None = None
    args: tuple[str, ...] = field(default_factory=tuple)

    @property
    def channel_id(self) -> str | None:
        """Return the affected channel id, if the event carries a channel."""
        return self.channel.id if self.channel is not None else None

    @property
    def destination(self) -> str:
        """Return the dialed extension: dialplan exten first, then Stasis args."""
        if self.channel is not None and self.channel.dialplan_exten:
            return self.channel.dialplan_exten
        for arg in self.args:
            if arg:
                return arg
        return ""


def parse_ari_event(payload: object) -> AriEvent | None:
    """Parse one raw ARI WebSocket message.

    Returns ``None`` for malformed messages so the stream can log and skip
    them without dropping the connection.
    """
    data = _as_dict(payload)
    event_type = data.get("type")
    if not isinstance(event_type, str) or not event_type:
        return None
    application = data.get("application")
    timestamp = data.get("timestamp")
    raw_args = data.get("args")
    args = tuple(
        arg for arg in raw_args if isinstance(arg, str)
    ) if isinstance(raw_args, list) else ()
    return AriEvent(
        type=event_type,
        application=application if isinstance(application, str) else "",
        timestamp=timestamp if isinstance(timestamp, str) else "",
        channel=AriChannelSnapshot.from_payload(data.get("channel")),
        args=args,
    )

"""Asterisk-specific telephony adapter package."""

from voice_service.telephony.asterisk.adapter import AsteriskAdapter
from voice_service.telephony.asterisk.media import encode_ulaw
from voice_service.telephony.asterisk.transport import (
    AsteriskTransport,
    AsteriskTransportError,
    HttpAsteriskTransport,
)

__all__ = [
    "AsteriskAdapter",
    "AsteriskTransport",
    "AsteriskTransportError",
    "HttpAsteriskTransport",
    "encode_ulaw",
]

"""Asterisk-specific telephony adapter package."""

from voice_service.telephony.asterisk.adapter import AsteriskAdapter
from voice_service.telephony.asterisk.ari_client import AriEventStream, AriEventStreamError
from voice_service.telephony.asterisk.ari_events import AriEvent, parse_ari_event
from voice_service.telephony.asterisk.live_call import AsteriskLiveCallRunner
from voice_service.telephony.asterisk.media import encode_ulaw
from voice_service.telephony.asterisk.rtp_egress import RtpEgressSender, RtpPacketizer
from voice_service.telephony.asterisk.rtp_ingress import RtpMediaIngress
from voice_service.telephony.asterisk.transport import (
    AsteriskTransport,
    AsteriskTransportError,
    HttpAsteriskTransport,
)

__all__ = [
    "AriEvent",
    "AriEventStream",
    "AriEventStreamError",
    "AsteriskAdapter",
    "AsteriskLiveCallRunner",
    "AsteriskTransport",
    "AsteriskTransportError",
    "HttpAsteriskTransport",
    "RtpEgressSender",
    "RtpMediaIngress",
    "RtpPacketizer",
    "encode_ulaw",
    "parse_ari_event",
]

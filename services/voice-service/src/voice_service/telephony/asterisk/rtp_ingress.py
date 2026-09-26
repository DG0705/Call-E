"""RTP ingress for Asterisk inbound media.

Asterisk sends caller audio as G.711 mu-law RTP datagrams (from the phone leg
via an ARI external-media channel). This module owns that Asterisk-specific
transport detail: it parses RTP, decodes mu-law to the voice engine's internal
PCM representation, and queues decoded frames per ARI channel.

The ``AsteriskAdapter`` drains the queue through the neutral ``receive_audio``
boundary, so ``VoiceSessionManager`` keeps receiving normalized ``AudioChunk``
objects and never sees RTP, sockets, or SSRCs.
"""

import asyncio
import struct
from collections import deque
from dataclasses import dataclass, field

from voice_service.audio import AudioChunk
from voice_service.telephony.asterisk.media import decode_ulaw

_RTP_VERSION = 2
_RTP_HEADER_LEN = 12
_PCMU_PAYLOAD_TYPE = 0

_RTP_FRAME_SAMPLES = 160


@dataclass
class RtpMediaIngress:
    """Queue decoded inbound RTP frames per ARI channel."""

    _frames: dict[str, deque[AudioChunk]] = field(default_factory=dict)
    _listeners: dict[str, asyncio.DatagramTransport] = field(default_factory=dict)
    _remote_addrs: dict[str, tuple[str, int]] = field(default_factory=dict)

    def ingest(self, channel_id: str, datagram: bytes) -> AudioChunk | None:
        """Parse one RTP datagram and queue its decoded PCM frame.

        Returns the decoded chunk, or ``None`` when the datagram is not a
        usable mu-law voice frame (wrong version, payload type, or truncated).
        """
        payload = _rtp_mulaw_payload(datagram)
        if payload is None:
            return None
        chunk = decode_ulaw(
            payload, metadata={"rtp_channel_id": channel_id}
        )
        self._frames.setdefault(channel_id, deque()).append(chunk)
        return chunk

    def receive(self, channel_id: str) -> AudioChunk | None:
        """Return the oldest queued PCM frame for a channel, if any."""
        frames = self._frames.get(channel_id)
        if not frames:
            return None
        return frames.popleft()

    def pending(self, channel_id: str) -> int:
        """Return how many decoded frames are queued for a channel."""
        return len(self._frames.get(channel_id, ()))

    def release(self, channel_id: str) -> None:
        """Drop queued frames and close the listener for a finished call."""
        self._frames.pop(channel_id, None)
        self._remote_addrs.pop(channel_id, None)
        listener = self._listeners.pop(channel_id, None)
        if listener is not None:
            listener.close()

    def note_remote_addr(self, channel_id: str, addr: object) -> None:
        """Record the UDP source of inbound RTP for symmetric egress."""
        if (
            isinstance(addr, tuple)
            and len(addr) >= 2
            and isinstance(addr[0], str)
            and isinstance(addr[1], int)
        ):
            self._remote_addrs[channel_id] = (addr[0], addr[1])

    def remote_addr(self, channel_id: str) -> tuple[str, int] | None:
        """Return the learned Asterisk RTP source address, if any."""
        return self._remote_addrs.get(channel_id)

    async def bind(self, channel_id: str, *, host: str, port: int) -> None:
        """Listen for RTP datagrams from Asterisk for one call channel.

        Each call binds its own UDP port so inbound frames route to the call
        without SSRC bookkeeping; pass ``f"{host}:{port}"`` as the
        ``external_host`` when creating the matching ARI external-media
        channel.
        """
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _RtpDatagramProtocol(self, channel_id),
            local_addr=(host, port),
        )
        previous = self._listeners.pop(channel_id, None)
        if previous is not None:
            previous.close()
        self._listeners[channel_id] = transport


def _rtp_mulaw_payload(datagram: bytes) -> bytes | None:
    """Extract the mu-law payload from an RTP datagram, if it carries voice."""
    if len(datagram) < _RTP_HEADER_LEN:
        return None
    first, second = datagram[0], datagram[1]
    if (first >> 6) != _RTP_VERSION:
        return None
    if (second & 0x7F) != _PCMU_PAYLOAD_TYPE:
        return None
    header_len = _RTP_HEADER_LEN + (first & 0x0F) * 4
    if len(datagram) <= header_len:
        return None
    return datagram[header_len:]


def build_rtp_datagram(
    payload: bytes,
    *,
    sequence: int = 0,
    timestamp: int = 0,
    ssrc: int = 0,
) -> bytes:
    """Build a minimal mu-law RTP datagram (tests and local loopback)."""
    header = struct.pack(
        ">BBHII",
        0x80,
        _PCMU_PAYLOAD_TYPE,
        sequence & 0xFFFF,
        timestamp & 0xFFFFFFFF,
        ssrc & 0xFFFFFFFF,
    )
    return header + payload


class _RtpDatagramProtocol(asyncio.DatagramProtocol):
    """Forward received UDP datagrams into the ingress queue."""

    def __init__(self, ingress: RtpMediaIngress, channel_id: str) -> None:
        self._ingress = ingress
        self._channel_id = channel_id

    def datagram_received(self, data: bytes, addr: object) -> None:
        self._ingress.note_remote_addr(self._channel_id, addr)
        self._ingress.ingest(self._channel_id, data)

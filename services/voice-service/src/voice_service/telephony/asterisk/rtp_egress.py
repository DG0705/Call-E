"""Outbound RTP for Asterisk external-media playback.

ElevenLabs produces internal PCM (8 kHz, mono, 16-bit little-endian). This
module owns the Asterisk-specific playout detail: it encodes PCM to G.711
mu-law, packetizes 20 ms frames (160 bytes) into RTP datagrams with correct
payload type/sequence/timestamp behavior, and sends them over UDP to the
Asterisk external-media address learned from inbound RTP.

The ``AsteriskAdapter`` calls this boundary from ``send_audio`` when a call
carries RTP egress state, so ``TelephonyService`` and ``VoiceSessionManager``
keep working with normalized ``AudioChunk`` objects.
"""

from __future__ import annotations

import asyncio
import random
import struct
from dataclasses import dataclass, field

from voice_service.audio import AudioChunk
from voice_service.telephony.asterisk.media import encode_ulaw

_RTP_VERSION = 2
_PCMU_PAYLOAD_TYPE = 0
_FRAME_BYTES = 160
_TIMESTAMP_STEP = 160


@dataclass
class RtpPacketizer:
    """Packetize PCM audio into mu-law RTP datagrams for one call."""

    ssrc: int
    sequence: int = 0
    timestamp: int = 0

    def packetize(self, chunk: AudioChunk) -> list[bytes]:
        """Encode one PCM chunk into 20 ms RTP datagrams."""
        ulaw = encode_ulaw(chunk)
        datagrams: list[bytes] = []
        for offset in range(0, len(ulaw), _FRAME_BYTES):
            frame = ulaw[offset : offset + _FRAME_BYTES]
            if len(frame) < _FRAME_BYTES:
                frame = frame + b"\xff" * (_FRAME_BYTES - len(frame))
            header = struct.pack(
                ">BBHII",
                0x80,
                _PCMU_PAYLOAD_TYPE,
                self.sequence & 0xFFFF,
                self.timestamp & 0xFFFFFFFF,
                self.ssrc & 0xFFFFFFFF,
            )
            datagrams.append(header + frame)
            self.sequence += 1
            self.timestamp += _TIMESTAMP_STEP
        return datagrams


class _SilentDatagramProtocol(asyncio.DatagramProtocol):
    """UDP endpoint sink; egress only sends, never receives."""


@dataclass
class RtpEgressSender:
    """Send packetized RTP to Asterisk over one shared UDP socket."""

    _transport: asyncio.DatagramTransport | None = None
    _packetizers: dict[str, RtpPacketizer] = field(default_factory=dict)

    async def ensure_started(self) -> None:
        """Open the shared UDP socket (ephemeral local port)."""
        if self._transport is not None:
            return
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            _SilentDatagramProtocol, local_addr=("0.0.0.0", 0)
        )
        self._transport = transport

    def register(
        self, channel_id: str, *, ssrc: int | None = None
    ) -> RtpPacketizer:
        """Create (or reuse) per-call packetizer state. Idempotent."""
        packetizer = self._packetizers.get(channel_id)
        if packetizer is None:
            packetizer = RtpPacketizer(
                ssrc=ssrc if ssrc is not None else random.getrandbits(32)
            )
            self._packetizers[channel_id] = packetizer
        return packetizer

    async def send(
        self, channel_id: str, remote: tuple[str, int], chunk: AudioChunk
    ) -> int:
        """Packetize one PCM chunk and send every datagram. Returns count."""
        await self.ensure_started()
        assert self._transport is not None
        packetizer = self.register(channel_id)
        datagrams = packetizer.packetize(chunk)
        for datagram in datagrams:
            self._transport.sendto(datagram, remote)
        return len(datagrams)

    def pending_packets(self, channel_id: str) -> RtpPacketizer | None:
        """Return per-call packetizer state, if registered."""
        return self._packetizers.get(channel_id)

    def release(self, channel_id: str) -> None:
        """Drop per-call packetizer state for a finished call."""
        self._packetizers.pop(channel_id, None)

    def close(self) -> None:
        """Close the shared UDP socket."""
        transport, self._transport = self._transport, None
        if transport is not None:
            transport.close()

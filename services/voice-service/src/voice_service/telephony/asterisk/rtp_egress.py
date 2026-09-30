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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from voice_service.audio import AudioChunk
from voice_service.telephony.asterisk.media import encode_ulaw

_RTP_VERSION = 2
_PCMU_PAYLOAD_TYPE = 0
_FRAME_BYTES = 160
_TIMESTAMP_STEP = 160
# Real-time cadence of one 160-byte mu-law frame: Asterisk silently discards
# back-to-back bursts, so each datagram targets an absolute 20 ms deadline.
_FRAME_SECONDS = 0.020


class RtpEgressAborted(Exception):
    """Raised when playout is aborted mid-stream (caller barge-in)."""

#: Monotonic clock returning seconds (defaults to the event-loop clock so
#: ``asyncio.sleep`` delays align with it). Injectable for deterministic tests.
Clock = Callable[[], float]
#: Async sleep used between paced datagrams. Injectable for tests.
Sleeper = Callable[[float], Awaitable[None]]


def _loop_clock() -> float:
    return asyncio.get_running_loop().time()


async def _loop_sleep(delay: float) -> None:
    await asyncio.sleep(delay)


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
    _clock: Clock | None = None
    _sleep: Sleeper | None = None
    _stream_deadlines: dict[str, float] = field(default_factory=dict)
    _last_sent: dict[str, float] = field(default_factory=dict)

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
        self, channel_id: str, remote: tuple[str, int], chunk: AudioChunk,
        abort: asyncio.Event | None = None,
    ) -> int:
        """Packetize one PCM chunk and send datagrams at 20 ms cadence.

        Returns the datagram count. Each datagram targets an absolute
        monotonic deadline (``start + index * 20 ms``) so transmission
        follows real-time RTP cadence without accumulating drift; only the
        remaining time before each deadline is slept, and overdue deadlines
        send immediately. Packetization, headers, destination, and the shared
        socket are unchanged. When ``abort`` is set, playout stops at the
        next frame boundary with :class:`RtpEgressAborted`.
        """
        await self.ensure_started()
        assert self._transport is not None
        packetizer = self.register(channel_id)
        datagrams = packetizer.packetize(chunk)
        clock = self._clock or _loop_clock
        sleep = self._sleep or _loop_sleep
        start = clock()
        for index, datagram in enumerate(datagrams):
            if abort is not None and abort.is_set():
                raise RtpEgressAborted(channel_id)
            delay = start + index * _FRAME_SECONDS - clock()
            if delay > 0:
                await sleep(delay)
            self._transport.sendto(datagram, remote)
            self._last_sent[channel_id] = clock()
        return len(datagrams)

    async def send_frame(
        self, channel_id: str, remote: tuple[str, int], frame: AudioChunk,
        abort: asyncio.Event | None = None,
    ) -> int:
        """Packetize one 20 ms PCM frame and send its datagram on cadence.

        Returns 1 after the datagram is sent. Each call targets the channel's
        standing 20 ms deadline (advanced per frame from stream start), so
        frames arriving faster than real time are paced out — never
        firehosed — while overdue deadlines send immediately to catch up.
        Packetization, headers, destination, and the shared socket match
        :meth:`send`. When ``abort`` is set, raises :class:`RtpEgressAborted`
        before sending.
        """
        if abort is not None and abort.is_set():
            raise RtpEgressAborted(channel_id)
        await self.ensure_started()
        assert self._transport is not None
        packetizer = self.register(channel_id)
        datagrams = packetizer.packetize(frame)
        clock = self._clock or _loop_clock
        sleep = self._sleep or _loop_sleep
        now = clock()
        deadline = self._stream_deadlines.get(channel_id, now)
        if deadline < now:
            deadline = now
        else:
            delay = deadline - now
            if delay > 0:
                await sleep(delay)
        self._stream_deadlines[channel_id] = deadline + _FRAME_SECONDS
        if abort is not None and abort.is_set():
            raise RtpEgressAborted(channel_id)
        for datagram in datagrams:
            self._transport.sendto(datagram, remote)
            clock = self._clock or _loop_clock
            self._last_sent[channel_id] = clock()
        return len(datagrams)

    def is_playing(self, channel_id: str) -> bool:
        """Report whether RTP left for a channel within the barge window.

        The single source of truth for "audio is currently audible": the
        runner gates barge-in interrupts on this, so speech never cancels a
        reply that has not started (or has already finished) playing.
        """
        clock = self._clock or _loop_clock
        return clock() - self._last_sent.get(channel_id, 0.0) < 0.5

    def pending_packets(self, channel_id: str) -> RtpPacketizer | None:
        """Return per-call packetizer state, if registered."""
        return self._packetizers.get(channel_id)

    def release(self, channel_id: str) -> None:
        """Drop per-call packetizer state for a finished call."""
        self._packetizers.pop(channel_id, None)
        self._stream_deadlines.pop(channel_id, None)
        self._last_sent.pop(channel_id, None)

    def close(self) -> None:
        """Close the shared UDP socket."""
        transport, self._transport = self._transport, None
        if transport is not None:
            transport.close()

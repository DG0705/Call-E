"""Provider-neutral telephony provider boundary.

Implementations translate phone/SIP behavior into normalized :class:`TelephonyCall`
state. Business logic must never depend on a specific telephony vendor.
"""

import asyncio
from typing import Protocol

from voice_service.audio import AudioChunk
from voice_service.telephony.models import TelephonyCall


class TelephonyProviderError(Exception):
    """Base error for provider-level telephony failures."""


class AudioOutputInterrupted(Exception):
    """Caller speech cut off outbound audio playout (barge-in).

    Not a failure: partial audio already heard stands, and the turn ends
    early so the caller's new utterance is handled next.
    """


class TelephonyTransferUnavailableError(TelephonyProviderError):
    """Raised when human transfer/escalation is not yet implemented."""


class TelephonyProvider(Protocol):
    """Interface implemented by replaceable telephony providers."""

    provider_name: str

    async def start_call(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        conversation_id: str,
        destination_number: str,
        caller_number: str | None = None,
        request_id: str | None = None,
    ) -> TelephonyCall:
        """Originate an outbound call and return its ringing state."""
        ...

    async def accept_call(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        conversation_id: str,
        caller_number: str,
        destination_number: str,
        request_id: str | None = None,
    ) -> TelephonyCall:
        """Register an inbound call received by the provider."""
        ...

    async def answer_call(
        self, call: TelephonyCall, *, request_id: str | None = None
    ) -> TelephonyCall:
        """Answer a ringing call and return its active state."""
        ...

    async def receive_audio(
        self, call: TelephonyCall, *, request_id: str | None = None
    ) -> AudioChunk | None:
        """Return the next incoming audio chunk, or None when none is available."""
        ...

    async def send_audio(
        self,
        call: TelephonyCall,
        audio: AudioChunk,
        *,
        request_id: str | None = None,
        abort: asyncio.Event | None = None,
    ) -> None:
        """Send synthesized audio out toward the phone."""
        ...

    async def send_audio_frame(
        self,
        call: TelephonyCall,
        frame: AudioChunk,
        *,
        request_id: str | None = None,
        abort: asyncio.Event | None = None,
    ) -> int:
        """Stream one 20 ms PCM frame toward the phone; return datagrams sent.

        Provider-neutral incremental counterpart to :meth:`send_audio` for
        streaming TTS. Returns 0 when the call has no bound streaming egress.
        Raises :class:`AudioOutputInterrupted` when ``abort`` is set.
        """
        ...

    async def hangup(
        self, call: TelephonyCall, *, request_id: str | None = None
    ) -> TelephonyCall:
        """Hang up the call and return its ended state."""
        ...

    async def transfer(
        self,
        call: TelephonyCall,
        destination: str,
        *,
        request_id: str | None = None,
    ) -> TelephonyCall:
        """Placeholder for human transfer/escalation."""
        ...

    def is_playing(self, call: TelephonyCall) -> bool:
        """Report whether phone audio is currently leaving for this call.

        The barge-in gate consults this before interrupting: only speech that
        overlaps actual RTP output may cancel a reply.
        """
        return False

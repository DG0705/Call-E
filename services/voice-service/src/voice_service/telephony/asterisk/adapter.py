"""Asterisk adapter implementing the provider-neutral telephony boundary.

The adapter owns all Asterisk-specific terminology (SIP endpoints, ARI
channels, codecs). AgentRuntime and VoiceSessionManager never see it.
"""

import uuid
from datetime import UTC, datetime

from voice_service.audio import AudioChunk
from voice_service.telephony.asterisk.media import encode_ulaw
from voice_service.telephony.asterisk.transport import (
    AsteriskTransport,
    HttpAsteriskTransport,
)
from voice_service.telephony.models import TelephonyCall
from voice_service.telephony.provider import (
    TelephonyProviderError,
    TelephonyTransferUnavailableError,
)

OUTBOUND_CONTEXT = "from-internal"


class AsteriskAdapter:
    """Translate Asterisk lifecycle/media onto normalized TelephonyCall state."""

    provider_name = "asterisk"

    def __init__(
        self,
        *,
        base_url: str,
        username: str | None = None,
        password: str | None = None,
        transport: AsteriskTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._transport = transport or HttpAsteriskTransport(
            base_url=base_url, username=username, password=password
        )
        self._channels: dict[str, str] = {}

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
        try:
            channel_id = await self._transport.originate(
                endpoint=f"PJSIP/{destination_number}",
                context=OUTBOUND_CONTEXT,
                extension=destination_number,
                caller_id=caller_number,
            )
        except Exception as exc:
            raise TelephonyProviderError(
                "Asterisk could not originate the outbound call."
            ) from exc
        now = datetime.now(UTC)
        call = TelephonyCall(
            call_id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            caller_number=caller_number,
            destination_number=destination_number,
            direction="outbound",
            status="ringing",
            provider=self.provider_name,
            created_at=now,
            updated_at=now,
            metadata={"channel_id": channel_id},
        )
        self._channels[call.call_id] = channel_id
        return call

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
        try:
            channel_id = await self._transport.accept_inbound(
                caller_number=caller_number, destination_number=destination_number
            )
        except Exception as exc:
            raise TelephonyProviderError(
                "Asterisk could not accept the inbound call."
            ) from exc
        now = datetime.now(UTC)
        call = TelephonyCall(
            call_id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            caller_number=caller_number,
            destination_number=destination_number,
            direction="inbound",
            status="ringing",
            provider=self.provider_name,
            created_at=now,
            updated_at=now,
            metadata={"channel_id": channel_id},
        )
        self._channels[call.call_id] = channel_id
        return call

    async def answer_call(
        self, call: TelephonyCall, *, request_id: str | None = None
    ) -> TelephonyCall:
        channel_id = self._channel_for(call)
        try:
            await self._transport.answer(channel_id)
        except Exception as exc:
            raise TelephonyProviderError("Asterisk could not answer the call.") from exc
        call.status = "active"
        call.updated_at = datetime.now(UTC)
        return call

    async def receive_audio(
        self, call: TelephonyCall, *, request_id: str | None = None
    ) -> AudioChunk | None:
        """No RTP media streaming is implemented at this boundary yet."""
        return None

    async def send_audio(
        self,
        call: TelephonyCall,
        audio: AudioChunk,
        *,
        request_id: str | None = None,
    ) -> None:
        channel_id = self._channel_for(call)
        media = encode_ulaw(audio)
        try:
            await self._transport.play_media(channel_id, media)
        except Exception as exc:
            raise TelephonyProviderError("Asterisk could not play response audio.") from exc

    async def hangup(
        self, call: TelephonyCall, *, request_id: str | None = None
    ) -> TelephonyCall:
        channel_id = self._channel_for(call)
        try:
            await self._transport.hangup(channel_id)
        except Exception as exc:
            raise TelephonyProviderError("Asterisk could not hang up the call.") from exc
        now = datetime.now(UTC)
        call.status = "ended"
        call.updated_at = now
        call.ended_at = now
        return call

    async def transfer(
        self,
        call: TelephonyCall,
        destination: str,
        *,
        request_id: str | None = None,
    ) -> TelephonyCall:
        raise TelephonyTransferUnavailableError(
            "Human transfer is not implemented for the Asterisk adapter."
        )

    def _channel_for(self, call: TelephonyCall) -> str:
        channel_id = call.metadata.get("channel_id") or self._channels.get(call.call_id)
        if not channel_id:
            raise TelephonyProviderError(
                "Call has no associated Asterisk channel."
            )
        return str(channel_id)

    async def close(self) -> None:
        """Release transport resources during application shutdown."""
        close_transport = getattr(self._transport, "close", None)
        if close_transport is not None:
            await close_transport()

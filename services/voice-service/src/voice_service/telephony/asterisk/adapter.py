"""Asterisk adapter implementing the provider-neutral telephony boundary.

The adapter owns all Asterisk-specific terminology (SIP endpoints, ARI
channels, codecs). AgentRuntime and VoiceSessionManager never see it.
"""

import uuid
from datetime import UTC, datetime

from voice_service.audio import AudioChunk
from voice_service.telephony.asterisk.media import encode_ulaw
from voice_service.telephony.asterisk.rtp_ingress import RtpMediaIngress
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
EXTERNAL_MEDIA_APP = "call-e"


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
        media_ingress: RtpMediaIngress | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._transport = transport or HttpAsteriskTransport(
            base_url=base_url, username=username, password=password
        )
        self._channels: dict[str, str] = {}
        self._media_ingress = media_ingress

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
        """Return the oldest decoded inbound PCM frame for the call, if any.

        Frames arrive from Asterisk as mu-law RTP and are decoded to the
        internal PCM representation by :class:`RtpMediaIngress` at this
        boundary. Returns ``None`` when no media path is bound or no frame
        has arrived yet.
        """
        if self._media_ingress is None:
            return None
        channel_id = self._channel_for(call)
        return self._media_ingress.receive(channel_id)

    async def bind_media_ingress(
        self, call: TelephonyCall, *, host: str, port: int
    ) -> str:
        """Listen for this call's inbound RTP and return the external host.

        Each call binds its own UDP port; pass the returned ``"host:port"``
        to :meth:`start_external_media` so Asterisk streams caller audio to
        this listener. Decoded PCM frames are then drained via
        :meth:`receive_audio`.
        """
        channel_id = self._channel_for(call)
        if self._media_ingress is None:
            self._media_ingress = RtpMediaIngress()
        await self._media_ingress.bind(channel_id, host=host, port=port)
        return f"{host}:{port}"

    async def start_external_media(
        self, call: TelephonyCall, *, external_host: str
    ) -> str:
        """Create the ARI external-media channel streaming to our listener."""
        try:
            external_channel_id = await self._transport.create_external_media(
                app=EXTERNAL_MEDIA_APP,
                external_host=external_host,
                media_format="ulaw",
            )
        except Exception as exc:
            raise TelephonyProviderError(
                "Asterisk could not start external media for the call."
            ) from exc
        call.metadata["external_channel_id"] = external_channel_id
        return external_channel_id

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
        if self._media_ingress is not None:
            self._media_ingress.release(channel_id)
            self._channels.pop(call.call_id, None)
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

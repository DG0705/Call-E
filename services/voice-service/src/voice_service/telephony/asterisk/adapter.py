"""Asterisk adapter implementing the provider-neutral telephony boundary.

The adapter owns all Asterisk-specific terminology (SIP endpoints, ARI
channels, codecs). AgentRuntime and VoiceSessionManager never see it.
"""

import logging
import uuid
from datetime import UTC, datetime

from voice_service.audio import AudioChunk
from voice_service.telephony.asterisk.media import encode_ulaw
from voice_service.telephony.asterisk.rtp_egress import RtpEgressSender
from voice_service.telephony.asterisk.rtp_ingress import RtpMediaIngress
from voice_service.telephony.asterisk.transport import (
    AsteriskTransport,
    HttpAsteriskTransport,
)
from voice_service.telephony.models import TelephonyCall
from voice_service.telephony.observability import (
    TELEPHONY_EVENT_LOGGER,
    log_telephony_event,
)
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
        media_egress: RtpEgressSender | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._transport = transport or HttpAsteriskTransport(
            base_url=base_url, username=username, password=password
        )
        self._channels: dict[str, str] = {}
        self._media_ingress = media_ingress
        self._media_egress = media_egress
        # Egress destinations keyed by ARI channel id, owned by the adapter.
        # Call metadata is re-read from the store on every turn (fresh objects
        # under MongoDB), so routing state kept only on the call object would
        # be lost; see bind_egress.
        self._egress_remotes: dict[str, tuple[str, int]] = {}
        self._logger = logger or logging.getLogger(TELEPHONY_EVENT_LOGGER)

    @property
    def transport(self) -> AsteriskTransport:
        """The Asterisk communication surface this adapter drives."""
        return self._transport

    @property
    def media_ingress(self) -> RtpMediaIngress:
        """The inbound RTP queue shared with the live-call runner."""
        if self._media_ingress is None:
            self._media_ingress = RtpMediaIngress()
        return self._media_ingress

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
        channel_id = self._channel_for(call)
        return self.media_ingress.receive(channel_id)

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
        await self.media_ingress.bind(channel_id, host=host, port=port)
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
        """Send synthesized audio toward the phone.

        Live calls bound with :meth:`bind_egress` stream packetized RTP to
        the Asterisk external-media address; otherwise audio falls back to
        the ARI play-media foundation.
        """
        channel_id = self._channel_for(call)
        remote = self._egress_remotes.get(channel_id)
        if remote is None:
            remote = self._adopt_egress_marker(call, channel_id)
        if remote is not None and self._media_egress is not None:
            try:
                sent = await self._media_egress.send(channel_id, remote, audio)
            except Exception as exc:
                raise TelephonyProviderError(
                    "Asterisk could not stream response audio."
                ) from exc
            log_telephony_event(
                self._logger,
                "egress_audio_sent",
                tenant_id=call.tenant_id,
                agent_id=call.agent_id,
                call_id=call.call_id,
                conversation_id=call.conversation_id,
                request_id=request_id,
                egress_host=remote[0],
                egress_port=remote[1],
                rtp_packets=sent,
                audio_format=audio.format,
                audio_sample_rate=audio.sample_rate,
                audio_channels=audio.channels,
                audio_bytes=len(audio.data),
                message=(
                    f"egress_audio_sent egress_host={remote[0]} "
                    f"egress_port={remote[1]} rtp_packets={sent} "
                    f"audio_format={audio.format} "
                    f"audio_sample_rate={audio.sample_rate} "
                    f"audio_channels={audio.channels} "
                    f"audio_bytes={len(audio.data)}"
                ),
            )
            return
        media = encode_ulaw(audio)
        try:
            await self._transport.play_media(channel_id, media)
        except Exception as exc:
            raise TelephonyProviderError("Asterisk could not play response audio.") from exc

    def _adopt_egress_marker(
        self, call: TelephonyCall, channel_id: str
    ) -> tuple[str, int] | None:
        """Adopt a metadata egress marker into adapter-owned routing state.

        Accepts ``"host:port"`` markers written by older flows so they keep
        working; malformed markers are ignored and fall back to play-media.
        """
        marker = call.metadata.get("rtp_egress_remote")
        if not marker:
            return None
        host, _, port = str(marker).rpartition(":")
        try:
            remote = (host, int(port))
        except ValueError:
            return None
        if not host:
            return None
        self._egress_remotes[channel_id] = remote
        return remote

    def bind_egress(self, call: TelephonyCall, *, remote_host: str, remote_port: int) -> str:
        """Bind RTP playout for a call to Asterisk's media address.

        The remote address is learned from the first inbound RTP datagram
        (symmetric RTP). The destination is recorded adapter-side keyed by
        ARI channel id, because call objects are re-read from the store on
        every turn and in-memory metadata mutations do not survive a
        MongoDB round trip. The ``"host:port"`` marker is still stored on
        the call metadata for diagnostics. Returns the marker.
        """
        if self._media_egress is None:
            self._media_egress = RtpEgressSender()
        remote = f"{remote_host}:{remote_port}"
        call.metadata["rtp_egress_remote"] = remote
        self._egress_remotes[self._channel_for(call)] = (remote_host, remote_port)
        log_telephony_event(
            self._logger,
            "egress_remote_learned",
            tenant_id=call.tenant_id,
            agent_id=call.agent_id,
            call_id=call.call_id,
            conversation_id=call.conversation_id,
            egress_host=remote_host,
            egress_port=remote_port,
            message=(
                "egress_remote_learned "
                f"egress_host={remote_host} egress_port={remote_port}"
            ),
        )
        return remote

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
        self.media_ingress.release(channel_id)
        self._channels.pop(call.call_id, None)
        self._egress_remotes.pop(channel_id, None)
        if self._media_egress is not None:
            self._media_egress.release(channel_id)
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
        """Release transport and egress resources during application shutdown."""
        if self._media_egress is not None:
            self._media_egress.close()
        close_transport = getattr(self._transport, "close", None)
        if close_transport is not None:
            await close_transport()

"""Tests for telephony providers and the Asterisk adapter boundary."""

import asyncio

import pytest

from voice_service.audio import AudioChunk
from voice_service.telephony.asterisk.adapter import AsteriskAdapter
from voice_service.telephony.asterisk.media import encode_ulaw
from voice_service.telephony.asterisk.transport import (
    AsteriskTransportError,
    HttpAsteriskTransport,
)
from voice_service.telephony.config import (
    TelephonySettings,
    load_telephony_settings,
)
from voice_service.telephony.factory import (
    TelephonyProviderConfigurationError,
    TelephonyProviderFactory,
)
from voice_service.telephony.mock_provider import MockTelephonyProvider
from voice_service.telephony.provider import (
    TelephonyProviderError,
    TelephonyTransferUnavailableError,
)


class FakeAsteriskTransport:
    """Deterministic transport recording every Asterisk operation."""

    def __init__(self) -> None:
        self.originate_calls: list[dict[str, str | None]] = []
        self.accept_calls: list[dict[str, str]] = []
        self.answer_calls: list[str] = []
        self.hangup_calls: list[str] = []
        self.play_calls: list[dict[str, object]] = []
        self.external_media_calls: list[dict[str, str]] = []

    async def originate(
        self,
        *,
        endpoint: str,
        context: str,
        extension: str,
        caller_id: str | None = None,
    ) -> str:
        self.originate_calls.append(
            {
                "endpoint": endpoint,
                "context": context,
                "extension": extension,
                "caller_id": caller_id,
            }
        )
        return "channel-1"

    async def accept_inbound(
        self, *, caller_number: str, destination_number: str
    ) -> str:
        self.accept_calls.append(
            {"caller_number": caller_number, "destination_number": destination_number}
        )
        return "channel-2"

    async def answer(self, channel_id: str) -> None:
        self.answer_calls.append(channel_id)

    async def hangup(self, channel_id: str) -> None:
        self.hangup_calls.append(channel_id)

    async def play_media(self, channel_id: str, media: bytes) -> None:
        self.play_calls.append({"channel_id": channel_id, "media": media})

    async def create_external_media(
        self, *, app: str, external_host: str, media_format: str = "ulaw"
    ) -> str:
        self.external_media_calls.append(
            {"app": app, "external_host": external_host, "media_format": media_format}
        )
        return "external-channel-1"


def build_adapter(
    *,
    transport: FakeAsteriskTransport | None = None,
    media_ingress: object | None = None,
) -> AsteriskAdapter:
    return AsteriskAdapter(
        base_url="http://asterisk:8088",
        username="user",
        password="secret",
        transport=transport or FakeAsteriskTransport(),
        media_ingress=media_ingress,  # type: ignore[arg-type]
    )


def test_mock_provider_runs_full_lifecycle() -> None:
    provider = MockTelephonyProvider()

    call = asyncio.run(
        provider.start_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            destination_number="+15550002",
            caller_number="+15550001",
        )
    )
    assert call.status == "ringing"
    assert call.direction == "outbound"

    call = asyncio.run(provider.answer_call(call))
    assert call.status == "active"

    provider.queue_audio(call.call_id, AudioChunk(data=b"hello", format="pcm"))
    received = asyncio.run(provider.receive_audio(call))
    assert received is not None
    assert received.data == b"hello"
    assert asyncio.run(provider.receive_audio(call)) is None

    audio = AudioChunk(data=b"reply", format="pcm")
    asyncio.run(provider.send_audio(call, audio))
    assert provider.sent_audio(call.call_id) == [audio]

    call = asyncio.run(provider.hangup(call))
    assert call.status == "ended"
    assert call.ended_at is not None


def test_mock_provider_accepts_inbound_calls() -> None:
    provider = MockTelephonyProvider()

    call = asyncio.run(
        provider.accept_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            caller_number="+15550001",
            destination_number="+15550002",
        )
    )

    assert call.direction == "inbound"
    assert call.status == "ringing"
    assert call.caller_number == "+15550001"


def test_mock_provider_transfer_is_unsupported() -> None:
    provider = MockTelephonyProvider()
    call = asyncio.run(
        provider.start_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            destination_number="+15550002",
        )
    )

    with pytest.raises(TelephonyTransferUnavailableError):
        asyncio.run(provider.transfer(call, destination="+15550003"))


def test_asterisk_adapter_originates_outbound_call() -> None:
    transport = FakeAsteriskTransport()
    adapter = build_adapter(transport=transport)

    call = asyncio.run(
        adapter.start_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            destination_number="+15550002",
            caller_number="+15550001",
        )
    )

    assert call.direction == "outbound"
    assert call.status == "ringing"
    assert call.metadata["channel_id"] == "channel-1"
    assert transport.originate_calls == [
        {
            "endpoint": "PJSIP/+15550002",
            "context": "from-internal",
            "extension": "+15550002",
            "caller_id": "+15550001",
        }
    ]


def test_asterisk_adapter_accepts_inbound_call() -> None:
    transport = FakeAsteriskTransport()
    adapter = build_adapter(transport=transport)

    call = asyncio.run(
        adapter.accept_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            caller_number="+15550001",
            destination_number="+15550002",
        )
    )

    assert call.direction == "inbound"
    assert call.status == "ringing"
    assert call.metadata["channel_id"] == "channel-2"
    assert transport.accept_calls == [
        {"caller_number": "+15550001", "destination_number": "+15550002"}
    ]


def test_asterisk_adapter_answers_and_hangs_up() -> None:
    transport = FakeAsteriskTransport()
    adapter = build_adapter(transport=transport)
    call = asyncio.run(
        adapter.start_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            destination_number="+15550002",
        )
    )

    call = asyncio.run(adapter.answer_call(call))
    assert call.status == "active"
    assert transport.answer_calls == ["channel-1"]

    call = asyncio.run(adapter.hangup(call))
    assert call.status == "ended"
    assert call.ended_at is not None
    assert transport.hangup_calls == ["channel-1"]


def test_asterisk_adapter_sends_encoded_audio_to_channel() -> None:
    transport = FakeAsteriskTransport()
    adapter = build_adapter(transport=transport)
    call = asyncio.run(
        adapter.start_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            destination_number="+15550002",
        )
    )

    asyncio.run(adapter.send_audio(call, AudioChunk(data=b"ab", format="pcm")))

    assert transport.play_calls == [
        {"channel_id": "channel-1", "media": encode_ulaw(AudioChunk(data=b"ab", format="pcm"))}
    ]


def test_asterisk_adapter_receive_audio_returns_none_without_media_path() -> None:
    adapter = build_adapter()
    call = asyncio.run(
        adapter.start_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            destination_number="+15550002",
        )
    )

    assert asyncio.run(adapter.receive_audio(call)) is None


def test_asterisk_adapter_transfer_is_unsupported() -> None:
    adapter = build_adapter()
    call = asyncio.run(
        adapter.start_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            destination_number="+15550002",
        )
    )

    with pytest.raises(TelephonyTransferUnavailableError):
        asyncio.run(adapter.transfer(call, destination="+15550003"))


def test_asterisk_adapter_wraps_transport_failures() -> None:
    class FailingTransport(FakeAsteriskTransport):
        async def originate(self, **kwargs: object) -> str:
            raise RuntimeError("ari unavailable")

    adapter = build_adapter(transport=FailingTransport())

    with pytest.raises(TelephonyProviderError):
        asyncio.run(
            adapter.start_call(
                tenant_id="tenant-1",
                agent_id="agent-1",
                conversation_id="conversation-1",
                destination_number="+15550002",
            )
        )


def test_http_transport_accept_inbound_needs_event_stream() -> None:
    import httpx

    transport = HttpAsteriskTransport(
        base_url="http://asterisk:8088",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler=lambda _: httpx.Response(404))),
    )

    with pytest.raises(AsteriskTransportError):
        asyncio.run(
            transport.accept_inbound(caller_number="+15550001", destination_number="+15550002")
        )


def test_ulaw_encoding_anchors() -> None:
    assert encode_ulaw(AudioChunk(data=b"\x00\x00", format="pcm")) == b"\xff"
    assert encode_ulaw(AudioChunk(data=b"\x08\x00", format="pcm")) == b"\xfe"
    assert encode_ulaw(AudioChunk(data=b"\xf8\xff", format="pcm")) == b"\x7e"


def test_ulaw_encoding_rejects_non_pcm() -> None:
    with pytest.raises(ValueError):
        encode_ulaw(AudioChunk(data=b"x", format="ulaw"))
    with pytest.raises(ValueError):
        encode_ulaw(AudioChunk.model_construct(data=b"x", format="pcm", sample_width=1))


def test_factory_returns_mock_by_default() -> None:
    assert isinstance(
        TelephonyProviderFactory.create(TelephonySettings(provider="mock")),
        MockTelephonyProvider,
    )


def test_factory_requires_asterisk_url_for_asterisk() -> None:
    with pytest.raises(TelephonyProviderConfigurationError):
        TelephonyProviderFactory.create(TelephonySettings(provider="asterisk"))
    adapter = TelephonyProviderFactory.create(
        TelephonySettings(provider="asterisk", asterisk_url="http://asterisk:8088")
    )
    assert isinstance(adapter, AsteriskAdapter)


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(TelephonyProviderConfigurationError):
        TelephonyProviderFactory.create(TelephonySettings(provider="twilio"))


def test_settings_default_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEPHONY_PROVIDER", raising=False)
    monkeypatch.delenv("ASTERISK_URL", raising=False)
    monkeypatch.delenv("ASTERISK_USERNAME", raising=False)
    monkeypatch.delenv("ASTERISK_PASSWORD", raising=False)

    settings = load_telephony_settings()

    assert settings.provider == "mock"
    assert settings.asterisk_url is None
    assert settings.asterisk_username is None
    assert settings.asterisk_password is None


def test_rtp_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    from voice_service.telephony.config import load_rtp_settings

    for name in (
        "VOICE_RTP_HOST",
        "VOICE_RTP_PORT_START",
        "VOICE_RTP_PORT_COUNT",
        "VOICE_RTP_FIRST_PACKET_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = load_rtp_settings()

    assert settings.host == "voice-service"
    assert settings.port_start == 20000
    assert settings.port_count == 100
    assert settings.first_packet_timeout_seconds == 10.0


def test_live_call_settings_follow_provider_and_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from voice_service.telephony.config import load_live_call_settings

    monkeypatch.delenv("ASTERISK_LIVE_CALLS", raising=False)
    assert load_live_call_settings(telephony_provider="asterisk").enabled is True
    assert load_live_call_settings(telephony_provider="mock").enabled is False
    assert load_live_call_settings(telephony_provider="asterisk").ari_app == "call-e"

    monkeypatch.setenv("ASTERISK_LIVE_CALLS", "false")
    assert load_live_call_settings(telephony_provider="asterisk").enabled is False
    monkeypatch.setenv("ASTERISK_LIVE_CALLS", "true")
    assert load_live_call_settings(telephony_provider="mock").enabled is True


def test_rtp_packetizer_sequences_and_timestamps() -> None:
    import struct

    from voice_service.telephony.asterisk.rtp_egress import RtpPacketizer

    packetizer = RtpPacketizer(ssrc=1234, sequence=100, timestamp=800)
    chunk = AudioChunk(data=b"\x00\x00" * 320, format="pcm")

    datagrams = packetizer.packetize(chunk)

    assert len(datagrams) == 2
    first = struct.unpack(">BBHII", datagrams[0][:12])
    second = struct.unpack(">BBHII", datagrams[1][:12])
    assert first[0] >> 6 == 2
    assert (first[1] & 0x7F) == 0
    assert (first[2], first[3], first[4]) == (100, 800, 1234)
    assert (second[2], second[3], second[4]) == (101, 960, 1234)
    assert len(datagrams[0][12:]) == 160


def test_rtp_packetizer_roundtrips_through_decode() -> None:
    from voice_service.audio import decode_ulaw
    from voice_service.telephony.asterisk.rtp_egress import RtpPacketizer

    samples = bytes([i % 256 for i in range(320)])
    packetizer = RtpPacketizer(ssrc=7)

    datagrams = packetizer.packetize(AudioChunk(data=samples, format="pcm"))

    assert len(datagrams) == 1
    assert decode_ulaw(datagrams[0][12:]).format == "pcm"


def test_rtp_egress_sender_delivers_udp_datagrams() -> None:
    import socket

    from voice_service.telephony.asterisk.rtp_egress import RtpEgressSender

    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(5)
    port = receiver.getsockname()[1]

    async def main() -> int:
        sender = RtpEgressSender()
        try:
            return await sender.send(
                "chan-1",
                ("127.0.0.1", port),
                AudioChunk(data=b"\x00\x00" * 160, format="pcm"),
            )
        finally:
            sender.close()

    try:
        sent = asyncio.run(main())
        packet, _ = receiver.recvfrom(4096)
    finally:
        receiver.close()

    assert sent == 1
    assert len(packet) == 12 + 160
    assert packet[0] >> 6 == 2
    assert (packet[1] & 0x7F) == 0


def test_rtp_egress_release_drops_channel_state() -> None:
    from voice_service.telephony.asterisk.rtp_egress import RtpEgressSender

    sender = RtpEgressSender()
    sender.register("chan-1", ssrc=9)

    assert sender.pending_packets("chan-1") is not None
    sender.release("chan-1")

    assert sender.pending_packets("chan-1") is None


def test_adapter_send_audio_uses_egress_when_bound() -> None:
    import socket

    transport = FakeAsteriskTransport()
    adapter = build_adapter(transport=transport)
    call = asyncio.run(
        adapter.start_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            destination_number="+15550002",
        )
    )
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(5)
    port = receiver.getsockname()[1]

    async def main() -> None:
        try:
            adapter.bind_egress(call, remote_host="127.0.0.1", remote_port=port)
            await adapter.send_audio(
                call, AudioChunk(data=b"\x00\x00" * 160, format="pcm")
            )
        finally:
            await adapter.close()

    try:
        asyncio.run(main())
        packet, _ = receiver.recvfrom(4096)
    finally:
        receiver.close()

    assert transport.play_calls == []
    assert len(packet) == 12 + 160


def test_ulaw_decode_roundtrip_is_stable_for_every_code() -> None:
    from voice_service.audio import decode_ulaw

    for code in range(256):
        decoded = decode_ulaw(bytes([code]))
        assert decoded.format == "pcm"
        assert decoded.sample_rate == 8000
        if code == 0x7F:
            # Mu-law negative zero decodes to digital silence, like 0xFF.
            assert decoded.data == b"\x00\x00"
            continue
        assert encode_ulaw(decoded) == bytes([code])


def test_ulaw_decode_rejects_empty_payload() -> None:
    from voice_service.audio import decode_ulaw

    with pytest.raises(ValueError):
        decode_ulaw(b"")


def test_rtp_ingress_queues_decoded_pcm_frames() -> None:
    from voice_service.telephony.asterisk.rtp_ingress import (
        RtpMediaIngress,
        build_rtp_datagram,
    )

    ingress = RtpMediaIngress()
    datagram = build_rtp_datagram(bytes([0xFF] * 160), sequence=1, timestamp=160)

    chunk = ingress.ingest("channel-1", datagram)

    assert chunk is not None
    assert chunk.format == "pcm"
    assert len(chunk.data) == 320
    assert ingress.pending("channel-1") == 1
    assert ingress.receive("channel-1") == chunk
    assert ingress.receive("channel-1") is None


def test_rtp_ingress_ignores_non_voice_datagrams() -> None:
    from voice_service.telephony.asterisk.rtp_ingress import (
        RtpMediaIngress,
        build_rtp_datagram,
    )

    ingress = RtpMediaIngress()

    assert ingress.ingest("channel-1", b"short") is None
    assert ingress.ingest("channel-1", b"\x00" * 20) is None
    alaw = bytearray(build_rtp_datagram(bytes([0xD5] * 160)))
    alaw[1] = 8
    assert ingress.ingest("channel-1", bytes(alaw)) is None
    assert ingress.pending("channel-1") == 0


def test_adapter_receive_audio_drains_decoded_inbound_pcm() -> None:
    from voice_service.telephony.asterisk.rtp_ingress import (
        RtpMediaIngress,
        build_rtp_datagram,
    )

    ingress = RtpMediaIngress()
    adapter = build_adapter(media_ingress=ingress)
    call = asyncio.run(
        adapter.start_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            destination_number="+15550002",
        )
    )
    ingress.ingest("channel-1", build_rtp_datagram(bytes([0xFF] * 160)))

    received = asyncio.run(adapter.receive_audio(call))

    assert received is not None
    assert received.format == "pcm"
    assert len(received.data) == 320
    assert asyncio.run(adapter.receive_audio(call)) is None


def test_adapter_start_external_media_records_channel() -> None:
    transport = FakeAsteriskTransport()
    adapter = build_adapter(transport=transport)
    call = asyncio.run(
        adapter.start_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            destination_number="+15550002",
        )
    )

    external_id = asyncio.run(
        adapter.start_external_media(call, external_host="voice-service:10000")
    )

    assert external_id == "external-channel-1"
    assert call.metadata["external_channel_id"] == "external-channel-1"
    assert transport.external_media_calls == [
        {
            "app": "call-e",
            "external_host": "voice-service:10000",
            "media_format": "ulaw",
        }
    ]


def test_adapter_hangup_releases_media_ingress() -> None:
    from voice_service.telephony.asterisk.rtp_ingress import (
        RtpMediaIngress,
        build_rtp_datagram,
    )

    ingress = RtpMediaIngress()
    adapter = build_adapter(media_ingress=ingress)
    call = asyncio.run(
        adapter.start_call(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            destination_number="+15550002",
        )
    )
    ingress.ingest("channel-1", build_rtp_datagram(bytes([0xFF] * 160)))

    asyncio.run(adapter.hangup(call))

    assert ingress.pending("channel-1") == 0


def test_http_transport_create_external_media_posts_ari() -> None:
    import httpx

    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"id": "ext-9"}, request=request)

    transport = HttpAsteriskTransport(
        base_url="http://asterisk:8088",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler=handler)),
    )

    channel_id = asyncio.run(
        transport.create_external_media(
            app="call-e", external_host="voice-service:10000"
        )
    )

    assert channel_id == "ext-9"
    assert str(seen["url"]).startswith(
        "http://asterisk:8088/ari/channels/externalMedia"
    )
    assert seen["params"] == {
        "app": "call-e",
        "externalHost": "voice-service:10000",
        "format": "ulaw",
    }


def test_http_transport_sends_basic_auth_when_configured() -> None:
    import base64

    import httpx

    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"id": "chan-7"}, request=request)

    transport = HttpAsteriskTransport(
        base_url="http://asterisk:8088",
        username="call-e-user",
        password="secret",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler=handler)),
    )

    channel_id = asyncio.run(
        transport.originate(
            endpoint="PJSIP/1000", context="from-internal", extension="1000"
        )
    )

    assert channel_id == "chan-7"
    assert seen["authorization"] == "Basic " + base64.b64encode(
        b"call-e-user:secret"
    ).decode()


def test_http_transport_sends_no_auth_header_without_credentials() -> None:
    import httpx

    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"id": "chan-7"}, request=request)

    transport = HttpAsteriskTransport(
        base_url="http://asterisk:8088",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler=handler)),
    )

    asyncio.run(
        transport.originate(
            endpoint="PJSIP/1000", context="from-internal", extension="1000"
        )
    )

    assert seen["authorization"] == ""


def test_http_transport_bridge_lifecycle() -> None:
    import httpx

    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url).split("?")[0]))
        if request.method == "POST" and request.url.path == "/ari/bridges":
            return httpx.Response(200, json={"id": "bridge-1"}, request=request)
        return httpx.Response(204, request=request)

    transport = HttpAsteriskTransport(
        base_url="http://asterisk:8088",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler=handler)),
    )

    bridge_id = asyncio.run(transport.create_bridge())
    asyncio.run(transport.add_channel_to_bridge(bridge_id, "chan-1"))
    asyncio.run(transport.add_channel_to_bridge(bridge_id, "chan-2"))
    asyncio.run(transport.destroy_bridge(bridge_id))

    assert bridge_id == "bridge-1"
    assert seen == [
        ("POST", "http://asterisk:8088/ari/bridges"),
        ("POST", "http://asterisk:8088/ari/bridges/bridge-1/addChannel"),
        ("POST", "http://asterisk:8088/ari/bridges/bridge-1/addChannel"),
        ("DELETE", "http://asterisk:8088/ari/bridges/bridge-1"),
    ]


def test_http_transport_accepts_pending_stasis_channel() -> None:
    transport = HttpAsteriskTransport(base_url="http://asterisk:8088")

    asyncio.run(
        transport.note_stasis_channel(
            "chan-live-1", caller_number="+15550001", destination_number="1000"
        )
    )
    channel_id = asyncio.run(
        transport.accept_inbound(
            caller_number="+15550001", destination_number="1000"
        )
    )

    assert channel_id == "chan-live-1"
    with pytest.raises(AsteriskTransportError):
        asyncio.run(
            transport.accept_inbound(
                caller_number="+15550001", destination_number="1000"
            )
        )

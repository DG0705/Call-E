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


def build_adapter(*, transport: FakeAsteriskTransport | None = None) -> AsteriskAdapter:
    return AsteriskAdapter(
        base_url="http://asterisk:8088",
        username="user",
        password="secret",
        transport=transport or FakeAsteriskTransport(),
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


def test_asterisk_adapter_receive_audio_is_unavailable_for_now() -> None:
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

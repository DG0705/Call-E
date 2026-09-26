"""Tests for the ARI live-call runner (fake ARI transport + real service stack).

These tests drive real orchestration code — the runner, TelephonyService,
AsteriskAdapter, RTP ingress/egress, and the utterance accumulator — with
fakes only at the external seams (ARI HTTP, voice engine, UDP network via
loopback). They do not claim a live phone call works; they prove the
vertical slice handles StasisStart, media setup, turns, and cleanup.
"""

import asyncio
import socket
import struct
from datetime import UTC, datetime

from voice_service.audio import AudioChunk
from voice_service.models import VoiceSession
from voice_service.session import VoiceTurnResult
from voice_service.telephony.asterisk.adapter import AsteriskAdapter
from voice_service.telephony.asterisk.ari_events import parse_ari_event
from voice_service.telephony.asterisk.live_call import AsteriskLiveCallRunner
from voice_service.telephony.asterisk.rtp_ingress import build_rtp_datagram
from voice_service.telephony.dev_routing import KaariDevRouter
from voice_service.telephony.events import EventPublisher, TelephonyEvent
from voice_service.telephony.models import TelephonyCall
from voice_service.telephony.service import TelephonyService
from voice_service.telephony.store import InMemoryCallStore
from voice_service.utterance import UtteranceConfig


def stasis_start(channel_id: str = "phone-1", exten: str = "1000") -> object:
    return parse_ari_event(
        {
            "type": "StasisStart",
            "application": "call-e",
            "channel": {
                "id": channel_id,
                "name": "PJSIP/dev-phone-00000001",
                "state": "Ring",
                "caller": {"number": "+15550001", "name": ""},
                "dialplan": {"context": "call-e-inbound", "exten": exten},
            },
            "args": [exten],
        }
    )


def hangup_event(event_type: str, channel_id: str) -> object:
    return parse_ari_event({"type": event_type, "channel": {"id": channel_id}})


class RecordingTransport:
    """Fake ARI transport recording every operation."""

    def __init__(self) -> None:
        self.pending: list[dict[str, str]] = []
        self.answered: list[str] = []
        self.hung_up: list[str] = []
        self.external_hosts: list[str] = []
        self.bridges: list[str] = ["bridge-1"]
        self.bridge_adds: list[tuple[str, str]] = []
        self.bridges_destroyed: list[str] = []
        self.fail_on: set[str] = set()

    async def note_stasis_channel(
        self, channel_id: str, *, caller_number: str, destination_number: str
    ) -> None:
        self.pending.append(
            {
                "channel_id": channel_id,
                "caller_number": caller_number,
                "destination_number": destination_number,
            }
        )

    async def accept_inbound(
        self, *, caller_number: str, destination_number: str
    ) -> str:
        for pending in self.pending:
            if (
                pending["caller_number"] == caller_number
                and pending["destination_number"] == destination_number
            ):
                self.pending.remove(pending)
                return pending["channel_id"]
        raise RuntimeError("no pending Stasis channel")

    async def answer(self, channel_id: str) -> None:
        self.answered.append(channel_id)

    async def hangup(self, channel_id: str) -> None:
        self.hung_up.append(channel_id)

    async def play_media(self, channel_id: str, media: bytes) -> None:
        raise AssertionError("live calls must use RTP egress, not play_media")

    async def create_external_media(
        self, *, app: str, external_host: str, media_format: str = "ulaw"
    ) -> str:
        self.external_hosts.append(external_host)
        return "external-1"

    async def create_bridge(self) -> str:
        return self.bridges[0]

    async def add_channel_to_bridge(self, bridge_id: str, channel_id: str) -> None:
        self.bridge_adds.append((bridge_id, channel_id))

    async def destroy_bridge(self, bridge_id: str) -> None:
        self.bridges_destroyed.append(bridge_id)


class FakeVoiceManager:
    """Minimal voice engine: sessions, greeting, and one scripted turn."""

    def __init__(self, greeting: AudioChunk | None = None) -> None:
        self.sessions: dict[str, VoiceSession] = {}
        self.processed: list[AudioChunk] = []
        self.ended: list[str] = []
        self.greeting = greeting

    async def create_session(self, **kwargs: object) -> VoiceSession:
        now = datetime.now(UTC)
        session = VoiceSession(
            session_id="session-1",
            tenant_id=str(kwargs["tenant_id"]),
            agent_id=str(kwargs["agent_id"]),
            conversation_id=str(kwargs["conversation_id"]),
            status="created",
            created_at=now,
            updated_at=now,
        )
        self.sessions[session.session_id] = session
        return session

    async def synthesize_greeting(self, **kwargs: object) -> AudioChunk | None:
        return self.greeting

    async def process_audio_input(self, **kwargs: object) -> VoiceTurnResult:
        audio = kwargs["audio"]
        assert isinstance(audio, AudioChunk)
        self.processed.append(audio)
        return VoiceTurnResult(
            session_id="session-1",
            tenant_id=str(kwargs["tenant_id"]),
            agent_id="kaari-sales-agent",
            conversation_id="conv",
            transcript="ten planters",
            response_text="Here are ten planters.",
            audio=AudioChunk(data=b"\x00\x00" * 160, format="pcm"),
            stt_provider="deepgram",
            runtime_provider="groq",
            runtime_model="model",
            tts_provider="elevenlabs",
            content_type="audio/pcm",
        )

    async def end_session(self, **kwargs: object) -> VoiceSession:
        self.ended.append(str(kwargs["session_id"]))
        return self.sessions[str(kwargs["session_id"])]


class RecordingPublisher:
    def __init__(self) -> None:
        self.published: list[TelephonyEvent] = []

    async def publish(self, event: TelephonyEvent) -> None:
        self.published.append(event)


def voice_frame(amplitude: int = 4000) -> bytes:
    """One 20 ms μ-law frame of loud audio, encoded from PCM properly."""
    from voice_service.audio import AudioChunk, encode_ulaw

    samples = [amplitude if i % 2 == 0 else -amplitude for i in range(160)]
    return encode_ulaw(
        AudioChunk(data=struct.pack(f"<{len(samples)}h", *samples), format="pcm")
    )


def silence_frame() -> bytes:
    """One 20 ms μ-law silence frame (0xFF decodes to digital zero)."""
    return bytes([0xFF] * 160)


class Harness:
    def __init__(
        self,
        *,
        greeting: AudioChunk | None = None,
        first_packet_timeout_seconds: float = 10.0,
    ) -> None:
        self.transport = RecordingTransport()
        self.adapter = AsteriskAdapter(
            base_url="http://asterisk:8088",
            transport=self.transport,  # type: ignore[arg-type]
        )
        self.voice = FakeVoiceManager(greeting=greeting)
        self.publisher = RecordingPublisher()
        self.telephony = TelephonyService(
            provider=self.adapter,  # type: ignore[arg-type]
            call_store=InMemoryCallStore(),
            voice_manager=self.voice,  # type: ignore[arg-type]
            event_publisher=self.publisher,  # type: ignore[arg-type]
        )
        self.runner = AsteriskLiveCallRunner(
            adapter=self.adapter,
            telephony_service=self.telephony,
            dev_router=KaariDevRouter("1000"),
            rtp_host="127.0.0.1",
            rtp_port_start=43000,
            rtp_port_count=10,
            first_packet_timeout_seconds=first_packet_timeout_seconds,
            utterance_config=UtteranceConfig(
                min_utterance_ms=100, end_silence_ms=200, max_utterance_ms=15000
            ),
            start_turn_tasks=False,
        )

    @property
    def ingress(self):  # type: ignore[no-untyped-def]
        return self.adapter.media_ingress


def test_runner_full_inbound_flow_with_turn_and_cleanup() -> None:
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(5)
    asterisk_port = receiver.getsockname()[1]
    harness = Harness(
        greeting=AudioChunk(data=b"\x00\x00" * 160, format="pcm")
    )

    async def main() -> TelephonyCall:
        # Asterisk's first RTP datagram arrives as soon as media is bridged.
        harness.ingress.note_remote_addr("phone-1", ("127.0.0.1", asterisk_port))
        await harness.runner.handle_event(stasis_start())
        state = harness.runner._states["phone-1"]  # type: ignore[attr-defined]
        # Caller speaks: ten voice frames, then trailing silence.
        for _ in range(10):
            harness.ingress.ingest("phone-1", build_rtp_datagram(voice_frame()))
        for _ in range(10):
            harness.ingress.ingest("phone-1", build_rtp_datagram(silence_frame()))
        ran = await harness.runner._run_one_turn(state)  # type: ignore[attr-defined]
        assert ran is True
        # Caller hangs up.
        await harness.runner.handle_event(hangup_event("StasisEnd", "phone-1"))
        return state.call

    try:
        call = asyncio.run(main())
        greeting_packet, _ = receiver.recvfrom(4096)
    finally:
        receiver.close()

    assert call.tenant_id == "kaari-planters"
    assert call.agent_id == "kaari-sales-agent"
    assert call.status == "ended"
    # Greeting RTP reached the (loopback) phone leg.
    assert len(greeting_packet) == 12 + 160
    assert greeting_packet[0] >> 6 == 2
    assert (greeting_packet[1] & 0x7F) == 0
    # One accumulated utterance drove exactly one voice turn.
    assert len(harness.voice.processed) == 1
    assert len(harness.voice.processed[0].data) == 20 * 320
    assert harness.voice.processed[0].format == "pcm"
    # Media path: external channel created, both legs bridged.
    assert harness.transport.external_hosts == ["127.0.0.1:43000"]
    assert ("bridge-1", "phone-1") in harness.transport.bridge_adds
    assert ("bridge-1", "external-1") in harness.transport.bridge_adds
    assert harness.transport.answered == ["phone-1"]
    # Cleanup: record hung up, bridge destroyed, state dropped.
    assert harness.transport.bridges_destroyed == ["bridge-1"]
    assert "external-1" in harness.transport.hung_up
    assert harness.runner._states == {}  # type: ignore[attr-defined]
    assert harness.ingress.pending("phone-1") == 0
    names = [event.name for event in harness.publisher.published]
    assert "call.created.v1" in names
    assert "call.ended.v1" in names


def test_runner_rejects_unmapped_extension() -> None:
    harness = Harness()

    async def main() -> None:
        await harness.runner.handle_event(stasis_start(exten="9999"))

    asyncio.run(main())

    assert harness.transport.hung_up == ["phone-1"]
    assert harness.voice.sessions == {}
    assert harness.runner._states == {}  # type: ignore[attr-defined]


def test_runner_ignores_duplicate_stasis_start() -> None:
    harness = Harness(first_packet_timeout_seconds=0.05)

    async def main() -> None:
        # No inbound RTP: setup fails after the media timeout...
        await harness.runner.handle_event(stasis_start())
        # ...so a redelivered StasisStart finds no tracked call to duplicate.
        await harness.runner.handle_event(stasis_start())

    asyncio.run(main())

    assert harness.transport.hung_up.count("phone-1") == 2
    assert harness.runner._states == {}  # type: ignore[attr-defined]


def test_runner_ignores_external_channel_stasis_start() -> None:
    harness = Harness()

    async def main() -> None:
        harness.runner._external_channels["external-9"] = "phone-1"  # type: ignore[attr-defined]
        await harness.runner.handle_event(stasis_start(channel_id="external-9"))

    asyncio.run(main())

    assert harness.voice.sessions == {}
    assert harness.runner._states == {}  # type: ignore[attr-defined]


def test_runner_hangup_unknown_channel_is_noop() -> None:
    harness = Harness()

    async def main() -> None:
        await harness.runner.handle_event(hangup_event("StasisEnd", "ghost-1"))

    asyncio.run(main())

    assert harness.transport.hung_up == []
    assert harness.transport.bridges_destroyed == []


def test_runner_first_packet_timeout_cleans_up() -> None:
    harness = Harness(first_packet_timeout_seconds=0.05)

    async def main() -> None:
        await harness.runner.handle_event(stasis_start())

    asyncio.run(main())

    # Call record hung up, bridge destroyed, no lingering state.
    assert harness.runner._states == {}  # type: ignore[attr-defined]
    assert harness.transport.bridges_destroyed == ["bridge-1"]
    assert harness.ingress.pending("phone-1") == 0


def test_runner_run_one_turn_without_frames_returns_false() -> None:
    harness = Harness()

    async def main() -> bool:
        harness.ingress.note_remote_addr("phone-1", ("127.0.0.1", 9999))
        await harness.runner.handle_event(stasis_start())
        state = harness.runner._states["phone-1"]  # type: ignore[attr-defined]
        try:
            return await harness.runner._run_one_turn(state)  # type: ignore[attr-defined]
        finally:
            await harness.runner.handle_event(hangup_event("StasisEnd", "phone-1"))

    assert asyncio.run(main()) is False
    assert harness.voice.processed == []


def test_app_builds_live_runner_only_for_asterisk() -> None:
    from voice_service.agent_runtime import AgentConfiguration, RuntimeResult
    from voice_service.app import create_voice_app
    from voice_service.session_store import InMemoryVoiceSessionStore
    from voice_service.stt import MockSTTProvider
    from voice_service.telephony.asterisk.live_call import AsteriskLiveCallRunner
    from voice_service.telephony.config import TelephonySettings
    from voice_service.telephony.mock_provider import MockTelephonyProvider
    from voice_service.telephony.store import InMemoryCallStore
    from voice_service.tts import MockTTSProvider

    class _Runtime:
        async def get_agent(self, **kwargs: object) -> AgentConfiguration:
            return AgentConfiguration(
                id="a", tenant_id="t", language="en", voice_id=None
            )

        async def respond(self, **kwargs: object) -> RuntimeResult:
            return RuntimeResult(
                text="hi", provider_name="mock", model_name="m",
                conversation_id="c", agent_id="a",
            )

    asterisk_app = create_voice_app(
        session_store=InMemoryVoiceSessionStore(),
        call_store=InMemoryCallStore(),
        agent_runtime=_Runtime(),  # type: ignore[arg-type]
        stt_provider=MockSTTProvider(),
        tts_provider=MockTTSProvider(),
        telephony_provider=AsteriskAdapter(
            base_url="http://asterisk:8088", transport=RecordingTransport()  # type: ignore[arg-type]
        ),
        telephony_settings=TelephonySettings(
            provider="asterisk", asterisk_url="http://asterisk:8088"
        ),
    )
    mock_app = create_voice_app(
        session_store=InMemoryVoiceSessionStore(),
        call_store=InMemoryCallStore(),
        agent_runtime=_Runtime(),  # type: ignore[arg-type]
        stt_provider=MockSTTProvider(),
        tts_provider=MockTTSProvider(),
        telephony_provider=MockTelephonyProvider(),
    )

    assert isinstance(asterisk_app.state.live_call_runner, AsteriskLiveCallRunner)
    assert mock_app.state.live_call_runner is None

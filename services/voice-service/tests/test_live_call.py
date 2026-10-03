"""Tests for the ARI live-call runner (fake ARI transport + real service stack).

These tests drive real orchestration code — the runner, TelephonyService,
AsteriskAdapter, RTP ingress/egress, and the utterance accumulator — with
fakes only at the external seams (ARI HTTP, voice engine, UDP network via
loopback). They do not claim a live phone call works; they prove the
vertical slice handles StasisStart, media setup, turns, and cleanup.
"""

import asyncio
import logging
import socket
import struct
from datetime import UTC, datetime

import pytest

from voice_service.audio import AudioChunk
from voice_service.models import VoiceSession
from voice_service.session import VoiceTurnResult
from voice_service.telephony.asterisk.adapter import AsteriskAdapter
from voice_service.telephony.asterisk.ari_events import parse_ari_event
from voice_service.telephony.asterisk.live_call import AsteriskLiveCallRunner
from voice_service.telephony.asterisk.rtp_ingress import build_rtp_datagram
from voice_service.telephony.dev_routing import DevInboundRouter
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

    def _maybe_fail(self, op: str) -> None:
        if op in self.fail_on:
            raise RuntimeError(f"injected failure at {op}")

    async def answer(self, channel_id: str) -> None:
        self._maybe_fail("answer")
        self.answered.append(channel_id)

    async def hangup(self, channel_id: str) -> None:
        self._maybe_fail("hangup")
        self.hung_up.append(channel_id)

    async def play_media(self, channel_id: str, media: bytes) -> None:
        raise AssertionError("live calls must use RTP egress, not play_media")

    async def create_external_media(
        self, *, app: str, external_host: str, media_format: str = "ulaw"
    ) -> str:
        self._maybe_fail("create_external_media")
        self.external_hosts.append(external_host)
        return "external-1"

    async def create_bridge(self) -> str:
        self._maybe_fail("create_bridge")
        return self.bridges[0]

    async def add_channel_to_bridge(self, bridge_id: str, channel_id: str) -> None:
        self._maybe_fail("add_channel_to_bridge")
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
        self.greeting_calls: list[dict[str, object]] = []

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
        self.greeting_calls.append(kwargs)
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
            dev_router=DevInboundRouter(
                "1000", tenant_id="kaari-planters", agent_id="kaari-sales-agent"
            ),
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

    # The phone channel was answered before the media wait even though no
    # RTP ever arrived: the timeout is about media, never about answering.
    assert harness.transport.answered == ["phone-1"]
    # No greeting was attempted without a ready media path.
    assert harness.voice.greeting_calls == []
    # Call record hung up, bridge destroyed, no lingering state.
    assert harness.runner._states == {}  # type: ignore[attr-defined]
    assert harness.transport.bridges_destroyed == ["bridge-1"]
    assert harness.ingress.pending("phone-1") == 0


def test_runner_answers_before_waiting_for_media() -> None:
    harness = Harness()
    observed: dict[str, object] = {}
    runner = harness.runner
    real_wait = runner._wait_for_media  # type: ignore[attr-defined]

    async def spy_wait(channel_id: str) -> tuple[str, int]:
        # When the media wait begins, the ARI answer must already be done.
        observed["answered"] = list(harness.transport.answered)
        observed["session_started"] = len(harness.voice.sessions)
        return await real_wait(channel_id)

    async def main() -> None:
        harness.ingress.note_remote_addr("phone-1", ("127.0.0.1", 9999))
        runner._wait_for_media = spy_wait  # type: ignore[attr-defined, method-assign]
        try:
            await runner.handle_event(stasis_start())
        finally:
            await runner.handle_event(hangup_event("StasisEnd", "phone-1"))

    asyncio.run(main())

    assert observed["answered"] == ["phone-1"]
    assert observed["session_started"] == 0


def test_runner_hangup_during_media_setup_cleans_up_once() -> None:
    harness = Harness(first_packet_timeout_seconds=0.6)

    async def main() -> None:
        setup = asyncio.create_task(runner_handle())
        await asyncio.sleep(0.1)
        # Caller hangs up while the runner is still waiting for first RTP.
        await harness.runner.handle_event(hangup_event("StasisEnd", "phone-1"))
        await setup

    async def runner_handle() -> None:
        await harness.runner.handle_event(stasis_start())

    asyncio.run(main())

    assert harness.transport.hung_up.count("phone-1") == 1
    assert harness.transport.hung_up.count("external-1") == 1
    assert harness.transport.bridges_destroyed == ["bridge-1"]
    assert harness.runner._states == {}  # type: ignore[attr-defined]
    ended = [
        event.name
        for event in harness.publisher.published
        if event.name == "call.ended.v1"
    ]
    assert len(ended) == 1


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


def test_setup_failure_records_stage_and_safe_reason(
    caplog: pytest.LogCaptureFixture,
) -> None:
    harness = Harness()
    harness.transport.fail_on.add("answer")
    caplog.set_level(logging.INFO, logger="voice_service.telephony.events")

    asyncio.run(harness.runner.handle_event(stasis_start()))

    failed = [
        record.telephony_event
        for record in caplog.records
        if record.telephony_event["event"] == "inbound_setup_failed"
    ]
    assert len(failed) == 1
    payload = failed[0]
    assert payload["stage"] == "answer"
    assert payload["error"] == "PlatformError"
    assert "could not answer" in payload["error_message"]
    assert payload["error_code"] == "telephony_provider_error"
    assert harness.runner._states == {}  # type: ignore[attr-defined]


def test_setup_failure_message_text_carries_safe_diagnostics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    harness = Harness()
    harness.transport.fail_on.add("answer")
    caplog.set_level(logging.INFO, logger="voice_service.telephony.events")

    asyncio.run(harness.runner.handle_event(stasis_start()))

    messages = [
        record.getMessage()
        for record in caplog.records
        if record.telephony_event["event"] == "inbound_setup_failed"
    ]
    assert len(messages) == 1
    assert "stage=answer" in messages[0]
    assert "error=PlatformError" in messages[0]
    assert "error_code=telephony_provider_error" in messages[0]
    assert "could not answer" in messages[0]


def test_setup_failure_message_redacts_credentials() -> None:
    from voice_service.telephony.asterisk.live_call import _setup_failure_message

    message = _setup_failure_message(
        stage="answer",
        exc=RuntimeError("dial failed: password=hunter2 token=abc"),
        error_code=None,
    )

    assert message.startswith("inbound_setup_failed stage=answer")
    assert "error=RuntimeError" in message
    assert "hunter2" not in message
    assert "password=***" in message
    assert "error_code" not in message


def test_setup_failure_before_any_mark_has_null_error_code(
    caplog: pytest.LogCaptureFixture,
) -> None:
    harness = Harness()
    harness.transport.fail_on.add("create_bridge")
    caplog.set_level(logging.INFO, logger="voice_service.telephony.events")

    asyncio.run(harness.runner.handle_event(stasis_start()))

    failed = [
        record.telephony_event
        for record in caplog.records
        if record.telephony_event["event"] == "inbound_setup_failed"
    ]
    assert len(failed) == 1
    assert failed[0]["stage"] == "external_media"
    assert failed[0]["error"] == "RuntimeError"
    assert failed[0]["error_code"] is None
    assert harness.runner._states == {}  # type: ignore[attr-defined]


def test_safe_error_message_redacts_credentials() -> None:
    from voice_service.telephony.asterisk.live_call import _safe_error_message

    leaked = RuntimeError(
        "dial failed: password=hunter2 api_key=AKIA123 token=abc "
        "Authorization: Bearer xyz secret=top"
    )
    scrubbed = _safe_error_message(leaked)

    assert "hunter2" not in scrubbed
    assert "AKIA123" not in scrubbed
    assert "Bearer xyz" not in scrubbed
    assert "password=***" in scrubbed
    assert "dial failed" in scrubbed


def test_safe_error_message_truncates_long_messages() -> None:
    from voice_service.telephony.asterisk.live_call import _safe_error_message

    scrubbed = _safe_error_message(RuntimeError("x" * 500))

    assert len(scrubbed) <= 203
    assert scrubbed.endswith("...")


def test_isolated_turn_failure_keeps_call_alive() -> None:
    from call_e_shared.exceptions import PlatformError
    from datetime import UTC, datetime

    from voice_service.telephony.asterisk.live_call import _LiveCallState
    from voice_service.telephony.models import TelephonyCall
    from voice_service.utterance import UtteranceAccumulator

    harness = Harness()
    now = datetime.now(UTC)
    call = TelephonyCall(
        call_id="call-1",
        tenant_id="tenant-1",
        agent_id="agent-1",
        conversation_id="conv",
        caller_number="+15550001",
        destination_number="1000",
        direction="inbound",
        metadata={"channel_id": "phone-1"},
        created_at=now,
        updated_at=now,
    )
    state = _LiveCallState(
        call=call,
        request_id="req-1",
        stop_turns=asyncio.Event(),
        accumulator=UtteranceAccumulator(
            config=harness.runner._utterance_config  # type: ignore[attr-defined]
        ),
    )
    harness.runner._states["phone-1"] = state  # type: ignore[attr-defined]
    harness.ingress.note_remote_addr("phone-1", ("127.0.0.1", 40000))

    async def failing_process_audio(**kwargs: object) -> object:
        raise PlatformError(code="voice_tts_error", message="tts down", status_code=502)

    harness.telephony.process_audio = failing_process_audio  # type: ignore[method-assign]

    async def main() -> bool:
        for _ in range(10):
            harness.ingress.ingest("phone-1", build_rtp_datagram(voice_frame()))
        for _ in range(15):
            harness.ingress.ingest("phone-1", build_rtp_datagram(silence_frame()))
        return await harness.runner._run_one_turn_with_barge_watch(state)  # type: ignore[attr-defined]

    assert asyncio.run(main()) is True

    # No cleanup: the channel is still tracked and the call can continue.
    assert "phone-1" in harness.runner._states  # type: ignore[attr-defined]
    assert state.consecutive_failures == 1


def test_three_failed_turns_keep_call_alive() -> None:
    from call_e_shared.exceptions import PlatformError
    from datetime import UTC, datetime

    from voice_service.telephony.asterisk.live_call import _LiveCallState
    from voice_service.telephony.models import TelephonyCall
    from voice_service.utterance import UtteranceAccumulator

    harness = Harness()
    now = datetime.now(UTC)
    call = TelephonyCall(
        call_id="call-1",
        tenant_id="tenant-1",
        agent_id="agent-1",
        conversation_id="conv",
        caller_number="+15550001",
        destination_number="1000",
        direction="inbound",
        metadata={"channel_id": "phone-1"},
        created_at=now,
        updated_at=now,
    )
    state = _LiveCallState(
        call=call,
        request_id="req-1",
        stop_turns=asyncio.Event(),
        accumulator=UtteranceAccumulator(
            config=harness.runner._utterance_config  # type: ignore[attr-defined]
        ),
    )
    harness.runner._states["phone-1"] = state  # type: ignore[attr-defined]
    harness.ingress.note_remote_addr("phone-1", ("127.0.0.1", 40000))

    async def failing_process_audio(**kwargs: object) -> object:
        raise PlatformError(code="voice_tts_error", message="tts down", status_code=502)

    harness.telephony.process_audio = failing_process_audio  # type: ignore[method-assign]

    async def main() -> None:
        for _ in range(3):
            for _ in range(10):
                harness.ingress.ingest("phone-1", build_rtp_datagram(voice_frame()))
            for _ in range(15):
                harness.ingress.ingest("phone-1", build_rtp_datagram(silence_frame()))
            await harness.runner._run_one_turn_with_barge_watch(state)  # type: ignore[attr-defined]

    asyncio.run(main())

    assert state.consecutive_failures == 3
    # Far below the runaway guard: the runner keeps tracking the call.
    assert "phone-1" in harness.runner._states  # type: ignore[attr-defined]


def test_runaway_guard_ends_call_after_many_consecutive_failures() -> None:
    from call_e_shared.exceptions import PlatformError
    from datetime import UTC, datetime

    from voice_service.telephony.asterisk.live_call import _LiveCallState
    from voice_service.telephony.models import TelephonyCall
    from voice_service.utterance import UtteranceAccumulator

    harness = Harness()
    now = datetime.now(UTC)
    call = TelephonyCall(
        call_id="call-1",
        tenant_id="tenant-1",
        agent_id="agent-1",
        conversation_id="conv",
        caller_number="+15550001",
        destination_number="1000",
        direction="inbound",
        metadata={"channel_id": "phone-1"},
        created_at=now,
        updated_at=now,
    )
    state = _LiveCallState(
        call=call,
        request_id="req-1",
        stop_turns=asyncio.Event(),
        consecutive_failures=19,
        accumulator=UtteranceAccumulator(
            config=harness.runner._utterance_config  # type: ignore[attr-defined]
        ),
    )
    harness.runner._states["phone-1"] = state  # type: ignore[attr-defined]
    harness.ingress.note_remote_addr("phone-1", ("127.0.0.1", 40000))

    async def failing_process_audio(**kwargs: object) -> object:
        raise PlatformError(code="voice_tts_error", message="tts down", status_code=502)

    harness.telephony.process_audio = failing_process_audio  # type: ignore[method-assign]

    async def main() -> None:
        for _ in range(10):
            harness.ingress.ingest("phone-1", build_rtp_datagram(voice_frame()))
        for _ in range(15):
            harness.ingress.ingest("phone-1", build_rtp_datagram(silence_frame()))
        await harness.runner._run_one_turn_with_barge_watch(state)  # type: ignore[attr-defined]

    asyncio.run(main())

    assert state.consecutive_failures == 20
    # Guard tripped: the runner gave up tracking the broken call.
    assert "phone-1" not in harness.runner._states  # type: ignore[attr-defined]


def test_turn_logs_start_and_completion(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    caplog.set_level(logging.INFO, logger="voice_service.telephony.events")
    harness = Harness(
        greeting=AudioChunk(data=b"\x00\x00" * 160, format="pcm")
    )

    async def main() -> None:
        harness.ingress.note_remote_addr("phone-1", ("127.0.0.1", 40001))
        await harness.runner.handle_event(stasis_start())
        state = harness.runner._states["phone-1"]  # type: ignore[attr-defined]
        for _ in range(10):
            harness.ingress.ingest("phone-1", build_rtp_datagram(voice_frame()))
        for _ in range(10):
            harness.ingress.ingest("phone-1", build_rtp_datagram(silence_frame()))
        await harness.runner._run_one_turn_with_barge_watch(state)  # type: ignore[attr-defined]
        await harness.runner.handle_event(hangup_event("StasisEnd", "phone-1"))

    asyncio.run(main())

    started = [
        record.telephony_event
        for record in caplog.records
        if getattr(record, "telephony_event", None) is not None
        and record.telephony_event["event"] == "TURN_START"
    ]
    completed = [
        record.telephony_event
        for record in caplog.records
        if getattr(record, "telephony_event", None) is not None
        and record.telephony_event["event"] == "TURN_COMPLETED"
    ]
    assert len(started) == 1
    assert started[0]["turn"] == 1
    assert len(completed) == 1
    assert completed[0]["turn"] == 1


def test_barge_watcher_detects_speech_and_preserves_utterance() -> None:
    from datetime import UTC, datetime

    from voice_service.telephony.asterisk.live_call import _LiveCallState
    from voice_service.telephony.models import TelephonyCall
    from voice_service.utterance import UtteranceAccumulator

    harness = Harness()
    now = datetime.now(UTC)
    call = TelephonyCall(
        call_id="call-1",
        tenant_id="tenant-1",
        agent_id="agent-1",
        conversation_id="conv",
        caller_number="+15550001",
        destination_number="1000",
        direction="inbound",
        metadata={"channel_id": "phone-1"},
        created_at=now,
        updated_at=now,
    )
    state = _LiveCallState(
        call=call,
        request_id="req-1",
        stop_turns=asyncio.Event(),
        accumulator=UtteranceAccumulator(
            config=harness.runner._utterance_config  # type: ignore[attr-defined]
        ),
    )
    harness.ingress.note_remote_addr("phone-1", ("127.0.0.1", 40000))

    for _ in range(10):
        harness.ingress.ingest("phone-1", build_rtp_datagram(voice_frame()))
    assert harness.runner._drain_watching_for_barge(state) is True  # type: ignore[attr-defined]

    for _ in range(15):
        harness.ingress.ingest("phone-1", build_rtp_datagram(silence_frame()))
    # Trailing silence is not barge-in, but it completes the utterance.
    assert harness.runner._drain_watching_for_barge(state) is False  # type: ignore[attr-defined]
    assert state.pending_utterance is not None

    # The next turn starts cleanly from the preserved utterance.
    collected = harness.runner._collect_utterance(state)  # type: ignore[attr-defined]
    assert collected is not None
    assert state.pending_utterance is None


def test_barge_watcher_ignores_silence() -> None:
    from datetime import UTC, datetime

    from voice_service.telephony.asterisk.live_call import _LiveCallState
    from voice_service.telephony.models import TelephonyCall
    from voice_service.utterance import UtteranceAccumulator

    harness = Harness()
    now = datetime.now(UTC)
    call = TelephonyCall(
        call_id="call-1",
        tenant_id="tenant-1",
        agent_id="agent-1",
        conversation_id="conv",
        caller_number="+15550001",
        destination_number="1000",
        direction="inbound",
        metadata={"channel_id": "phone-1"},
        created_at=now,
        updated_at=now,
    )
    state = _LiveCallState(
        call=call,
        request_id="req-1",
        stop_turns=asyncio.Event(),
        accumulator=UtteranceAccumulator(
            config=harness.runner._utterance_config  # type: ignore[attr-defined]
        ),
    )
    harness.ingress.note_remote_addr("phone-1", ("127.0.0.1", 40000))

    for _ in range(10):
        harness.ingress.ingest("phone-1", build_rtp_datagram(silence_frame()))
    assert harness.runner._drain_watching_for_barge(state) is False  # type: ignore[attr-defined]
    assert state.pending_utterance is None


def test_barge_watch_interrupts_slow_turn() -> None:
    from datetime import UTC, datetime

    from voice_service.telephony.asterisk.live_call import _LiveCallState
    from voice_service.telephony.models import TelephonyCall
    from voice_service.utterance import UtteranceAccumulator

    harness = Harness()
    now = datetime.now(UTC)
    call = TelephonyCall(
        call_id="call-1",
        tenant_id="tenant-1",
        agent_id="agent-1",
        conversation_id="conv",
        caller_number="+15550001",
        destination_number="1000",
        direction="inbound",
        metadata={"channel_id": "phone-1"},
        created_at=now,
        updated_at=now,
    )
    state = _LiveCallState(
        call=call,
        request_id="req-1",
        stop_turns=asyncio.Event(),
        accumulator=UtteranceAccumulator(
            config=harness.runner._utterance_config  # type: ignore[attr-defined]
        ),
    )
    interrupts: list[tuple[str, str]] = []
    slow_calls = 0

    async def slow_turn(watched: object) -> bool:
        nonlocal slow_calls
        slow_calls += 1
        await asyncio.sleep(0.3)
        return True

    async def fake_interrupt(**kwargs: object) -> bool:
        interrupts.append((str(kwargs["tenant_id"]), str(kwargs["call_id"])))
        return True

    harness.runner._run_one_turn = slow_turn  # type: ignore[method-assign]
    harness.telephony.interrupt_audio = fake_interrupt  # type: ignore[method-assign]

    async def main() -> bool:
        task = asyncio.create_task(
            harness.runner._run_one_turn_with_barge_watch(state)  # type: ignore[attr-defined]
        )
        await asyncio.sleep(0.05)
        for _ in range(5):
            harness.ingress.ingest("phone-1", build_rtp_datagram(voice_frame()))
        return await task

    assert asyncio.run(main()) is True
    assert slow_calls == 1
    assert interrupts == [("tenant-1", "call-1")]

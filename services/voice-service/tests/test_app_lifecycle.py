"""Tests for the voice-service application lifespan.

The live-call runner must start exactly once via the ASGI lifespan (not via
deprecated on_event hooks) and stop cleanly on shutdown, so a restarted
voice-service process reliably registers the ARI Stasis application.
"""

import logging

import pytest
from fastapi.testclient import TestClient

from voice_service.agent_runtime import AgentConfiguration, RuntimeResult
from voice_service.app import create_voice_app
from voice_service.session_store import InMemoryVoiceSessionStore
from voice_service.stt import MockSTTProvider
from voice_service.telephony.mock_provider import MockTelephonyProvider
from voice_service.telephony.store import InMemoryCallStore
from voice_service.tts import MockTTSProvider


class FakeAgentRuntimeClient:
    """Deterministic runtime boundary for lifespan tests."""

    async def get_agent(self, *, tenant_id: str, agent_id: str) -> AgentConfiguration:
        return AgentConfiguration(
            id=agent_id, tenant_id=tenant_id, language="en", voice_id=None
        )

    async def respond(
        self, *, tenant_id: str, agent_id: str, conversation_id: str, message: str
    ) -> RuntimeResult:
        return RuntimeResult(
            text="hi",
            provider_name="mock",
            model_name="mock-agent-runtime-v1",
            conversation_id=conversation_id,
            agent_id=agent_id,
        )


class FakeLiveCallRunner:
    """Recording stand-in for AsteriskLiveCallRunner."""

    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    async def start(self) -> None:
        self.start_calls += 1

    async def stop(self) -> None:
        self.stop_calls += 1


class FakeDatabase:
    """Recording stand-in for VoiceDatabase persistence wiring."""

    def __init__(self) -> None:
        self.session_store = InMemoryVoiceSessionStore()
        self.call_store = InMemoryCallStore()
        self.initialize_calls = 0
        self.close_calls = 0

    async def initialize(self) -> None:
        self.initialize_calls += 1

    async def close(self) -> None:
        self.close_calls += 1


def build_app(
    *,
    runner: FakeLiveCallRunner | None = None,
    database: FakeDatabase | None = None,
    enable_live_calls: bool | None = None,
):
    return create_voice_app(
        session_store=None if database is not None else InMemoryVoiceSessionStore(),
        database=database,  # type: ignore[arg-type]
        agent_runtime=FakeAgentRuntimeClient(),  # type: ignore[arg-type]
        stt_provider=MockSTTProvider(),
        tts_provider=MockTTSProvider(),
        telephony_provider=MockTelephonyProvider(),
        live_call_runner=runner,  # type: ignore[arg-type]
        enable_live_calls=enable_live_calls,
    )


def test_lifespan_starts_runner_once_and_stops_on_shutdown() -> None:
    runner = FakeLiveCallRunner()
    database = FakeDatabase()
    app = build_app(runner=runner, database=database)

    with TestClient(app):
        assert runner.start_calls == 1
        assert runner.stop_calls == 0
    assert runner.stop_calls == 1

    assert database.initialize_calls == 1
    assert database.close_calls == 1


def test_lifespan_logs_runner_started_without_secrets(
    caplog: pytest.LogCaptureFixture,
) -> None:
    runner = FakeLiveCallRunner()
    app = build_app(runner=runner)

    with caplog.at_level(logging.INFO, logger="voice_service.telephony.events"):
        with TestClient(app):
            pass

    started = [
        record
        for record in caplog.records
        if record.getMessage() == "ARI live-call runner started"
    ]
    assert len(started) == 1
    for record in caplog.records:
        assert "api_key" not in record.getMessage()
        assert "password" not in record.getMessage().lower()


def test_lifespan_without_runner_starts_and_stops_cleanly() -> None:
    app = build_app()

    assert app.state.live_call_runner is None
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200


def test_lifespan_disabled_runner_never_starts() -> None:
    from voice_service.telephony.asterisk.adapter import AsteriskAdapter
    from voice_service.telephony.config import TelephonySettings

    class SilentTransport:
        provider_name = "asterisk"

        async def answer_call(self, call: object, **kwargs: object) -> object:
            return call

    app = create_voice_app(
        session_store=InMemoryVoiceSessionStore(),
        agent_runtime=FakeAgentRuntimeClient(),  # type: ignore[arg-type]
        stt_provider=MockSTTProvider(),
        tts_provider=MockTTSProvider(),
        telephony_provider=AsteriskAdapter(
            base_url="http://asterisk:8088",
            transport=SilentTransport(),  # type: ignore[arg-type]
        ),
        telephony_settings=TelephonySettings(
            provider="asterisk", asterisk_url="http://asterisk:8088"
        ),
        enable_live_calls=False,
    )

    assert app.state.live_call_runner is None
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200


def test_runner_start_is_idempotent() -> None:
    import asyncio

    from voice_service.telephony.asterisk.adapter import AsteriskAdapter
    from voice_service.telephony.asterisk.live_call import AsteriskLiveCallRunner
    from voice_service.telephony.dev_routing import KaariDevRouter

    class FakeStream:
        def __init__(self) -> None:
            self.run_calls = 0
            self.stopped = False

        async def run(self, handler: object) -> None:
            self.run_calls += 1
            await asyncio.sleep(3600)

        async def stop(self) -> None:
            self.stopped = True

    stream = FakeStream()
    runner = AsteriskLiveCallRunner(
        adapter=AsteriskAdapter(base_url="http://asterisk:8088"),
        telephony_service=object(),  # type: ignore[arg-type]
        dev_router=KaariDevRouter("1000"),
        event_stream=stream,  # type: ignore[arg-type]
    )

    async def main() -> None:
        await runner.start()
        await runner.start()
        for _ in range(10):
            await asyncio.sleep(0)
        assert stream.run_calls == 1
        await runner.stop()

    asyncio.run(main())
    assert stream.stopped is True

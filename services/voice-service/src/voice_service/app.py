"""Voice service application assembly."""

import os

from fastapi import FastAPI

from call_e_shared import create_app

from voice_service.agent_runtime import (
    AgentRuntimeClient,
    create_agent_runtime_http_client,
)
from voice_service.config import (
    STTSettings,
    TTSSettings,
    load_stt_settings,
    load_tts_settings,
)
from voice_service.database import VoiceDatabase, create_voice_database
from voice_service.factory import STTProviderFactory, TTSProviderFactory
from voice_service.routes.voice import router as voice_router
from voice_service.session import VoiceSessionManager
from voice_service.session_store import InMemoryVoiceSessionStore, VoiceSessionStore
from voice_service.stt import STTProvider
from voice_service.telephony import (
    TelephonyProvider,
    TelephonyProviderFactory,
    TelephonySettings,
    load_live_call_settings,
    load_rtp_settings,
    load_telephony_settings,
)
from voice_service.telephony.asterisk.adapter import AsteriskAdapter
from voice_service.telephony.asterisk.ari_client import AriEventStream
from voice_service.telephony.asterisk.live_call import AsteriskLiveCallRunner
from voice_service.telephony.dev_routing import KaariDevRouter
from voice_service.telephony.events import EventPublisher, LoggingEventPublisher
from voice_service.telephony.routes import router as telephony_router
from voice_service.telephony.service import TelephonyService
from voice_service.telephony.store import CallStore, InMemoryCallStore
from voice_service.tts import TTSProvider


VOICE_SERVICE_NAME = "voice-service"


def create_voice_app(
    *,
    session_store: VoiceSessionStore | None = None,
    database: VoiceDatabase | None = None,
    stt_provider: STTProvider | None = None,
    tts_provider: TTSProvider | None = None,
    stt_settings: STTSettings | None = None,
    tts_settings: TTSSettings | None = None,
    agent_runtime: AgentRuntimeClient | None = None,
    telephony_provider: TelephonyProvider | None = None,
    telephony_settings: TelephonySettings | None = None,
    call_store: CallStore | None = None,
    event_publisher: EventPublisher | None = None,
    dev_inbound_router: KaariDevRouter | None = None,
    live_call_runner: AsteriskLiveCallRunner | None = None,
    enable_live_calls: bool | None = None,
) -> FastAPI:
    """Create the service hosting the tenant-scoped voice session lifecycle."""
    app = create_app(VOICE_SERVICE_NAME)
    if database is None and session_store is None:
        database = create_voice_database()
    if session_store is None:
        if database is not None:
            session_store = database.session_store
        else:
            session_store = InMemoryVoiceSessionStore()
    if call_store is None:
        if database is not None:
            call_store = database.call_store
        else:
            call_store = InMemoryCallStore()

    runtime = agent_runtime or create_agent_runtime_http_client()
    manager = VoiceSessionManager(
        stt_provider=stt_provider or STTProviderFactory.create(stt_settings or load_stt_settings()),
        tts_provider=tts_provider or TTSProviderFactory.create(tts_settings or load_tts_settings()),
        agent_runtime=runtime,
        session_store=session_store,
    )
    app.state.voice_session_manager = manager
    app.include_router(voice_router)

    resolved_telephony_settings = (
        telephony_settings or load_telephony_settings()
    )
    provider = telephony_provider or TelephonyProviderFactory.create(
        resolved_telephony_settings
    )
    telephony = TelephonyService(
        provider=provider,
        call_store=call_store,
        voice_manager=manager,
        event_publisher=event_publisher or LoggingEventPublisher(),
    )
    app.state.telephony_service = telephony
    router_instance = dev_inbound_router or KaariDevRouter.from_environment()
    app.state.dev_inbound_router = router_instance
    app.include_router(telephony_router)

    runner = live_call_runner or _build_live_call_runner(
        provider=provider,
        telephony=telephony,
        dev_router=router_instance,
        settings=resolved_telephony_settings,
        enable_live_calls=enable_live_calls,
    )
    app.state.live_call_runner = runner
    if runner is not None:

        @app.on_event("startup")
        async def start_live_call_runner() -> None:
            await runner.start()

        @app.on_event("shutdown")
        async def stop_live_call_runner() -> None:
            await runner.stop()

    if database is not None:

        @app.on_event("startup")
        async def initialize_voice_database() -> None:
            await database.initialize()

        @app.on_event("shutdown")
        async def close_voice_database() -> None:
            await telephony.close()
            await database.close()
            await _close_provider(manager.stt_provider)
            await _close_provider(manager.tts_provider)
            close_runtime = getattr(runtime, "close", None)
            if close_runtime is not None:
                await close_runtime()

    return app


async def _close_provider(provider: object) -> None:
    close_method = getattr(provider, "close", None)
    if close_method is not None:
        await close_method()


def _build_live_call_runner(
    *,
    provider: TelephonyProvider,
    telephony: TelephonyService,
    dev_router: KaariDevRouter,
    settings: TelephonySettings,
    enable_live_calls: bool | None,
) -> AsteriskLiveCallRunner | None:
    """Build the ARI-driven live runner for Asterisk deployments only."""
    if not isinstance(provider, AsteriskAdapter):
        return None
    live_settings = load_live_call_settings(
        telephony_provider=settings.provider
    )
    if enable_live_calls is not None:
        enabled = enable_live_calls
    else:
        # An explicitly wired AsteriskAdapter opts into live calls; the
        # ASTERISK_LIVE_CALLS environment variable can still force it off.
        enabled = live_settings.enabled or (
            isinstance(provider, AsteriskAdapter)
            and os.getenv("ASTERISK_LIVE_CALLS", "").strip().lower()
            not in ("0", "false", "no", "off")
        )
    if not enabled or not settings.asterisk_url:
        return None
    rtp_settings = load_rtp_settings()
    stream = AriEventStream(
        base_url=settings.asterisk_url,
        app=live_settings.ari_app,
        username=settings.asterisk_username,
        password=settings.asterisk_password,
    )
    return AsteriskLiveCallRunner(
        adapter=provider,
        telephony_service=telephony,
        dev_router=dev_router,
        event_stream=stream,
        rtp_host=rtp_settings.host,
        rtp_port_start=rtp_settings.port_start,
        rtp_port_count=rtp_settings.port_count,
        first_packet_timeout_seconds=rtp_settings.first_packet_timeout_seconds,
    )

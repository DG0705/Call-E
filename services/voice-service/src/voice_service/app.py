"""Voice service application assembly."""

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
    load_telephony_settings,
)
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

    telephony = TelephonyService(
        provider=telephony_provider
        or TelephonyProviderFactory.create(
            telephony_settings or load_telephony_settings()
        ),
        call_store=call_store,
        voice_manager=manager,
        event_publisher=event_publisher or LoggingEventPublisher(),
    )
    app.state.telephony_service = telephony
    app.include_router(telephony_router)

    if database is not None:

        @app.on_event("startup")
        async def initialize_voice_database() -> None:
            await database.initialize()

        @app.on_event("shutdown")
        async def close_voice_database() -> None:
            await telephony.close()
            await database.close()
            close_runtime = getattr(runtime, "close", None)
            if close_runtime is not None:
                await close_runtime()

    return app

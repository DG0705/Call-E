"""The application flow that orchestrates one real-time voice turn."""

import logging
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel

from call_e_shared.exceptions import PlatformError

from voice_service.agent_runtime import AgentRuntimeClient
from voice_service.audio import AudioChunk, decode_wav
from voice_service.models import AudioFormat, VoiceSession
from voice_service.observability import VOICE_EVENT_LOGGER, log_voice_event
from voice_service.session_store import VoiceSessionStore
from voice_service.stt import STTProvider
from voice_service.tts import TTSProvider

_AGENT_UNAVAILABLE_MESSAGE = "Agent configuration is unavailable."
_AGENT_UNAVAILABLE_CODE = "voice_agent_unavailable"
_SESSION_NOT_FOUND_CODE = "voice_session_not_found"
_SESSION_ENDED_CODE = "voice_session_ended"
_SESSION_FAILED_CODE = "voice_session_failed"
_STT_ERROR_CODE = "voice_stt_error"
_RUNTIME_ERROR_CODE = "voice_runtime_error"
_TTS_ERROR_CODE = "voice_tts_error"


class VoiceTurnResult(BaseModel):
    """Outcome of processing one user audio utterance."""

    session_id: str
    tenant_id: str
    agent_id: str
    conversation_id: str
    transcript: str
    response_text: str
    audio: AudioChunk
    stt_provider: str
    stt_confidence: float | None = None
    runtime_provider: str
    runtime_model: str
    tts_provider: str
    tts_voice_id: str | None = None
    content_type: str


class VoiceSessionManager:
    """Own the voice lifecycle while delegating speech and agent work."""

    def __init__(
        self,
        *,
        stt_provider: STTProvider,
        tts_provider: TTSProvider,
        agent_runtime: AgentRuntimeClient,
        session_store: VoiceSessionStore,
        logger: logging.Logger | None = None,
    ) -> None:
        self._stt_provider = stt_provider
        self._tts_provider = tts_provider
        self._agent_runtime = agent_runtime
        self._session_store = session_store
        self._logger = logger or logging.getLogger(VOICE_EVENT_LOGGER)

    async def create_session(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        conversation_id: str,
        language: str = "en",
        input_audio_format: AudioFormat = "pcm",
        output_audio_format: AudioFormat = "pcm",
        voice_id: str | None = None,
        request_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> VoiceSession:
        """Validate the agent, then create a session in the created state."""
        try:
            agent = await self._agent_runtime.get_agent(
                tenant_id=tenant_id, agent_id=agent_id
            )
        except Exception as exc:
            log_voice_event(
                self._logger,
                "session_created",
                tenant_id=tenant_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                request_id=request_id,
                outcome="failed",
            )
            raise PlatformError(
                code=_AGENT_UNAVAILABLE_CODE,
                message=_AGENT_UNAVAILABLE_MESSAGE,
                status_code=502,
            ) from exc
        now = datetime.now(UTC)
        session = VoiceSession(
            session_id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            status="created",
            language=agent.language or language,
            input_audio_format=input_audio_format,
            output_audio_format=output_audio_format,
            voice_id=voice_id or agent.voice_id,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )
        await self._session_store.create(session)
        log_voice_event(
            self._logger,
            "session_created",
            tenant_id=tenant_id,
            agent_id=agent_id,
            session_id=session.session_id,
            conversation_id=conversation_id,
            request_id=request_id,
        )
        return session

    async def get_session(
        self, *, tenant_id: str, session_id: str
    ) -> VoiceSession:
        """Return one tenant-scoped session or fail with a not-found error."""
        return await self._require_session(tenant_id=tenant_id, session_id=session_id)

    async def process_audio_input(
        self,
        *,
        tenant_id: str,
        session_id: str,
        audio: AudioChunk,
        request_id: str | None = None,
    ) -> VoiceTurnResult:
        """Run the audio-to-speech pipeline for one user utterance."""
        session = await self._require_session(tenant_id=tenant_id, session_id=session_id)
        if session.status == "ended":
            raise PlatformError(
                code=_SESSION_ENDED_CODE,
                message="Voice session has ended.",
                status_code=409,
            )
        if session.status == "failed":
            raise PlatformError(
                code=_SESSION_FAILED_CODE,
                message="Voice session is in a failed state.",
                status_code=409,
            )
        if not audio.data:
            raise PlatformError(
                code="empty_audio", message="Audio payload is empty.", status_code=400
            )
        if audio.format not in ("pcm", "wav", "ulaw"):
            raise PlatformError(
                code="unsupported_audio_format",
                message=f"Unsupported audio format '{audio.format}'.",
                status_code=400,
            )
        audio = self._normalize_input_audio(audio)
        await self._mark(session, "processing")
        log_voice_event(
            self._logger,
            "turn_started",
            tenant_id=tenant_id,
            agent_id=session.agent_id,
            session_id=session.session_id,
            conversation_id=session.conversation_id,
            request_id=request_id,
            input_format=audio.format,
        )
        try:
            transcription = await self._stt_provider.transcribe(audio)
        except Exception as exc:
            await self._fail(session, _STT_ERROR_CODE)
            log_voice_event(
                self._logger,
                "turn_failed",
                tenant_id=tenant_id,
                agent_id=session.agent_id,
                session_id=session.session_id,
                conversation_id=session.conversation_id,
                request_id=request_id,
                stage="stt",
                error_code=_STT_ERROR_CODE,
            )
            raise PlatformError(
                code=_STT_ERROR_CODE,
                message="Speech-to-text processing failed.",
                status_code=502,
            ) from exc
        log_voice_event(
            self._logger,
            "transcription_completed",
            tenant_id=tenant_id,
            agent_id=session.agent_id,
            session_id=session.session_id,
            conversation_id=session.conversation_id,
            request_id=request_id,
            provider=transcription.provider,
        )
        if not transcription.text:
            await self._mark(session, "active")
            raise PlatformError(
                code="stt_no_transcript",
                message="No speech was recognized.",
                status_code=422,
            )
        try:
            runtime_result = await self._agent_runtime.respond(
                tenant_id=tenant_id,
                agent_id=session.agent_id,
                conversation_id=session.conversation_id,
                message=transcription.text,
            )
        except Exception as exc:
            await self._fail(session, _RUNTIME_ERROR_CODE)
            log_voice_event(
                self._logger,
                "turn_failed",
                tenant_id=tenant_id,
                agent_id=session.agent_id,
                session_id=session.session_id,
                conversation_id=session.conversation_id,
                request_id=request_id,
                stage="runtime",
                error_code=_RUNTIME_ERROR_CODE,
            )
            raise PlatformError(
                code=_RUNTIME_ERROR_CODE,
                message="Agent runtime failed to respond.",
                status_code=502,
            ) from exc
        log_voice_event(
            self._logger,
            "runtime_response_generated",
            tenant_id=tenant_id,
            agent_id=session.agent_id,
            session_id=session.session_id,
            conversation_id=session.conversation_id,
            request_id=request_id,
            provider=runtime_result.provider_name,
            model=runtime_result.model_name,
        )
        try:
            synthesis = await self._tts_provider.synthesize(
                text=runtime_result.text,
                voice_id=session.voice_id,
                language=session.language,
                output_format=session.output_audio_format,
            )
        except Exception as exc:
            await self._fail(session, _TTS_ERROR_CODE)
            log_voice_event(
                self._logger,
                "turn_failed",
                tenant_id=tenant_id,
                agent_id=session.agent_id,
                session_id=session.session_id,
                conversation_id=session.conversation_id,
                request_id=request_id,
                stage="tts",
                error_code=_TTS_ERROR_CODE,
            )
            raise PlatformError(
                code=_TTS_ERROR_CODE,
                message="Text-to-speech synthesis failed.",
                status_code=502,
            ) from exc
        log_voice_event(
            self._logger,
            "synthesis_completed",
            tenant_id=tenant_id,
            agent_id=session.agent_id,
            session_id=session.session_id,
            conversation_id=session.conversation_id,
            request_id=request_id,
            provider=synthesis.provider,
            content_type=synthesis.content_type,
        )
        await self._mark(session, "active")
        return VoiceTurnResult(
            session_id=session.session_id,
            tenant_id=session.tenant_id,
            agent_id=session.agent_id,
            conversation_id=session.conversation_id,
            transcript=transcription.text,
            response_text=runtime_result.text,
            audio=synthesis.audio,
            stt_provider=transcription.provider,
            stt_confidence=transcription.confidence,
            runtime_provider=runtime_result.provider_name,
            runtime_model=runtime_result.model_name,
            tts_provider=synthesis.provider,
            tts_voice_id=synthesis.voice_id,
            content_type=synthesis.content_type,
        )

    async def end_session(
        self, *, tenant_id: str, session_id: str, request_id: str | None = None
    ) -> VoiceSession:
        """End an active session, remaining idempotent per tenant boundary."""
        session = await self._require_session(tenant_id=tenant_id, session_id=session_id)
        if session.status == "ended":
            raise PlatformError(
                code=_SESSION_ENDED_CODE,
                message="Voice session has already ended.",
                status_code=409,
            )
        await self._mark(session, "ended")
        log_voice_event(
            self._logger,
            "session_ended",
            tenant_id=tenant_id,
            agent_id=session.agent_id,
            session_id=session.session_id,
            conversation_id=session.conversation_id,
            request_id=request_id,
        )
        return session

    async def _require_session(
        self, *, tenant_id: str, session_id: str
    ) -> VoiceSession:
        session = await self._session_store.get(
            tenant_id=tenant_id, session_id=session_id
        )
        if session is None:
            raise PlatformError(
                code=_SESSION_NOT_FOUND_CODE,
                message="Voice session was not found.",
                status_code=404,
            )
        return session

    async def _fail(self, session: VoiceSession, error_code: str) -> None:
        session.status = "failed"
        session.error_code = error_code
        session.updated_at = datetime.now(UTC)
        await self._session_store.save(session)

    async def _mark(self, session: VoiceSession, status: str) -> None:
        session.status = status  # type: ignore[assignment]
        session.updated_at = datetime.now(UTC)
        await self._session_store.save(session)

    @staticmethod
    def _normalize_input_audio(audio: AudioChunk) -> AudioChunk:
        """Decode WAV input to PCM for speech-to-text providers."""
        if audio.format != "wav":
            return audio
        try:
            return decode_wav(audio)
        except ValueError as exc:
            raise PlatformError(
                code="invalid_audio_format",
                message="WAV audio is malformed.",
                status_code=400,
            ) from exc

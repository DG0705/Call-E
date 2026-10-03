"""The application flow that orchestrates one real-time voice turn."""

import asyncio
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from call_e_shared.exceptions import PlatformError

from voice_service.agent_runtime import AgentRuntimeClient
from voice_service.audio import AudioChunk, PcmFrameAccumulator, decode_wav
from voice_service.config import TurnSettings
from voice_service.stt import STTResult
from voice_service.greeting_cache import (
    GreetingAudioStore,
    InMemoryGreetingAudioStore,
    greeting_cache_key,
)
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

_STT_FALLBACK_MESSAGE = (
    "I'm sorry, I didn't quite catch that. "
    "Could you please repeat your request?"
)
_RUNTIME_FALLBACK_MESSAGE = (
    "I'm sorry, I'm having trouble reaching our systems right now. "
    "Please bear with me and try again in a moment."
)
_TURN_TIMEOUT_MESSAGE = (
    "I'm sorry, give me just a moment."
)
_TURN_TIMEOUT_CODE = "voice_turn_timeout"


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
    audio_packets_streamed: int = 0
    tts_sentences: int = 0


def split_first_sentence(text: str) -> tuple[str | None, str]:
    """Split the first complete sentence off streamed LLM text.

    A boundary is sentence-final punctuation (``.``/``!``/``?``) followed by
    whitespace or the end of the buffer, with at least 20 characters buffered
    so tiny fragments (``OK.``, ``Mr.``) are never sent to TTS alone. Returns
    ``(None, text)`` until a safe boundary exists; the caller flushes the
    remainder when the stream ends.
    """
    match = re.search(r"^(.{20,}?[.!?])(?=\s|$)", text, re.DOTALL)
    if match is None:
        return None, text
    return match.group(1).strip(), text[match.end():].lstrip()


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
        turn_settings: TurnSettings | None = None,
        greeting_store: GreetingAudioStore | None = None,
    ) -> None:
        self._stt_provider = stt_provider
        self._tts_provider = tts_provider
        self._agent_runtime = agent_runtime
        self._session_store = session_store
        self._logger = logger or logging.getLogger(VOICE_EVENT_LOGGER)
        self._turn_settings = turn_settings or TurnSettings()
        self._greeting_store = greeting_store or InMemoryGreetingAudioStore()

    @property
    def stt_provider(self) -> STTProvider:
        """The configured speech-to-text provider."""
        return self._stt_provider

    @property
    def tts_provider(self) -> TTSProvider:
        """The configured text-to-speech provider."""
        return self._tts_provider

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
        session_metadata = dict(metadata or {})
        if agent.greeting:
            session_metadata["greeting"] = agent.greeting
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
            metadata=session_metadata,
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

    async def synthesize_greeting(
        self,
        *,
        tenant_id: str,
        session_id: str,
        request_id: str | None = None,
    ) -> AudioChunk | None:
        """Return the session's configured greeting audio, cached when possible.

        The greeting is static per agent configuration, so PCM synthesized for
        an identical (tenant, agent, text, voice, model, format) tuple is
        reused instead of calling TTS again. A configuration change misses the
        cache and regenerates; stale entries are pruned on store. Returns
        ``None`` when the agent declared no greeting.
        """
        session = await self._require_session(tenant_id=tenant_id, session_id=session_id)
        greeting = session.metadata.get("greeting")
        if not greeting:
            return None
        text = str(greeting)
        model = getattr(self._tts_provider, "_model_id", None) or getattr(
            self._tts_provider, "model_name", None
        )
        cache_key = greeting_cache_key(
            tenant_id=session.tenant_id,
            agent_id=session.agent_id,
            text=text,
            voice_id=session.voice_id,
            model=str(model) if model is not None else None,
            output_format=session.output_audio_format,
        )
        try:
            cached = await asyncio.wait_for(
                self._greeting_store.get(cache_key), timeout=3.0
            )
        except Exception:
            cached = None
        if cached is not None:
            log_voice_event(
                self._logger,
                "audio_synthesized",
                tenant_id=session.tenant_id,
                agent_id=session.agent_id,
                session_id=session.session_id,
                conversation_id=session.conversation_id,
                request_id=request_id,
                stage="greeting",
                provider=getattr(self._tts_provider, "provider_name", "unknown"),
                content_type="audio/pcm",
                greeting_cached=True,
            )
            return cached
        try:
            synthesis = await asyncio.wait_for(
                self._tts_provider.synthesize(
                    text=text,
                    voice_id=session.voice_id,
                    language=session.language,
                    output_format=session.output_audio_format,
                ),
                timeout=self._turn_settings.tts_timeout,
            )
        except Exception as exc:
            log_voice_event(
                self._logger,
                "audio_synthesized",
                tenant_id=session.tenant_id,
                agent_id=session.agent_id,
                session_id=session.session_id,
                conversation_id=session.conversation_id,
                request_id=request_id,
                stage="greeting",
                outcome="failed",
                error_code=_TTS_ERROR_CODE,
            )
            raise PlatformError(
                code=_TTS_ERROR_CODE,
                message="Text-to-speech synthesis failed.",
                status_code=502,
            ) from exc
        log_voice_event(
            self._logger,
            "audio_synthesized",
            tenant_id=session.tenant_id,
            agent_id=session.agent_id,
            session_id=session.session_id,
            conversation_id=session.conversation_id,
            request_id=request_id,
            stage="greeting",
            provider=synthesis.provider,
            content_type=synthesis.content_type,
            greeting_cached=False,
        )
        try:
            async with asyncio.timeout(5.0):
                await self._greeting_store.put(cache_key, synthesis.audio)
                await self._greeting_store.prune(
                    tenant_id=session.tenant_id,
                    agent_id=session.agent_id,
                    voice_id=session.voice_id,
                    keep_key=cache_key,
                )
        except Exception:
            self._logger.warning(
                "greeting cache store failed",
                extra={"session_id": session.session_id},
            )
        return synthesis.audio

    async def process_audio_input(
        self,
        *,
        tenant_id: str,
        session_id: str,
        audio: AudioChunk,
        request_id: str | None = None,
        audio_sink: Callable[[AudioChunk], Awaitable[None]] | None = None,
    ) -> VoiceTurnResult:
        """Run the audio-to-speech pipeline for one user utterance.

        When ``audio_sink`` is provided, synthesized speech streams through it
        as complete 20 ms PCM frames while the TTS response is still arriving
        (first audio plays before synthesis completes); otherwise the full
        utterance audio is buffered and returned classically.
        """
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
        # Monotonic stage markers for latency diagnostics: turn_started is
        # emitted when the finalized utterance enters the pipeline, so the
        # deltas below measure speech_end -> transcription -> runtime -> TTS.
        turn_start = time.monotonic()
        log_voice_event(
            self._logger,
            "STT_START",
            tenant_id=tenant_id,
            agent_id=session.agent_id,
            session_id=session.session_id,
            conversation_id=session.conversation_id,
            request_id=request_id,
            message="STT_START",
        )
        try:
            try:
                transcription = await asyncio.wait_for(
                    self._stt_provider.transcribe(audio),
                    timeout=self._turn_settings.stt_timeout,
                )
            except TimeoutError:
                # One immediate retry: provider stalls are usually transient,
                # and a rescued turn answers seconds sooner than a fallback.
                log_voice_event(
                    self._logger,
                    "stt_retry",
                    tenant_id=tenant_id,
                    agent_id=session.agent_id,
                    session_id=session.session_id,
                    conversation_id=session.conversation_id,
                    request_id=request_id,
                )
                transcription = await asyncio.wait_for(
                    self._stt_provider.transcribe(audio),
                    timeout=self._turn_settings.stt_timeout,
                )
        except TimeoutError:
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
                timeout=True,
                message="turn_failed stage=stt error=TimeoutError timeout=True",
            )
            return await self._fallback_turn(
                session,
                text=_STT_FALLBACK_MESSAGE,
                transcript="",
                request_id=request_id,
                error_code=_STT_ERROR_CODE,
            )
        except Exception:
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
                message="turn_failed stage=stt",
            )
            return await self._fallback_turn(
                session,
                text=_STT_FALLBACK_MESSAGE,
                transcript="",
                request_id=request_id,
                error_code=_STT_ERROR_CODE,
            )
        stt_done = time.monotonic()
        stt_elapsed_ms = int((stt_done - turn_start) * 1000)
        log_voice_event(
            self._logger,
            "transcription_completed",
            tenant_id=tenant_id,
            agent_id=session.agent_id,
            session_id=session.session_id,
            conversation_id=session.conversation_id,
            request_id=request_id,
            provider=transcription.provider,
            stt_elapsed_ms=stt_elapsed_ms,
        )
        if not transcription.text:
            await self._mark(session, "active")
            raise PlatformError(
                code="stt_no_transcript",
                message="No speech was recognized.",
                status_code=422,
            )
        # Prefer the streaming runtime when the sink is present: LLM text
        # deltas flow into per-sentence TTS while generation continues, so the
        # first sentence plays long before the complete response exists.
        # Buffered clients (and missing sinks) keep the classic path below.
        if audio_sink is not None and hasattr(
            self._agent_runtime, "respond_stream"
        ):
            return await self._run_streaming_turn(
                session=session,
                tenant_id=tenant_id,
                transcription=transcription,
                audio_sink=audio_sink,
                request_id=request_id,
                turn_start=turn_start,
                stt_done=stt_done,
                stt_elapsed_ms=stt_elapsed_ms,
            )
        try:
            runtime_result = await asyncio.wait_for(
                self._agent_runtime.respond(
                    tenant_id=tenant_id,
                    agent_id=session.agent_id,
                    conversation_id=session.conversation_id,
                    message=transcription.text,
                ),
                timeout=self._turn_settings.runtime_timeout,
            )
        except TimeoutError:
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
                timeout=True,
                message="turn_failed stage=runtime error=TimeoutError timeout=True",
            )
            return await self._fallback_turn(
                session,
                text=_RUNTIME_FALLBACK_MESSAGE,
                transcript=transcription.text,
                request_id=request_id,
                error_code=_RUNTIME_ERROR_CODE,
            )
        except Exception:
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
                message="turn_failed stage=runtime",
            )
            return await self._fallback_turn(
                session,
                text=_RUNTIME_FALLBACK_MESSAGE,
                transcript=transcription.text,
                request_id=request_id,
                error_code=_RUNTIME_ERROR_CODE,
            )
        runtime_done = time.monotonic()
        runtime_elapsed_ms = int((runtime_done - stt_done) * 1000)
        tool_iterations = int(
            getattr(runtime_result, "tool_iterations", 0) or 0
        ) or len(getattr(runtime_result, "tool_execution_history", None) or [])
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
            runtime_elapsed_ms=runtime_elapsed_ms,
        )
        tts_start = time.monotonic()
        log_voice_event(
            self._logger,
            "tts_started",
            tenant_id=tenant_id,
            agent_id=session.agent_id,
            session_id=session.session_id,
            conversation_id=session.conversation_id,
            request_id=request_id,
            output_format=session.output_audio_format,
            text_chars=len(runtime_result.text),
        )
        stream_stats: dict[str, object] | None = None
        if audio_sink is not None:
            try:
                stream_stats = await self._stream_tts_to_sink(
                    session=session,
                    text=runtime_result.text,
                    audio_sink=audio_sink,
                    request_id=request_id,
                    tts_start=tts_start,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                # Sink/RTP failure before any playout: fall through to the
                # buffered path so the classic send surfaces the same error.
                stream_stats = None
            if (
                stream_stats is not None
                and not stream_stats["completed"]
                and stream_stats["frames"] == 0
            ):
                # Provider failure (or empty stream) before first audio:
                # retry once via the buffered path below.
                stream_stats = None
        if stream_stats is not None and stream_stats["frames"] > 0:
            frames_sent = int(stream_stats["frames"])
            if not stream_stats["completed"]:
                log_voice_event(
                    self._logger,
                    "tts_stream_interrupted",
                    tenant_id=tenant_id,
                    agent_id=session.agent_id,
                    session_id=session.session_id,
                    conversation_id=session.conversation_id,
                    request_id=request_id,
                    frames_sent=frames_sent,
                    error=str(stream_stats.get("error") or "unknown"),
                )
            synth_done = time.monotonic()
            tts_elapsed_ms = int((synth_done - runtime_done) * 1000)
            turn_elapsed_ms = int((synth_done - turn_start) * 1000)
            log_voice_event(
                self._logger,
                "synthesis_completed",
                tenant_id=tenant_id,
                agent_id=session.agent_id,
                session_id=session.session_id,
                conversation_id=session.conversation_id,
                request_id=request_id,
                provider=getattr(self._tts_provider, "provider_name", "unknown"),
                tts_elapsed_ms=tts_elapsed_ms,
                streamed=True,
            )
            log_voice_event(
                self._logger,
                "turn_completed",
                tenant_id=tenant_id,
                agent_id=session.agent_id,
                session_id=session.session_id,
                conversation_id=session.conversation_id,
                request_id=request_id,
                stt_elapsed_ms=stt_elapsed_ms,
                runtime_elapsed_ms=runtime_elapsed_ms,
                tts_elapsed_ms=tts_elapsed_ms,
                turn_elapsed_ms=turn_elapsed_ms,
                tool_iterations=tool_iterations,
                response_chars=len(runtime_result.text),
                audio_bytes=int(stream_stats["bytes"]),
                audio_packets_streamed=frames_sent,
                streamed=True,
            )
            await self._mark(session, "active")
            return VoiceTurnResult(
                session_id=session.session_id,
                tenant_id=session.tenant_id,
                agent_id=session.agent_id,
                conversation_id=session.conversation_id,
                transcript=transcription.text,
                response_text=runtime_result.text,
                audio=AudioChunk(data=b"", format="pcm"),
                stt_provider=transcription.provider,
                stt_confidence=transcription.confidence,
                runtime_provider=runtime_result.provider_name,
                runtime_model=runtime_result.model_name,
                tts_provider=getattr(
                    self._tts_provider, "provider_name", "unknown"
                ),
                tts_voice_id=None,
                content_type="audio/pcm",
                audio_packets_streamed=frames_sent,
            )
        try:
            synthesis = await asyncio.wait_for(
                self._tts_provider.synthesize(
                    text=runtime_result.text,
                    voice_id=session.voice_id,
                    language=session.language,
                    output_format=session.output_audio_format,
                ),
                timeout=self._turn_settings.tts_timeout,
            )
        except TimeoutError as exc:
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
                timeout=True,
                error=str(type(exc).__name__),
                message=f"turn_failed stage=tts error={type(exc).__name__} timeout=True",
            )
            return await self._fallback_turn(
                session,
                text=_RUNTIME_FALLBACK_MESSAGE,
                transcript=transcription.text,
                request_id=request_id,
                error_code=_TTS_ERROR_CODE,
            )
        except Exception as exc:
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
                error=str(type(exc).__name__),
                message=(
                    f"turn_failed stage=tts error={type(exc).__name__} "
                    f"detail={exc}"
                ),
            )
            return await self._fallback_turn(
                session,
                text=_RUNTIME_FALLBACK_MESSAGE,
                transcript=transcription.text,
                request_id=request_id,
                error_code=_TTS_ERROR_CODE,
            )
        synth_done = time.monotonic()
        tts_elapsed_ms = int((synth_done - runtime_done) * 1000)
        turn_elapsed_ms = int((synth_done - turn_start) * 1000)
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
            tts_elapsed_ms=tts_elapsed_ms,
        )
        log_voice_event(
            self._logger,
            "turn_completed",
            tenant_id=tenant_id,
            agent_id=session.agent_id,
            session_id=session.session_id,
            conversation_id=session.conversation_id,
            request_id=request_id,
            stt_elapsed_ms=stt_elapsed_ms,
            runtime_elapsed_ms=runtime_elapsed_ms,
            tts_elapsed_ms=tts_elapsed_ms,
            turn_elapsed_ms=turn_elapsed_ms,
            tool_iterations=tool_iterations,
            response_chars=len(runtime_result.text),
            audio_bytes=len(synthesis.audio.data),
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
            audio_packets_streamed=0,
        )

    async def _run_streaming_turn(
        self,
        *,
        session: VoiceSession,
        tenant_id: str,
        transcription: STTResult,
        audio_sink: Callable[[AudioChunk], Awaitable[None]],
        request_id: str | None,
        turn_start: float,
        stt_done: float,
        stt_elapsed_ms: int,
    ) -> VoiceTurnResult:
        """Run one turn with LLM sentences flowing into TTS as they arrive.

        The runtime stream is consumed sentence by sentence; each completed
        sentence starts TTS immediately while the model keeps generating, so
        first audio no longer waits for the complete response. Bounds come
        from the provider HTTP timeouts plus the outer turn deadline — no
        stage here can hang silently. Failures before any speech fall back to
        a spoken message; failures after speech keep the partial playout and
        return, never failing the call.
        """
        from voice_service.telephony.provider import AudioOutputInterrupted

        runtime_started = time.monotonic()
        log_voice_event(
            self._logger,
            "RUNTIME_START",
            tenant_id=tenant_id,
            agent_id=session.agent_id,
            session_id=session.session_id,
            conversation_id=session.conversation_id,
            request_id=request_id,
            message="RUNTIME_START",
        )
        buffer = ""
        sentences = 0
        total_frames = 0
        total_bytes = 0
        total_chunks = 0
        first_audio_ms: int | None = None
        runtime_result: Any = None
        tts_started_logged = False

        async def _speak(sentence: str) -> None:
            nonlocal sentences, total_frames, total_bytes, total_chunks
            nonlocal first_audio_ms, tts_started_logged
            if not tts_started_logged:
                tts_started_logged = True
                log_voice_event(
                    self._logger,
                    "tts_started",
                    tenant_id=tenant_id,
                    agent_id=session.agent_id,
                    session_id=session.session_id,
                    conversation_id=session.conversation_id,
                    request_id=request_id,
                    output_format=session.output_audio_format,
                    text_chars=len(sentence),
                    streamed_sentences=True,
                )
            sentence_start = time.monotonic()
            stats = await self._stream_tts_to_sink(
                session=session,
                text=sentence,
                audio_sink=audio_sink,
                request_id=request_id,
                tts_start=sentence_start,
            )
            if not stats["completed"] and stats["frames"] == 0:
                raise RuntimeError(
                    str(stats.get("error") or "sentence TTS failed")
                )
            total_frames += int(stats["frames"])
            total_bytes += int(stats["bytes"])
            total_chunks += int(stats["chunks"])
            if first_audio_ms is None and stats["first_chunk_ms"] is not None:
                first_audio_ms = int(stats["first_chunk_ms"])
            sentences += 1
            log_voice_event(
                self._logger,
                "tts_sentence_started",
                tenant_id=tenant_id,
                agent_id=session.agent_id,
                session_id=session.session_id,
                conversation_id=session.conversation_id,
                request_id=request_id,
                sentence_index=sentences,
                text_chars=len(sentence),
            )

        stream = self._agent_runtime.respond_stream(
            tenant_id=tenant_id,
            agent_id=session.agent_id,
            conversation_id=session.conversation_id,
            message=transcription.text,
        )
        try:
            async for chunk in stream:
                # Support both voice-service RuntimeTextChunk (text_delta, done, result)
                # and agent-service RuntimeStreamEvent (type, delta, result)
                text_delta = getattr(chunk, "text_delta", None)
                if text_delta is None:
                    text_delta = getattr(chunk, "delta", None)
                if text_delta:
                    buffer += text_delta
                    while True:
                        sentence, buffer = split_first_sentence(buffer)
                        if sentence is None:
                            break
                        await _speak(sentence)
                    if len(buffer) > 300 and buffer.strip():
                        await _speak(buffer.strip())
                        buffer = ""
                # Detect completion: voice-service uses chunk.done, agent-service uses chunk.type == "done"
                chunk_done = getattr(chunk, "done", False)
                if not chunk_done:
                    chunk_type = getattr(chunk, "type", None)
                    if chunk_type == "done":
                        chunk_done = True
                if chunk_done:
                    chunk_result = getattr(chunk, "result", None)
                    if chunk_result is not None:
                        runtime_result = chunk_result
                    break
        except asyncio.CancelledError:
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                try:
                    await aclose()
                except Exception:
                    pass
            raise
        except AudioOutputInterrupted:
            return await self._partial_stream_result(
                session=session,
                tenant_id=tenant_id,
                transcription=transcription,
                request_id=request_id,
                turn_start=turn_start,
                stt_done=stt_done,
                stt_elapsed_ms=stt_elapsed_ms,
                runtime_result=runtime_result,
                total_frames=total_frames,
                total_bytes=total_bytes,
                sentences=sentences,
                first_audio_ms=first_audio_ms,
                error="AudioOutputInterrupted",
            )
        except Exception as exc:
            if total_frames > 0:
                return await self._partial_stream_result(
                    session=session,
                    tenant_id=tenant_id,
                    transcription=transcription,
                    request_id=request_id,
                    turn_start=turn_start,
                    stt_done=stt_done,
                    stt_elapsed_ms=stt_elapsed_ms,
                    runtime_result=runtime_result,
                    total_frames=total_frames,
                    total_bytes=total_bytes,
                    sentences=sentences,
                    first_audio_ms=first_audio_ms,
                    error=str(type(exc).__name__),
                )
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
                error=str(type(exc).__name__),
                message=f"turn_failed stage=runtime error={type(exc).__name__}",
            )
            return await self._fallback_turn(
                session,
                text=_RUNTIME_FALLBACK_MESSAGE,
                transcript=transcription.text,
                request_id=request_id,
                error_code=_RUNTIME_ERROR_CODE,
            )
        finally:
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                try:
                    await aclose()
                except Exception:
                    pass
        remainder = buffer.strip()
        if remainder and runtime_result is not None:
            await _speak(remainder)
        if runtime_result is None or total_frames == 0:
            return await self._fallback_turn(
                session,
                text=_RUNTIME_FALLBACK_MESSAGE,
                transcript=transcription.text,
                request_id=request_id,
                error_code=_RUNTIME_ERROR_CODE,
            )
        runtime_done = time.monotonic()
        runtime_elapsed_ms = int((runtime_done - stt_done) * 1000)
        tool_iterations = int(
            getattr(runtime_result, "tool_iterations", 0) or 0
        )
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
            runtime_elapsed_ms=runtime_elapsed_ms,
        )
        synth_done = time.monotonic()
        tts_elapsed_ms = int((synth_done - runtime_started) * 1000)
        turn_elapsed_ms = int((synth_done - turn_start) * 1000)
        log_voice_event(
            self._logger,
            "synthesis_completed",
            tenant_id=tenant_id,
            agent_id=session.agent_id,
            session_id=session.session_id,
            conversation_id=session.conversation_id,
            request_id=request_id,
            provider=getattr(self._tts_provider, "provider_name", "unknown"),
            tts_elapsed_ms=tts_elapsed_ms,
            streamed=True,
        )
        log_voice_event(
            self._logger,
            "turn_completed",
            tenant_id=tenant_id,
            agent_id=session.agent_id,
            session_id=session.session_id,
            conversation_id=session.conversation_id,
            request_id=request_id,
            stt_elapsed_ms=stt_elapsed_ms,
            runtime_elapsed_ms=runtime_elapsed_ms,
            tts_elapsed_ms=tts_elapsed_ms,
            turn_elapsed_ms=turn_elapsed_ms,
            tool_iterations=tool_iterations,
            response_chars=len(runtime_result.text),
            audio_bytes=total_bytes,
            audio_packets_streamed=total_frames,
            tts_sentences=sentences,
            tts_first_audio_ms=first_audio_ms,
            streamed=True,
        )
        await self._mark(session, "active")
        return VoiceTurnResult(
            session_id=session.session_id,
            tenant_id=session.tenant_id,
            agent_id=session.agent_id,
            conversation_id=session.conversation_id,
            transcript=transcription.text,
            response_text=runtime_result.text,
            audio=AudioChunk(data=b"", format="pcm"),
            stt_provider=transcription.provider,
            stt_confidence=transcription.confidence,
            runtime_provider=runtime_result.provider_name,
            runtime_model=runtime_result.model_name,
            tts_provider=getattr(self._tts_provider, "provider_name", "unknown"),
            tts_voice_id=None,
            content_type="audio/pcm",
            audio_packets_streamed=total_frames,
            tts_sentences=sentences,
        )

    async def _partial_stream_result(
        self,
        *,
        session: VoiceSession,
        tenant_id: str,
        transcription: STTResult,
        request_id: str | None,
        turn_start: float,
        stt_done: float,
        stt_elapsed_ms: int,
        runtime_result: Any,
        total_frames: int,
        total_bytes: int,
        sentences: int,
        first_audio_ms: int | None,
        error: str,
    ) -> VoiceTurnResult:
        """Return a partial streamed turn after interruption or late failure."""
        log_voice_event(
            self._logger,
            "tts_stream_interrupted",
            tenant_id=tenant_id,
            agent_id=session.agent_id,
            session_id=session.session_id,
            conversation_id=session.conversation_id,
            request_id=request_id,
            frames_sent=total_frames,
            error=error,
        )
        runtime_elapsed_ms = int((time.monotonic() - stt_done) * 1000)
        log_voice_event(
            self._logger,
            "turn_completed",
            tenant_id=tenant_id,
            agent_id=session.agent_id,
            session_id=session.session_id,
            conversation_id=session.conversation_id,
            request_id=request_id,
            stt_elapsed_ms=stt_elapsed_ms,
            runtime_elapsed_ms=runtime_elapsed_ms,
            tts_elapsed_ms=runtime_elapsed_ms,
            turn_elapsed_ms=int((time.monotonic() - turn_start) * 1000),
            tool_iterations=int(getattr(runtime_result, "tool_iterations", 0) or 0)
            if runtime_result is not None
            else 0,
            response_chars=len(getattr(runtime_result, "text", "") or ""),
            audio_bytes=total_bytes,
            audio_packets_streamed=total_frames,
            tts_sentences=sentences,
            tts_first_audio_ms=first_audio_ms,
            streamed=True,
            interrupted=True,
        )
        await self._mark(session, "active")
        return VoiceTurnResult(
            session_id=session.session_id,
            tenant_id=session.tenant_id,
            agent_id=session.agent_id,
            conversation_id=session.conversation_id,
            transcript=transcription.text,
            response_text=getattr(runtime_result, "text", "") or "",
            audio=AudioChunk(data=b"", format="pcm"),
            stt_provider=transcription.provider,
            stt_confidence=transcription.confidence,
            runtime_provider=getattr(runtime_result, "provider_name", "unknown"),
            runtime_model=getattr(runtime_result, "model_name", "unknown"),
            tts_provider=getattr(self._tts_provider, "provider_name", "unknown"),
            tts_voice_id=None,
            content_type="audio/pcm",
            audio_packets_streamed=total_frames,
            tts_sentences=sentences,
        )

    async def _stream_tts_to_sink(
        self,
        *,
        session: VoiceSession,
        text: str,
        audio_sink: Callable[[AudioChunk], Awaitable[None]],
        request_id: str | None,
        tts_start: float,
    ) -> dict[str, object]:
        """Consume streaming TTS into 20 ms frames delivered to ``audio_sink``.

        Returns stage stats (frames/bytes/chunks/first-chunk/completed).
        Provider errors are captured as ``completed=False`` so the caller can
        fall back or keep partial playout; sink (RTP send) errors propagate so
        send failures surface through the classic path. Cancellation closes
        the provider stream and re-raises without leaking the task. Only the
        partial-frame remainder (<320 bytes) plus in-flight HTTP buffers are
        ever held — the sink's paced consumption backpressures the stream, so
        no unbounded queue can grow.
        """
        stats: dict[str, object] = {
            "frames": 0,
            "bytes": 0,
            "chunks": 0,
            "first_chunk_ms": None,
            "completed": False,
            "error": None,
        }
        buffer = PcmFrameAccumulator()
        log_voice_event(
            self._logger,
            "tts_stream_started",
            tenant_id=session.tenant_id,
            agent_id=session.agent_id,
            session_id=session.session_id,
            conversation_id=session.conversation_id,
            request_id=request_id,
            text_chars=len(text),
        )
        stream = self._tts_provider.synthesize_stream(
            text=text, voice_id=session.voice_id, language=session.language
        )
        try:
            async for fragment in stream:
                data = fragment.data
                if not data:
                    continue
                stats["chunks"] = int(stats["chunks"]) + 1
                stats["bytes"] = int(stats["bytes"]) + len(data)
                if stats["first_chunk_ms"] is None:
                    first_ms = int((time.monotonic() - tts_start) * 1000)
                    stats["first_chunk_ms"] = first_ms
                    log_voice_event(
                        self._logger,
                        "tts_first_audio_chunk",
                        tenant_id=session.tenant_id,
                        agent_id=session.agent_id,
                        session_id=session.session_id,
                        conversation_id=session.conversation_id,
                        request_id=request_id,
                        first_chunk_elapsed_ms=first_ms,
                        chunk_bytes=len(data),
                    )
                for frame in buffer.append(data):
                    try:
                        await audio_sink(frame)
                    except Exception:
                        stats["sink_error"] = True
                        raise
                    stats["frames"] = int(stats["frames"]) + 1
            final = buffer.flush()
            if final is not None:
                try:
                    await audio_sink(final)
                except Exception:
                    stats["sink_error"] = True
                    raise
                stats["frames"] = int(stats["frames"]) + 1
            stats["completed"] = True
        except asyncio.CancelledError:
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                try:
                    await aclose()
                except Exception:
                    pass
            raise
        except Exception as exc:
            # Deferred import: telephony.provider is owned by the layer above.
            from voice_service.telephony.provider import AudioOutputInterrupted

            if isinstance(exc, AudioOutputInterrupted):
                # Caller barge-in: partial playout stands; report interruption
                # with the frames already sent instead of raising.
                stats["completed"] = False
                stats["interrupted"] = True
            elif stats.get("sink_error"):
                raise
            else:
                stats["error"] = type(exc).__name__
        total_ms = int((time.monotonic() - tts_start) * 1000)
        log_voice_event(
            self._logger,
            "tts_audio_stream_completed",
            tenant_id=session.tenant_id,
            agent_id=session.agent_id,
            session_id=session.session_id,
            conversation_id=session.conversation_id,
            request_id=request_id,
            tts_total_elapsed_ms=total_ms,
            tts_stream_chunks=stats["chunks"],
            tts_audio_bytes=stats["bytes"],
            frames_sent=stats["frames"],
            completed=stats["completed"],
        )
        return stats

    async def _fallback_turn(
        self,
        session: VoiceSession,
        *,
        text: str,
        transcript: str,
        request_id: str | None,
        error_code: str,
    ) -> VoiceTurnResult:
        """Return a graceful spoken fallback instead of silence on provider failure.

        The session is marked active again so the caller can retry. If speech
        synthesis itself is unavailable, the turn returns empty audio (nothing
        to play) but the session stays active and the call continues — a dead
        TTS provider must never hang up a live call. The failure is logged
        loudly with the provider error so credentials can be fixed.
        """
        log_voice_event(
            self._logger,
            "tts_started",
            tenant_id=session.tenant_id,
            agent_id=session.agent_id,
            session_id=session.session_id,
            conversation_id=session.conversation_id,
            request_id=request_id,
            stage="fallback",
            output_format=session.output_audio_format,
            text_chars=len(text),
        )
        try:
            synthesis = await asyncio.wait_for(
                self._tts_provider.synthesize(
                    text=text,
                    voice_id=session.voice_id,
                    language=session.language,
                    output_format=session.output_audio_format,
                ),
                timeout=self._turn_settings.tts_timeout,
            )
        except Exception as tts_exc:
            log_voice_event(
                self._logger,
                "turn_failed",
                tenant_id=session.tenant_id,
                agent_id=session.agent_id,
                session_id=session.session_id,
                conversation_id=session.conversation_id,
                request_id=request_id,
                stage="fallback",
                error_code=_TTS_ERROR_CODE,
                error=str(type(tts_exc).__name__),
                message=(
                    f"turn_failed stage=fallback error={type(tts_exc).__name__} "
                    f"detail={tts_exc}"
                ),
            )
            await self._mark(session, "active")
            return VoiceTurnResult(
                session_id=session.session_id,
                tenant_id=session.tenant_id,
                agent_id=session.agent_id,
                conversation_id=session.conversation_id,
                transcript=transcript,
                response_text=text,
                audio=AudioChunk(data=b"", format="pcm"),
                stt_provider=getattr(self._stt_provider, "provider_name", "unknown"),
                runtime_provider="fallback",
                runtime_model="fallback",
                tts_provider=getattr(self._tts_provider, "provider_name", "unknown"),
                tts_voice_id=None,
                content_type="audio/pcm",
            )
        await self._mark(session, "active")
        log_voice_event(
            self._logger,
            "audio_synthesized",
            tenant_id=session.tenant_id,
            agent_id=session.agent_id,
            session_id=session.session_id,
            conversation_id=session.conversation_id,
            request_id=request_id,
            stage="fallback",
            provider=synthesis.provider,
            content_type=synthesis.content_type,
            fallback_error_code=error_code,
        )
        return VoiceTurnResult(
            session_id=session.session_id,
            tenant_id=session.tenant_id,
            agent_id=session.agent_id,
            conversation_id=session.conversation_id,
            transcript=transcript,
            response_text=text,
            audio=synthesis.audio,
            stt_provider=getattr(self._stt_provider, "provider_name", "unknown"),
            runtime_provider="fallback",
            runtime_model="fallback",
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

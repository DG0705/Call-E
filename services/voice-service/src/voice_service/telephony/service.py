"""Integration layer connecting telephony providers to the voice engine.

TelephonyService owns the telephony-specific lifecycle: it keeps call records
persisted, publishes normalized lifecycle events, and composes the voice
engine through the existing VoiceSessionManager interface.
"""

import logging
import uuid
from datetime import UTC, datetime

from call_e_shared.exceptions import PlatformError

from voice_service.audio import AudioChunk
from voice_service.session import VoiceSessionManager, VoiceTurnResult
from voice_service.telephony import events
from voice_service.telephony.models import TelephonyCall
from voice_service.telephony.observability import log_telephony_event
from voice_service.telephony.provider import TelephonyProvider
from voice_service.telephony.store import CallStore

_TELEPHONY_PROVIDER_ERROR = "telephony_provider_error"
_CALL_NOT_FOUND = "call_not_found"
_CALL_ENDED = "call_ended"
_CALL_FAILED = "call_failed"
_CALL_NOT_ANSWERED = "call_not_answered"
_VOICE_SESSION_MISSING = "voice_session_missing"
_CALL_PERSISTENCE_ERROR = "call_persistence_error"

_MAX_DRAIN_CHUNKS = 100


class TelephonyService:
    """Coordinate provider, persistence, events, and voice turns per call."""

    def __init__(
        self,
        *,
        provider: TelephonyProvider,
        call_store: CallStore,
        voice_manager: VoiceSessionManager,
        event_publisher: events.EventPublisher,
        logger: logging.Logger | None = None,
    ) -> None:
        self._provider = provider
        self._call_store = call_store
        self._voice_manager = voice_manager
        self._event_publisher = event_publisher
        self._logger = logger or logging.getLogger(events.TELEPHONY_EVENT_LOGGER)

    async def create_outbound_call(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        destination_number: str,
        caller_number: str | None = None,
        conversation_id: str | None = None,
        request_id: str | None = None,
    ) -> TelephonyCall:
        """Originate an outbound call and persist its ringing state."""
        conversation_id = conversation_id or uuid.uuid4().hex
        try:
            call = await self._provider.start_call(
                tenant_id=tenant_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                destination_number=destination_number,
                caller_number=caller_number,
                request_id=request_id,
            )
        except Exception as exc:
            raise PlatformError(
                code=_TELEPHONY_PROVIDER_ERROR,
                message="Telephony provider could not start the call.",
                status_code=502,
            ) from exc
        await self._persist_new_call(call, request_id=request_id)
        await self._emit(
            events.CALL_CREATED,
            call,
            request_id=request_id,
            direction=call.direction,
        )
        await self._emit(
            events.CALL_RINGING,
            call,
            request_id=request_id,
            direction=call.direction,
        )
        log_telephony_event(
            self._logger,
            "call_created",
            tenant_id=call.tenant_id,
            agent_id=call.agent_id,
            call_id=call.call_id,
            conversation_id=call.conversation_id,
            request_id=request_id,
        )
        log_telephony_event(
            self._logger,
            "call_ringing",
            tenant_id=call.tenant_id,
            agent_id=call.agent_id,
            call_id=call.call_id,
            conversation_id=call.conversation_id,
            request_id=request_id,
        )
        return call

    async def create_inbound_call(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        caller_number: str,
        destination_number: str,
        conversation_id: str | None = None,
        request_id: str | None = None,
    ) -> TelephonyCall:
        """Register an inbound call and persist its ringing state."""
        conversation_id = conversation_id or uuid.uuid4().hex
        try:
            call = await self._provider.accept_call(
                tenant_id=tenant_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                caller_number=caller_number,
                destination_number=destination_number,
                request_id=request_id,
            )
        except Exception as exc:
            raise PlatformError(
                code=_TELEPHONY_PROVIDER_ERROR,
                message="Telephony provider could not accept the call.",
                status_code=502,
            ) from exc
        await self._persist_new_call(call, request_id=request_id)
        await self._emit(
            events.CALL_CREATED,
            call,
            request_id=request_id,
            direction=call.direction,
        )
        await self._emit(
            events.CALL_RINGING,
            call,
            request_id=request_id,
            direction=call.direction,
        )
        log_telephony_event(
            self._logger,
            "call_created",
            tenant_id=call.tenant_id,
            agent_id=call.agent_id,
            call_id=call.call_id,
            conversation_id=call.conversation_id,
            request_id=request_id,
        )
        log_telephony_event(
            self._logger,
            "call_ringing",
            tenant_id=call.tenant_id,
            agent_id=call.agent_id,
            call_id=call.call_id,
            conversation_id=call.conversation_id,
            request_id=request_id,
        )
        return call

    async def answer_call(
        self,
        *,
        tenant_id: str,
        call_id: str,
        request_id: str | None = None,
    ) -> TelephonyCall:
        """Answer a ringing call and open its voice session."""
        call = await self._require_open_call(
            tenant_id=tenant_id, call_id=call_id, request_id=request_id
        )
        try:
            call = await self._provider.answer_call(call, request_id=request_id)
        except Exception as exc:
            await self._mark_failed(call, _TELEPHONY_PROVIDER_ERROR, request_id)
            raise PlatformError(
                code=_TELEPHONY_PROVIDER_ERROR,
                message="Telephony provider could not answer the call.",
                status_code=502,
            ) from exc
        await self._emit(
            events.CALL_ANSWERED,
            call,
            request_id=request_id,
        )
        log_telephony_event(
            self._logger,
            "call_answered",
            tenant_id=call.tenant_id,
            agent_id=call.agent_id,
            call_id=call.call_id,
            conversation_id=call.conversation_id,
            request_id=request_id,
        )
        try:
            session = await self._voice_manager.create_session(
                tenant_id=call.tenant_id,
                agent_id=call.agent_id,
                conversation_id=call.conversation_id,
                request_id=request_id,
            )
        except PlatformError:
            await self._mark_failed(call, "voice_session_unavailable", request_id)
            raise
        call.metadata["session_id"] = session.session_id
        call.updated_at = datetime.now(UTC)
        await self._call_store.save(call)
        await self._emit(
            events.CALL_STARTED,
            call,
            request_id=request_id,
            session_id=session.session_id,
        )
        log_telephony_event(
            self._logger,
            "call_started",
            tenant_id=call.tenant_id,
            agent_id=call.agent_id,
            call_id=call.call_id,
            conversation_id=call.conversation_id,
            session_id=session.session_id,
            request_id=request_id,
        )
        return call

    async def process_audio(
        self,
        *,
        tenant_id: str,
        call_id: str,
        audio: AudioChunk,
        request_id: str | None = None,
    ) -> VoiceTurnResult:
        """Run one phone utterance through the voice engine and send audio back."""
        call = await self._require_active_call(
            tenant_id=tenant_id, call_id=call_id, request_id=request_id
        )
        session_id = call.metadata.get("session_id")
        if not session_id:
            raise PlatformError(
                code=_VOICE_SESSION_MISSING,
                message="Call has no open voice session.",
                status_code=409,
            )
        log_telephony_event(
            self._logger,
            "media_started",
            tenant_id=call.tenant_id,
            agent_id=call.agent_id,
            call_id=call.call_id,
            conversation_id=call.conversation_id,
            session_id=str(session_id),
            request_id=request_id,
            input_format=audio.format,
        )
        try:
            result = await self._voice_manager.process_audio_input(
                tenant_id=call.tenant_id,
                session_id=str(session_id),
                audio=audio,
                request_id=request_id,
            )
        except Exception as exc:
            log_telephony_event(
                self._logger,
                "media_failed",
                tenant_id=call.tenant_id,
                agent_id=call.agent_id,
                call_id=call.call_id,
                conversation_id=call.conversation_id,
                session_id=str(session_id),
                request_id=request_id,
            )
            raise
        log_telephony_event(
            self._logger,
            "transcript_produced",
            tenant_id=call.tenant_id,
            agent_id=call.agent_id,
            call_id=call.call_id,
            conversation_id=call.conversation_id,
            session_id=str(session_id),
            request_id=request_id,
            transcript=result.transcript,
        )
        log_telephony_event(
            self._logger,
            "agent_response_produced",
            tenant_id=call.tenant_id,
            agent_id=call.agent_id,
            call_id=call.call_id,
            conversation_id=call.conversation_id,
            session_id=str(session_id),
            request_id=request_id,
        )
        try:
            await self._provider.send_audio(
                call, result.audio, request_id=request_id
            )
        except Exception as exc:
            raise PlatformError(
                code=_TELEPHONY_PROVIDER_ERROR,
                message="Telephony provider could not return audio.",
                status_code=502,
            ) from exc
        log_telephony_event(
            self._logger,
            "audio_returned",
            tenant_id=call.tenant_id,
            agent_id=call.agent_id,
            call_id=call.call_id,
            conversation_id=call.conversation_id,
            session_id=str(session_id),
            request_id=request_id,
            content_type=result.content_type,
        )
        return result

    async def drain_audio(
        self,
        *,
        tenant_id: str,
        call_id: str,
        request_id: str | None = None,
    ) -> list[VoiceTurnResult]:
        """Consume queued phone audio and return every completed voice turn."""
        results: list[VoiceTurnResult] = []
        for _ in range(_MAX_DRAIN_CHUNKS):
            call = await self._require_active_call(
                tenant_id=tenant_id, call_id=call_id, request_id=request_id
            )
            audio = await self._provider.receive_audio(call, request_id=request_id)
            if audio is None:
                break
            results.append(
                await self.process_audio(
                    tenant_id=tenant_id,
                    call_id=call_id,
                    audio=audio,
                    request_id=request_id,
                )
            )
        return results

    async def hangup(
        self,
        *,
        tenant_id: str,
        call_id: str,
        request_id: str | None = None,
    ) -> TelephonyCall:
        """Hang up an active call, ending its voice session and persisting state."""
        call = await self._require_open_call(
            tenant_id=tenant_id, call_id=call_id, request_id=request_id
        )
        try:
            call = await self._provider.hangup(call, request_id=request_id)
        except Exception as exc:
            await self._mark_failed(call, _TELEPHONY_PROVIDER_ERROR, request_id)
            raise PlatformError(
                code=_TELEPHONY_PROVIDER_ERROR,
                message="Telephony provider could not hang up the call.",
                status_code=502,
            ) from exc
        session_id = call.metadata.get("session_id")
        if session_id:
            try:
                await self._voice_manager.end_session(
                    tenant_id=call.tenant_id,
                    session_id=str(session_id),
                    request_id=request_id,
                )
            except PlatformError:
                self._logger.info(
                    "telephony_hangup_session_end_skipped",
                    extra={"call_id": call.call_id, "session_id": session_id},
                )
        await self._emit(
            events.CALL_ENDED,
            call,
            request_id=request_id,
        )
        await self._call_store.save(call)
        log_telephony_event(
            self._logger,
            "call_ended",
            tenant_id=call.tenant_id,
            agent_id=call.agent_id,
            call_id=call.call_id,
            conversation_id=call.conversation_id,
            session_id=str(session_id) if session_id else None,
            request_id=request_id,
        )
        return call

    async def get_call(self, *, tenant_id: str, call_id: str) -> TelephonyCall:
        """Return one tenant-scoped call record or fail with a not-found error."""
        call = await self._call_store.get(tenant_id=tenant_id, call_id=call_id)
        if call is None:
            raise PlatformError(
                code=_CALL_NOT_FOUND,
                message="Telephony call was not found.",
                status_code=404,
            )
        return call

    async def close(self) -> None:
        """Release provider resources during application shutdown."""
        close_provider = getattr(self._provider, "close", None)
        if close_provider is not None:
            await close_provider()

    async def _require_open_call(
        self, *, tenant_id: str, call_id: str, request_id: str | None = None
    ) -> TelephonyCall:
        call = await self._call_store.get(tenant_id=tenant_id, call_id=call_id)
        if call is None:
            raise PlatformError(
                code=_CALL_NOT_FOUND,
                message="Telephony call was not found.",
                status_code=404,
            )
        if call.status == "ended":
            raise PlatformError(
                code=_CALL_ENDED,
                message="Telephony call has ended.",
                status_code=409,
            )
        if call.status == "failed":
            raise PlatformError(
                code=_CALL_FAILED,
                message="Telephony call is in a failed state.",
                status_code=409,
            )
        return call

    async def _require_active_call(
        self, *, tenant_id: str, call_id: str, request_id: str | None = None
    ) -> TelephonyCall:
        call = await self._require_open_call(
            tenant_id=tenant_id, call_id=call_id, request_id=request_id
        )
        if call.status != "active":
            raise PlatformError(
                code=_CALL_NOT_ANSWERED,
                message="Telephony call is not answered and active.",
                status_code=409,
            )
        return call

    async def _persist_new_call(
        self, call: TelephonyCall, *, request_id: str | None
    ) -> None:
        try:
            await self._call_store.create(call)
        except Exception as exc:
            log_telephony_event(
                self._logger,
                "call_failed",
                tenant_id=getattr(call, "tenant_id", None),
                agent_id=getattr(call, "agent_id", None),
                call_id=getattr(call, "call_id", None),
                conversation_id=getattr(call, "conversation_id", None),
                request_id=request_id,
                error_code=_CALL_PERSISTENCE_ERROR,
            )
            raise PlatformError(
                code=_CALL_PERSISTENCE_ERROR,
                message="Telephony call record could not be persisted.",
                status_code=502,
            ) from exc

    async def _mark_failed(
        self, call: TelephonyCall, error_code: str, request_id: str | None
    ) -> None:
        call.status = "failed"
        call.error_code = error_code
        call.updated_at = datetime.now(UTC)
        try:
            await self._call_store.save(call)
        except Exception:
            self._logger.exception(
                "telephony_call_failure_persist_error",
                extra={"call_id": call.call_id, "error_code": error_code},
            )
        await self._emit(
            events.CALL_FAILED,
            call,
            request_id=request_id,
            error_code=error_code,
        )
        log_telephony_event(
            self._logger,
            "call_failed",
            tenant_id=call.tenant_id,
            agent_id=call.agent_id,
            call_id=call.call_id,
            conversation_id=call.conversation_id,
            request_id=request_id,
            error_code=error_code,
        )

    async def _emit(
        self,
        name: str,
        call: TelephonyCall,
        request_id: str | None = None,
        **details: object,
    ) -> None:
        event = events.TelephonyEvent(
            name=name,
            call_id=call.call_id,
            tenant_id=call.tenant_id,
            agent_id=call.agent_id,
            conversation_id=call.conversation_id,
            session_id=call.metadata.get("session_id"),
            request_id=request_id,
            metadata={**details},
        )
        try:
            await self._event_publisher.publish(event)
        except Exception:
            self._logger.exception(
                "telephony_event_publish_error", extra={"event": name}
            )

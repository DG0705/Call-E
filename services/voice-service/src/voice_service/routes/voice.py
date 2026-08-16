"""Development API for exercising the voice session lifecycle."""

import base64

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from call_e_shared.exceptions import PlatformError

from voice_service.audio import AudioChunk
from voice_service.models import AudioFormat, VoiceSession


router = APIRouter(tags=["voice"])


class CreateSessionRequest(BaseModel):
    """Input for opening a voice session for one agent conversation."""

    tenant_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    language: str = "en"
    input_audio_format: AudioFormat = "pcm"
    output_audio_format: AudioFormat = "pcm"
    voice_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class EndSessionRequest(BaseModel):
    """Input for closing an open voice session."""

    tenant_id: str = Field(min_length=1)


class TurnRequest(BaseModel):
    """One user utterance submitted to an open voice session."""

    tenant_id: str = Field(min_length=1)
    audio_base64: str = Field(min_length=1)
    audio_format: AudioFormat = "pcm"
    sample_rate: int = Field(default=8000, ge=1)
    channels: int = Field(default=1, ge=1)


class TurnResponse(BaseModel):
    """Stable API response for one completed voice turn."""

    session_id: str
    tenant_id: str
    agent_id: str
    conversation_id: str
    transcript: str
    response: str
    audio_format: AudioFormat
    audio_base64: str
    content_type: str
    stt_provider: str
    tts_provider: str
    request_id: str | None = None


@router.post(
    "/api/v1/voice/sessions",
    response_model=VoiceSession,
    response_model_by_alias=False,
)
async def create_session(request: Request, payload: CreateSessionRequest) -> VoiceSession:
    """Open one voice session after validating the tenant-scoped agent."""
    return await request.app.state.voice_session_manager.create_session(
        tenant_id=payload.tenant_id,
        agent_id=payload.agent_id,
        conversation_id=payload.conversation_id,
        language=payload.language,
        input_audio_format=payload.input_audio_format,
        output_audio_format=payload.output_audio_format,
        voice_id=payload.voice_id,
        request_id=getattr(request.state, "request_id", None),
        metadata=payload.metadata,
    )


@router.get(
    "/api/v1/voice/sessions/{session_id}",
    response_model=VoiceSession,
    response_model_by_alias=False,
)
async def get_session(
    request: Request, session_id: str, tenant_id: str = Query(min_length=1)
) -> VoiceSession:
    """Return the current lifecycle state of one voice session."""
    return await request.app.state.voice_session_manager.get_session(
        tenant_id=tenant_id, session_id=session_id
    )


@router.post(
    "/api/v1/voice/sessions/{session_id}/turn", response_model=TurnResponse
)
async def process_turn(
    request: Request, session_id: str, payload: TurnRequest
) -> TurnResponse:
    """Run one audio utterance through speech, agent, and synthesis."""
    try:
        audio = AudioChunk(
            data=base64.b64decode(payload.audio_base64, validate=True),
            format=payload.audio_format,
            sample_rate=payload.sample_rate,
            channels=payload.channels,
        )
    except Exception as exc:
        raise PlatformError(
            code="invalid_audio_payload",
            message="Audio payload is not valid base64.",
            status_code=400,
        ) from exc
    result = await request.app.state.voice_session_manager.process_audio_input(
        tenant_id=payload.tenant_id,
        session_id=session_id,
        audio=audio,
        request_id=getattr(request.state, "request_id", None),
    )
    return TurnResponse(
        session_id=result.session_id,
        tenant_id=result.tenant_id,
        agent_id=result.agent_id,
        conversation_id=result.conversation_id,
        transcript=result.transcript,
        response=result.response_text,
        audio_format=result.audio.format,
        audio_base64=base64.b64encode(result.audio.data).decode("ascii"),
        content_type=result.content_type,
        stt_provider=result.stt_provider,
        tts_provider=result.tts_provider,
        request_id=getattr(request.state, "request_id", None),
    )


@router.post(
    "/api/v1/voice/sessions/{session_id}/end",
    response_model=VoiceSession,
    response_model_by_alias=False,
)
async def end_session(
    request: Request, session_id: str, payload: EndSessionRequest
) -> VoiceSession:
    """End one voice session and persist its final lifecycle state."""
    return await request.app.state.voice_session_manager.end_session(
        tenant_id=payload.tenant_id,
        session_id=session_id,
        request_id=getattr(request.state, "request_id", None),
    )

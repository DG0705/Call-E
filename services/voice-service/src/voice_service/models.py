"""Tenant-scoped voice session persistence models."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


VOICE_SESSIONS_COLLECTION = "voice_sessions"

SessionStatus = Literal["created", "active", "processing", "ended", "failed"]
AudioFormat = Literal["pcm", "wav", "ulaw"]


class VoiceSession(BaseModel):
    """Provider-neutral lifecycle state for one real-time voice conversation."""

    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(alias="_id")
    tenant_id: str
    agent_id: str
    conversation_id: str
    status: SessionStatus = "created"
    language: str = "en"
    input_audio_format: AudioFormat = "pcm"
    output_audio_format: AudioFormat = "pcm"
    voice_id: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None

"""Provider-neutral text-to-speech interface and local test implementation."""

from typing import Any, Protocol

from pydantic import BaseModel, Field

from voice_service.audio import AudioChunk, audio_content_type, encode_wav
from voice_service.models import AudioFormat


class TTSResult(BaseModel):
    """Normalized synthesized speech returned by a text-to-speech provider."""

    audio: AudioChunk
    provider: str
    voice_id: str | None = None
    content_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class TTSProvider(Protocol):
    """Interface implemented by replaceable text-to-speech providers."""

    async def synthesize(
        self,
        *,
        text: str,
        voice_id: str | None = None,
        language: str = "en",
        output_format: AudioFormat = "pcm",
    ) -> TTSResult: ...


class MockTTSProvider:
    """Deterministic local provider for development and tests."""

    provider_name = "mock"
    voice_name = "mock-voice"

    def __init__(self) -> None:
        self.last_text: str | None = None

    async def synthesize(
        self,
        *,
        text: str,
        voice_id: str | None = None,
        language: str = "en",
        output_format: AudioFormat = "pcm",
    ) -> TTSResult:
        self.last_text = text
        payload = AudioChunk(data=text.encode(), format="pcm")
        chunk = (
            encode_wav(payload)
            if output_format == "wav"
            else payload.model_copy(update={"format": output_format})
        )
        return TTSResult(
            audio=chunk,
            provider=self.provider_name,
            voice_id=voice_id or self.voice_name,
            content_type=audio_content_type(chunk.format),
            metadata={"language": language},
        )

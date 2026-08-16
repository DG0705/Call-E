"""Provider-neutral speech-to-text interface and local test implementation."""

from typing import Any, Protocol

from pydantic import BaseModel, Field

from voice_service.audio import AudioChunk


class STTResult(BaseModel):
    """Normalized transcription returned by a speech-to-text provider."""

    text: str
    language: str = "en"
    confidence: float | None = None
    provider: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class STTProvider(Protocol):
    """Interface implemented by replaceable speech-to-text providers."""

    async def transcribe(self, audio: AudioChunk) -> STTResult: ...


class MockSTTProvider:
    """Deterministic local provider for development and tests."""

    provider_name = "mock"

    def __init__(
        self,
        *,
        default_transcript: str = "Mock transcription of customer audio.",
    ) -> None:
        self._default_transcript = default_transcript
        self.last_audio: AudioChunk | None = None
        self.calls = 0

    async def transcribe(self, audio: AudioChunk) -> STTResult:
        self.calls += 1
        self.last_audio = audio
        return STTResult(
            text=self._default_transcript,
            language="en",
            confidence=0.95,
            provider=self.provider_name,
            metadata={
                "format": audio.format,
                "sample_rate": audio.sample_rate,
                "channels": audio.channels,
            },
        )

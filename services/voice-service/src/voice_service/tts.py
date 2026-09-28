"""Provider-neutral text-to-speech interface and local test implementation."""

from collections.abc import AsyncIterator
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

    def synthesize_stream(
        self,
        *,
        text: str,
        voice_id: str | None = None,
        language: str = "en",
    ) -> AsyncIterator[AudioChunk]:
        """Yield raw PCM audio fragments incrementally as synthesis streams.

        Fragments are 8 kHz mono 16-bit little-endian PCM of arbitrary size;
        callers accumulate them into complete frames. The default
        implementation buffers one full synthesis and yields it once, so
        providers without true streaming keep working unchanged.
        """
        return self._buffered_stream(
            text=text, voice_id=voice_id, language=language
        )

    async def _buffered_stream(
        self,
        *,
        text: str,
        voice_id: str | None = None,
        language: str = "en",
    ) -> AsyncIterator[AudioChunk]:
        result = await self.synthesize(
            text=text, voice_id=voice_id, language=language, output_format="pcm"
        )
        yield result.audio


class MockTTSProvider:
    """Deterministic local provider for development and tests."""

    provider_name = "mock"
    voice_name = "mock-voice"

    def synthesize_stream(
        self,
        *,
        text: str,
        voice_id: str | None = None,
        language: str = "en",
    ) -> AsyncIterator[AudioChunk]:
        """Yield the deterministic payload in two fragments, then stop."""
        return self._mock_stream(text=text, voice_id=voice_id, language=language)

    async def _mock_stream(
        self,
        *,
        text: str,
        voice_id: str | None = None,
        language: str = "en",
    ) -> AsyncIterator[AudioChunk]:
        result = await self.synthesize(
            text=text, voice_id=voice_id, language=language, output_format="pcm"
        )
        data = result.audio.data
        midpoint = len(data) // 2
        yield result.audio.model_copy(update={"data": data[:midpoint]})
        yield result.audio.model_copy(update={"data": data[midpoint:]})

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

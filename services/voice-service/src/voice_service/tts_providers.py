"""Real production-capable text-to-speech providers.

Each provider implements the neutral :class:`voice_service.tts.TTSProvider`
boundary and owns any codec/format conversion required by its remote API, so
codec handling never spreads into the application.

Providers are configured entirely with environment variables and never log
their credentials.
"""

from typing import Any, Protocol

import httpx

from voice_service.audio import AudioChunk, encode_ulaw, encode_wav
from voice_service.models import AudioFormat
from voice_service.tts import TTSResult


class TTSClient(Protocol):
    """Small HTTP surface needed by text-to-speech providers."""

    async def post(
        self,
        url: str,
        *,
        json: dict[str, Any],
        params: dict[str, str],
        headers: dict[str, str],
    ) -> httpx.Response: ...


class ElevenLabsTTSProvider:
    """Text-to-speech using the ElevenLabs REST API.

    Configuration (all from environment variables):
    - ``ELEVENLABS_API_KEY`` — required API key.
    - ``ELEVENLABS_VOICE_ID`` — default voice id (example ``pNInz6obpgDQGcFmaJgB``).
    - ``ELEVENLABS_MODEL_ID`` — model id (default ``eleven_multilingual_v2``).
    """

    provider_name = "elevenlabs"

    _BASE_URL = "https://api.elevenlabs.io/v1/text-to-speech"

    def __init__(
        self,
        *,
        api_key: str,
        voice_id: str | None = None,
        model_id: str = "eleven_multilingual_v2",
        timeout_seconds: float = 30.0,
        client: TTSClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError(
                "ELEVENLABS_API_KEY is required to configure ElevenLabsTTSProvider."
            )
        self._api_key = api_key
        self._voice_id = voice_id
        self._model_id = model_id
        self._timeout = timeout_seconds
        self._client = client or _HttpTTSClient(timeout_seconds)

    async def synthesize(
        self,
        *,
        text: str,
        voice_id: str | None = None,
        language: str = "en",
        output_format: AudioFormat = "pcm",
    ) -> TTSResult:
        """Synthesize the assistant text and convert to the internal format.

        ElevenLabs always returns raw 8 kHz PCM here; the provider wraps it in
        the requested internal encoding (pcm, wav, or ulaw) so telephony
        adapters keep receiving the normalized audio representation.
        """
        voice = voice_id or self._voice_id
        if not voice:
            raise TTSProviderError(
                "No ElevenLabs voice id configured. Set ELEVENLABS_VOICE_ID or "
                "supply voice_id."
            )
        try:
            response = await self._client.post(
                f"{self._BASE_URL}/{voice}",
                json={
                    "text": text,
                    "model_id": self._model_id,
                    "language_code": language,
                },
                params={
                    "output_format": "pcm_8000",
                    "optimize_streaming_latency": "0",
                },
                headers={
                    "xi-api-key": self._api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/pcm",
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise TTSProviderError(
                f"ElevenLabs synthesis failed with status {exc.response.status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise TTSProviderError("ElevenLabs synthesis request failed.") from exc

        pcm = AudioChunk(data=response.content, format="pcm", sample_rate=8000)
        if output_format == "pcm":
            audio = pcm
        elif output_format == "wav":
            audio = encode_wav(pcm)
        elif output_format == "ulaw":
            audio = AudioChunk(
                data=encode_ulaw(pcm),
                format="ulaw",
                sample_rate=pcm.sample_rate,
                channels=pcm.channels,
                sample_width=1,
                metadata={"ulaw_encoded_from": "pcm"},
            )
        else:
            raise TTSProviderError(f"Unsupported output format '{output_format}'.")

        from voice_service.audio import audio_content_type

        return TTSResult(
            audio=audio,
            provider=self.provider_name,
            voice_id=voice,
            content_type=audio_content_type(audio.format),
            metadata={
                "model_id": self._model_id,
                "language": language,
                "synthesized_bytes": len(response.content),
            },
        )

    async def close(self) -> None:
        """Release the HTTP client when this provider owns it."""
        close_client = getattr(self._client, "close", None)
        if close_client is not None:
            await close_client()


class TTSProviderError(Exception):
    """Raised when a real text-to-speech provider cannot complete a request."""


class _HttpTTSClient:
    """Default HTTP client shared by the real TTS providers."""

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def post(
        self,
        url: str,
        *,
        json: dict[str, Any],
        params: dict[str, str],
        headers: dict[str, str],
    ) -> httpx.Response:
        return await self._client.post(
            url, json=json, params=params, headers=headers
        )

    async def close(self) -> None:
        await self._client.aclose()

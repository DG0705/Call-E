"""Real production-capable speech-to-text providers.

Each provider implements the neutral :class:`voice_service.stt.STTPProvider`
boundary and owns any codec/format conversion required by its remote API, so
codec handling never spreads into the application.

Providers are configured entirely with environment variables and never log
their credentials.
"""

from typing import Any, Protocol

import httpx

from voice_service.audio import AudioChunk
from voice_service.stt import STTResult, STTProvider


class STTClient(Protocol):
    """Small HTTP surface needed by speech-to-text providers."""

    async def post(
        self, url: str, *, content: Any, params: dict[str, str], headers: dict[str, str]
    ) -> httpx.Response: ...


class DeepgramSTTProvider:
    """Speech-to-text using the Deepgram streaming/on-demand REST API.

    Configuration (all from environment variables):
    - ``DEEPGRAM_API_KEY`` — required API key.
    - ``DEEPGRAM_MODEL`` — model identifier (default ``nova-2``).
    - ``DEEPGRAM_LANGUAGE`` — language tag used when no explicit override is
      supplied (default ``en``).
    """

    provider_name = "deepgram"

    _BASE_URL = "https://api.deepgram.com/v1/listen"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "nova-2",
        default_language: str = "en",
        timeout_seconds: float = 30.0,
        client: STTClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("DEEPGRAM_API_KEY is required to configure DeepgramSTTProvider.")
        self._api_key = api_key
        self._model = model
        self._default_language = default_language
        self._timeout = timeout_seconds
        self._client = client or _HttpSTTClient(timeout_seconds)

    async def transcribe(self, audio: AudioChunk) -> STTResult:
        """Send internal PCM audio to Deepgram and normalize the transcript."""
        encoding, sample_rate, content_type = _stt_payload(audio)
        language = self._default_language
        params = {
            "model": self._model,
            "encoding": encoding,
            "sample_rate": str(sample_rate),
            "language": language,
            "punctuate": "true",
            "smart_format": "true",
        }
        try:
            response = await self._client.post(
                self._BASE_URL,
                content=audio.data,
                params=params,
                headers={
                    "Authorization": f"Token {self._api_key}",
                    "Content-Type": content_type,
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise STTProviderError(
                f"Deepgram transcription failed with status {exc.response.status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise STTProviderError("Deepgram transcription request failed.") from exc

        payload = _as_dict(response.json())
        result = payload.get("results", {})
        channels = result.get("channels") or []
        words: list[dict[str, Any]] = []
        if channels:
            alternatives = channels[0].get("alternatives") or []
            if alternatives:
                words = alternatives[0].get("words") or []
        text = " ".join(
            str(word.get("word", "")) for word in words if word.get("word")
        ).strip()
        confidence = _aggregate_confidence(words)

        return STTResult(
            text=text,
            language=language,
            confidence=confidence,
            provider=self.provider_name,
            metadata={
                "model": self._model,
                "format": audio.format,
                "sample_rate": audio.sample_rate,
                "channels": audio.channels,
                "input_bytes": len(audio.data),
            },
        )

    async def close(self) -> None:
        """Release the HTTP client when this provider owns it."""
        close_client = getattr(self._client, "close", None)
        if close_client is not None:
            await close_client()


class STTProviderError(Exception):
    """Raised when a real speech-to-text provider cannot complete a request."""


class _HttpSTTClient:
    """Default HTTP client shared by the real STT providers."""

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def post(
        self, url: str, *, content: Any, params: dict[str, str], headers: dict[str, str]
    ) -> httpx.Response:
        return await self._client.post(
            url, content=content, params=params, headers=headers
        )

    async def close(self) -> None:
        await self._client.aclose()


def _stt_payload(audio: AudioChunk) -> tuple[str, int, str]:
    """Describe the internal audio to the STT API with the required codec.

    The voice engine's internal representation is 16-bit PCM. If the chunk is
    already WAV we pass it through verbatim; otherwise we describe the raw
    little-endian linear PCM so the provider decodes it correctly.
    """
    if audio.format == "wav":
        return "", audio.sample_rate, "audio/wav"
    if audio.format == "ulaw":
        return "mulaw", audio.sample_rate, "audio/basic"
    return "slinear16", audio.sample_rate, "audio/pcm"


def _as_dict(payload: object) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


def _aggregate_confidence(words: list[dict[str, Any]]) -> float | None:
    """Average per-word confidence, or None when the provider omits it."""
    values = [word.get("confidence") for word in words if word.get("confidence") is not None]
    if not values:
        return None
    try:
        return float(sum(float(v) for v in values) / len(values))
    except (TypeError, ValueError):
        return None

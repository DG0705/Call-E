"""Tests for the real production-capable STT/TTS provider adapters.

These tests exercise the provider adapters against an in-memory HTTP transport
so they never depend on real paid APIs or the network (CI-safe).
"""

import asyncio

import httpx
import pytest

from voice_service.audio import AudioChunk, decode_wav, encode_ulaw
from voice_service.stt_providers import DeepgramSTTProvider, STTProviderError
from voice_service.tts_providers import ElevenLabsTTSProvider, TTSProviderError


def run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


def _fake_response(*, status: int = 200, json: dict[str, object] | None = None, content: bytes | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://example.invalid/")
    return httpx.Response(status, json=json, content=content, request=request)


class RecordingSTTClient:
    """Fake HTTP client capturing the request for Deepgram assertions."""

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.request_url: str | None = None
        self.request_params: dict[str, str] | None = None
        self.request_headers: dict[str, str] | None = None
        self.request_content: bytes | None = None

    async def post(
        self, url: str, *, content: object, params: dict[str, str], headers: dict[str, str]
    ) -> httpx.Response:
        self.request_url = url
        self.request_params = params
        self.request_headers = headers
        self.request_content = content if isinstance(content, bytes) else None  # type: ignore[assignment]
        return _fake_response(json=self._payload)


class FailingSTTClient:
    async def post(
        self, url: str, *, content: object, params: dict[str, str], headers: dict[str, str]
    ) -> httpx.Response:
        return _fake_response(status=401, json={"error": "unauthorized"})


class RecordingTTSClient:
    """Fake HTTP client capturing the request for ElevenLabs assertions."""

    def __init__(self, audio_bytes: bytes) -> None:
        self._audio_bytes = audio_bytes
        self.request_url: str | None = None
        self.request_json: dict[str, object] | None = None
        self.request_params: dict[str, str] | None = None
        self.request_headers: dict[str, str] | None = None

    async def post(
        self, url: str, *, json: dict[str, object], params: dict[str, str], headers: dict[str, str]
    ) -> httpx.Response:
        self.request_url = url
        self.request_json = json
        self.request_params = params
        self.request_headers = headers
        return _fake_response(content=self._audio_bytes)


class FailingTTSClient:
    async def post(
        self, url: str, *, json: dict[str, object], params: dict[str, str], headers: dict[str, str]
    ) -> httpx.Response:
        return _fake_response(status=401, json={"error": "unauthorized"})


# --- Deepgram STT ---


def test_deepgram_provider_transcribes_with_detailed_payload() -> None:
    client = RecordingSTTClient(
        {
            "results": {
                "channels": [
                    {
                        "alternatives": [
                            {
                                "words": [
                                    {"word": "I", "confidence": 0.99},
                                    {"word": "need", "confidence": 0.97},
                                    {"word": "ten", "confidence": 0.95},
                                ]
                            }
                        ]
                    }
                ]
            }
        }
    )
    provider = DeepgramSTTProvider(api_key="secret", client=client)  # type: ignore[arg-type]

    result = run(
        provider.transcribe(
            AudioChunk(data=b"\x00\x01" * 40, format="pcm", sample_rate=8000)
        )
    )

    assert result.provider == "deepgram"
    assert result.text == "I need ten"
    assert result.confidence == pytest.approx(0.97, abs=0.01)
    assert client.request_params is not None
    assert client.request_params["encoding"] == "linear16"
    assert client.request_params["sample_rate"] == "8000"
    assert client.request_params["language"] == "en"
    assert client.request_headers is not None
    assert client.request_headers["Authorization"] == "Token secret"


def test_deepgram_provider_handles_wav_input_passthrough() -> None:
    client = RecordingSTTClient(
        {"results": {"channels": [{"alternatives": [{"words": []}]}]}}
    )
    provider = DeepgramSTTProvider(api_key="secret", client=client)  # type: ignore[arg-type]

    result = run(provider.transcribe(AudioChunk(data=b"RIFF", format="wav")))

    assert client.request_params is not None
    assert client.request_params["encoding"] == ""
    assert client.request_headers is not None
    assert client.request_headers["Content-Type"] == "audio/wav"
    assert result.text == ""


def test_deepgram_provider_raises_clean_error_on_status_failure() -> None:
    provider = DeepgramSTTProvider(api_key="secret", client=FailingSTTClient())  # type: ignore[arg-type]

    with pytest.raises(STTProviderError):
        run(provider.transcribe(AudioChunk(data=b"audio", format="pcm")))


def test_deepgram_pcm_uses_linear16_encoding() -> None:
    """Regression test: Deepgram rejects `slinear16` with 400 Invalid query string.

    Raw 16-bit PCM must be described with Deepgram's `linear16` encoding
    value (verified against the live API); the Google-style `slinear16`
    value is rejected before any audio is processed.
    """
    from voice_service.stt_providers import _stt_payload

    encoding, sample_rate, content_type = _stt_payload(
        AudioChunk(data=b"\x00\x01" * 80, format="pcm", sample_rate=8000)
    )

    assert encoding == "linear16"
    assert encoding != "slinear16"
    assert sample_rate == 8000
    assert content_type == "audio/pcm"


def test_deepgram_provider_requires_api_key() -> None:
    with pytest.raises(ValueError):
        DeepgramSTTProvider(api_key="")


# --- ElevenLabs TTS ---


def test_elevenlabs_provider_synthesizes_pcm() -> None:
    pcm_data = (b"\x00\x01" * 160) + (b"\x00\x00" * 10)
    client = RecordingTTSClient(pcm_data)
    provider = ElevenLabsTTSProvider(
        api_key="secret", voice_id="voice-1", client=client  # type: ignore[arg-type]
    )

    result = run(
        provider.synthesize(
            text="Hello, thank you for calling Kaari Planters.",
            language="en",
            output_format="pcm",
        )
    )

    assert result.provider == "elevenlabs"
    assert result.audio.format == "pcm"
    assert result.audio.sample_rate == 8000
    assert result.audio.data == pcm_data
    assert result.voice_id == "voice-1"
    assert client.request_json is not None
    assert client.request_json["text"].startswith("Hello")
    assert client.request_params is not None
    assert client.request_params["output_format"] == "pcm_8000"
    assert client.request_headers is not None
    assert client.request_headers["xi-api-key"] == "secret"


def test_elevenlabs_provider_wraps_wav_output() -> None:
    client = RecordingTTSClient(b"\x00\x01" * 160)
    provider = ElevenLabsTTSProvider(
        api_key="secret", voice_id="voice-1", client=client  # type: ignore[arg-type]
    )

    result = run(
        provider.synthesize(text="Hi", output_format="wav")
    )

    assert result.audio.format == "wav"
    assert result.content_type == "audio/wav"
    decoded = decode_wav(result.audio)
    assert decoded.data == b"\x00\x01" * 160


def test_elevenlabs_provider_encodes_ulaw_output() -> None:
    client = RecordingTTSClient(b"\x00\x01" * 160)
    provider = ElevenLabsTTSProvider(
        api_key="secret", voice_id="voice-1", client=client  # type: ignore[arg-type]
    )

    result = run(provider.synthesize(text="Hi", output_format="ulaw"))

    assert result.audio.format == "ulaw"
    assert result.content_type == "audio/basic"
    assert result.audio.data == encode_ulaw(
        AudioChunk(data=b"\x00\x01" * 160, format="pcm")
    )


def test_elevenlabs_provider_requires_voice_when_not_configured() -> None:
    client = RecordingTTSClient(b"")
    provider = ElevenLabsTTSProvider(
        api_key="secret", voice_id=None, client=client  # type: ignore[arg-type]
    )

    with pytest.raises(TTSProviderError):
        run(provider.synthesize(text="Hi"))

    configured = ElevenLabsTTSProvider(
        api_key="secret", voice_id="v1", client=client  # type: ignore[arg-type]
    )
    assert run(configured.synthesize(text="Hi", output_format="pcm")).voice_id == "v1"


def test_elevenlabs_provider_raises_clean_error_on_status_failure() -> None:
    provider = ElevenLabsTTSProvider(
        api_key="secret", voice_id="voice-1", client=FailingTTSClient()  # type: ignore[arg-type]
    )

    with pytest.raises(TTSProviderError):
        run(provider.synthesize(text="Hi"))


def test_elevenlabs_provider_requires_api_key() -> None:
    with pytest.raises(ValueError):
        ElevenLabsTTSProvider(api_key="")

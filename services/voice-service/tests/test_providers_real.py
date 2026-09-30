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


class GarbageBodySTTClient:
    """Fake client answering 200 with a non-JSON body (overloaded proxy)."""

    async def post(
        self, url: str, *, content: object, params: dict[str, str], headers: dict[str, str]
    ) -> httpx.Response:
        request = httpx.Request("POST", "https://example.invalid/")
        return httpx.Response(200, content=b"<html>busy</html>", request=request)


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


class _GuardedStreamResponse:
    """Fake streaming HTTP response that forbids full-response buffering."""

    def __init__(
        self,
        blobs: list[bytes],
        *,
        status: int = 200,
        fail_after: int | None = None,
    ) -> None:
        self._blobs = blobs
        self._status = status
        self._fail_after = fail_after
        self.pulls = 0

    @property
    def content(self) -> bytes:
        raise AssertionError("streaming path must not buffer response.content")

    def raise_for_status(self) -> None:
        if self._status != 200:
            request = httpx.Request("POST", "https://example.invalid/")
            raise httpx.HTTPStatusError(
                "stream failed",
                request=request,
                response=httpx.Response(self._status, request=request),
            )

    async def aiter_bytes(self) -> object:
        for index, blob in enumerate(self._blobs):
            self.pulls += 1
            if self._fail_after is not None and index >= self._fail_after:
                raise httpx.HTTPError("stream interrupted")
            yield blob


class StreamingTTSClient:
    """Fake HTTP client serving ElevenLabs audio as a controlled stream."""

    def __init__(
        self,
        blobs: list[bytes],
        *,
        status: int = 200,
        fail_after: int | None = None,
    ) -> None:
        self._blobs = blobs
        self._status = status
        self._fail_after = fail_after
        self.request_url: str | None = None
        self.request_json: dict[str, object] | None = None
        self.request_params: dict[str, str] | None = None
        self.request_headers: dict[str, str] | None = None
        self.closed = False
        self.response: _GuardedStreamResponse | None = None

    def stream(
        self, method: str, url: str, *, json: dict[str, object], params: dict[str, str], headers: dict[str, str]
    ) -> object:
        assert method == "POST"
        self.request_url = url
        self.request_json = json
        self.request_params = params
        self.request_headers = headers
        client = self

        class _Context:
            async def __aenter__(self) -> _GuardedStreamResponse:
                client.response = _GuardedStreamResponse(
                    client._blobs,
                    status=client._status,
                    fail_after=client._fail_after,
                )
                return client.response

            async def __aexit__(self, *args: object) -> bool:
                client.closed = True
                return False

        return _Context()


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


def test_deepgram_non_json_body_becomes_provider_error() -> None:
    from voice_service.stt_providers import STTProviderError

    provider = DeepgramSTTProvider(api_key="secret", client=GarbageBodySTTClient())  # type: ignore[arg-type]

    with pytest.raises(STTProviderError):
        run(
            provider.transcribe(
                AudioChunk(data=b"\x00\x01" * 80, format="pcm", sample_rate=8000)
            )
        )


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


# --- ElevenLabs streaming TTS ---


def test_elevenlabs_stream_yields_first_chunk_before_full_response() -> None:
    blobs = [b"\x00\x01" * 50, b"\x02\x03" * 250, b"\x04\x05" * 200]
    client = StreamingTTSClient(blobs)
    provider = ElevenLabsTTSProvider(
        api_key="secret", voice_id="voice-1", client=client  # type: ignore[arg-type]
    )

    async def main() -> tuple[list[AudioChunk], int]:
        stream = provider.synthesize_stream(text="Hello there")
        first = await stream.__anext__()
        pulls_after_first = client.response.pulls if client.response else -1
        rest = [chunk async for chunk in stream]
        return [first, *rest], pulls_after_first

    chunks, pulls_after_first = run(main())  # type: ignore[misc]

    assert pulls_after_first == 1
    assert [chunk.data for chunk in chunks] == blobs
    assert all(chunk.format == "pcm" and chunk.sample_rate == 8000 for chunk in chunks)
    assert b"".join(chunk.data for chunk in chunks) == b"".join(blobs)


def test_elevenlabs_stream_uses_streaming_request_parameters() -> None:
    client = StreamingTTSClient([b"\x00\x01" * 160])
    provider = ElevenLabsTTSProvider(
        api_key="secret", voice_id="voice-1", client=client  # type: ignore[arg-type]
    )

    async def main() -> list[AudioChunk]:
        return [chunk async for chunk in provider.synthesize_stream(text="Hi")]

    chunks = run(main())  # type: ignore[misc]

    assert len(chunks) == 1
    assert client.request_url is not None and client.request_url.endswith("/voice-1")
    assert client.request_json is not None and client.request_json["text"] == "Hi"
    assert client.request_params is not None
    assert client.request_params["output_format"] == "pcm_8000"
    assert client.request_params["optimize_streaming_latency"] == "4"
    assert client.request_headers is not None
    assert client.request_headers["xi-api-key"] == "secret"
    assert client.closed is True


def test_elevenlabs_stream_skips_empty_blobs() -> None:
    client = StreamingTTSClient([b"", b"\x00\x01" * 160, b""])
    provider = ElevenLabsTTSProvider(
        api_key="secret", voice_id="voice-1", client=client  # type: ignore[arg-type]
    )

    async def main() -> list[AudioChunk]:
        return [chunk async for chunk in provider.synthesize_stream(text="Hi")]

    chunks = run(main())  # type: ignore[misc]

    assert [chunk.data for chunk in chunks] == [b"\x00\x01" * 160]


def test_elevenlabs_stream_raises_before_first_audio_on_status_failure() -> None:
    client = StreamingTTSClient([], status=429)
    provider = ElevenLabsTTSProvider(
        api_key="secret", voice_id="voice-1", client=client  # type: ignore[arg-type]
    )

    async def main() -> list[AudioChunk]:
        return [chunk async for chunk in provider.synthesize_stream(text="Hi")]

    with pytest.raises(TTSProviderError):
        run(main())


def test_elevenlabs_stream_raises_after_audio_started() -> None:
    blobs = [b"\x00\x01" * 160, b"\x02\x03" * 160, b"\x04\x05" * 160]
    client = StreamingTTSClient(blobs, fail_after=1)
    provider = ElevenLabsTTSProvider(
        api_key="secret", voice_id="voice-1", client=client  # type: ignore[arg-type]
    )

    async def main() -> list[AudioChunk]:
        received: list[AudioChunk] = []
        with pytest.raises(TTSProviderError):
            async for chunk in provider.synthesize_stream(text="Hi"):
                received.append(chunk)
        return received

    received = run(main())  # type: ignore[misc]

    assert [chunk.data for chunk in received] == blobs[:1]


def test_elevenlabs_stream_requires_voice() -> None:
    client = StreamingTTSClient([b"\x00\x01" * 10])
    provider = ElevenLabsTTSProvider(
        api_key="secret", voice_id=None, client=client  # type: ignore[arg-type]
    )

    async def main() -> list[AudioChunk]:
        return [chunk async for chunk in provider.synthesize_stream(text="Hi")]

    with pytest.raises(TTSProviderError):
        run(main())
    assert client.request_url is None

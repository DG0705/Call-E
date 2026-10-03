"""Tests for best-effort speech-provider startup verification."""

import asyncio

import httpx

from voice_service.diagnostics import verify_elevenlabs


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_rejected_key_logs_error_and_returns_false(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "unauthorized"})

    with caplog.at_level("ERROR"):
        ok = asyncio.run(
            verify_elevenlabs(
                api_key="bad-key", voice_id="v1", client=_client(handler)
            )
        )

    assert ok is False
    assert "TTS_PROVIDER_ERROR" in caplog.text
    assert "status=401" in caplog.text


def test_valid_key_and_voice_available(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"voices": [{"voice_id": "v1"}]})

    with caplog.at_level("INFO"):
        ok = asyncio.run(
            verify_elevenlabs(
                api_key="good-key", voice_id="v1", client=_client(handler)
            )
        )

    assert ok is True
    assert "TTS_PROVIDER_OK" in caplog.text


def test_valid_key_but_voice_not_owned(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"voices": [{"voice_id": "other"}]})

    with caplog.at_level("ERROR"):
        ok = asyncio.run(
            verify_elevenlabs(
                api_key="good-key", voice_id="v1", client=_client(handler)
            )
        )

    assert ok is False
    assert "TTS_VOICE_UNAVAILABLE" in caplog.text


def test_unreachable_api_is_non_fatal(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with caplog.at_level("WARNING"):
        ok = asyncio.run(
            verify_elevenlabs(
                api_key="good-key", voice_id="v1", client=_client(handler)
            )
        )

    assert ok is False
    assert "TTS_PROVIDER_UNREACHABLE" in caplog.text

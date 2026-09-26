"""Tests for smoke-test diagnostics (pure functions only, no network calls)."""

import importlib.util
import os

import httpx


def load_smoke_module():
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "..",
        "tools",
        "smoke_live_providers.py",
    )
    spec = importlib.util.spec_from_file_location(
        "smoke_live_providers", os.path.normpath(path)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def http_status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.invalid/")
    response = httpx.Response(status, json={"detail": "x"}, request=request)
    return httpx.HTTPStatusError("request failed", request=request, response=response)


def test_elevenlabs_402_classified_as_account_tier() -> None:
    smoke = load_smoke_module()

    assert smoke._elevenlabs_detail(http_status_error(402)) == (
        "ElevenLabs: configured voice is not available to the current "
        "account/API tier"
    )


def test_elevenlabs_non_402_reports_exception_type() -> None:
    smoke = load_smoke_module()

    assert smoke._elevenlabs_detail(http_status_error(401)) == "HTTPStatusError"
    assert smoke._elevenlabs_detail(RuntimeError("boom")) == "RuntimeError"


def test_http_status_code_walks_cause_chain() -> None:
    smoke = load_smoke_module()

    chained = RuntimeError("wrapper")
    chained.__cause__ = http_status_error(429)

    assert smoke._http_status_code(chained) == 429
    assert smoke._http_status_code(RuntimeError("plain")) is None

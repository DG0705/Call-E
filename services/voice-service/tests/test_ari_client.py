"""Tests for the ARI WebSocket event stream (fake sockets, no Asterisk)."""

import asyncio
import json

import pytest

from voice_service.telephony.asterisk.ari_client import AriEventStream
from voice_service.telephony.asterisk.ari_events import AriEvent


class FakeSocket:
    """Deterministic async WebSocket driven by canned messages."""

    def __init__(self, messages: list[str]) -> None:
        self._messages = messages
        self._drained = asyncio.Event()
        self.closed = False

    def __aiter__(self):  # type: ignore[no-untyped-def]
        async def _generate():
            for message in self._messages:
                yield message
            await self._drained.wait()

        return _generate()

    async def aclose(self) -> None:
        self.closed = True
        self._drained.set()


def stasis_start_message(channel_id: str = "chan-1") -> str:
    return json.dumps(
        {
            "type": "StasisStart",
            "application": "call-e",
            "channel": {
                "id": channel_id,
                "name": "PJSIP/dev-phone-00000001",
                "state": "Ring",
                "caller": {"number": "+15550001", "name": ""},
                "dialplan": {"context": "call-e-inbound", "exten": "1000"},
            },
            "args": ["1000"],
        }
    )


def test_stream_builds_websocket_url_without_logging_credentials() -> None:
    from voice_service.telephony.asterisk import ari_client

    url = ari_client._events_url(
        "http://asterisk:8088/", app="call-e", username="u", password="p"
    )

    assert url.startswith("ws://asterisk:8088/ari/events?")
    assert "app=call-e" in url
    assert "password" not in url


def test_stream_builds_wss_url_for_https_base() -> None:
    from voice_service.telephony.asterisk import ari_client

    url = ari_client._events_url("https://pbx.example:8089", app="call-e")

    assert url.startswith("wss://pbx.example:8089/ari/events?")


def test_stream_dispatches_events_until_stopped() -> None:
    received: list[AriEvent] = []
    socket = FakeSocket(
        [stasis_start_message(), "not-json", json.dumps({"nope": True})]
    )

    async def factory(url: str) -> FakeSocket:
        assert "api_key" not in url
        return socket

    stream = AriEventStream(
        base_url="http://asterisk:8088",
        socket_factory=factory,  # type: ignore[arg-type]
    )

    async def handled(event: AriEvent) -> None:
        received.append(event)
        await stream.stop()

    asyncio.run(stream.run(handled))

    assert [event.type for event in received] == ["StasisStart"]
    assert received[0].channel_id == "chan-1"
    assert socket.closed


def test_stream_handler_errors_do_not_kill_stream() -> None:
    received: list[AriEvent] = []
    socket = FakeSocket(
        [stasis_start_message("chan-1"), stasis_start_message("chan-2")]
    )

    async def factory(url: str) -> FakeSocket:
        return socket

    stream = AriEventStream(
        base_url="http://asterisk:8088",
        socket_factory=factory,  # type: ignore[arg-type]
    )
    calls = 0

    async def handled(event: AriEvent) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        received.append(event)
        await stream.stop()

    asyncio.run(stream.run(handled))

    assert calls == 2
    assert [event.channel_id for event in received] == ["chan-2"]


def test_stream_reconnects_after_factory_failure() -> None:
    attempts = 0

    async def factory(url: str) -> FakeSocket:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("ari down")
        return FakeSocket([])

    stream = AriEventStream(
        base_url="http://asterisk:8088",
        socket_factory=factory,  # type: ignore[arg-type]
    )

    async def main() -> None:
        task = asyncio.create_task(stream.run(_ignore))
        await asyncio.sleep(1.2)
        await stream.stop()
        await task

    async def _ignore(event: AriEvent) -> None:
        raise AssertionError("no events expected")

    asyncio.run(main())

    assert attempts >= 2


def test_stream_requires_websockets_package_for_default_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from voice_service.telephony.asterisk import ari_client

    real_import = __import__

    def fake_import(name: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if name == "websockets":
            raise ImportError("No module named 'websockets'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    async def main() -> None:
        with pytest.raises(ari_client.AriEventStreamError):
            await ari_client._default_socket_factory("ws://x/ari/events")

    asyncio.run(main())

"""ARI WebSocket event stream for the Call-E Stasis application.

Connects to ``ws(s)://host/ari/events?app=<app>`` so Asterisk pushes call
lifecycle events (``StasisStart``/``StasisEnd``/hangup/destroyed) to the voice
service. Authentication travels in the ``api_key`` query parameter per the ARI
contract; connection logs never include it.

The socket is created through an injectable factory so tests can drive the
stream with canned messages and no network.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol
from urllib.parse import quote, urlsplit, urlunsplit

from voice_service.telephony.asterisk.ari_events import AriEvent, parse_ari_event
from voice_service.telephony.observability import (
    TELEPHONY_EVENT_LOGGER,
    log_telephony_event,
)

ARI_APP_NAME = "call-e"

_RECONNECT_DELAYS = (1.0, 2.0, 5.0, 10.0, 30.0)


class AriSocket(Protocol):
    """Minimal async WebSocket surface used by the event stream."""

    def __aiter__(self) -> AsyncIterator[str]: ...
    async def aclose(self) -> None: ...


AriSocketFactory = Callable[[str], Awaitable[AriSocket]]


class AriEventStreamError(Exception):
    """Raised when the ARI event stream cannot (re)connect."""


class AriEventStream:
    """Maintain one ARI event subscription for an application name."""

    def __init__(
        self,
        *,
        base_url: str,
        app: str = ARI_APP_NAME,
        username: str | None = None,
        password: str | None = None,
        socket_factory: AriSocketFactory | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._events_url = _events_url(
            base_url, app=app, username=username, password=password
        )
        self._log_url = _events_url(base_url, app=app)
        self._app = app
        self._socket_factory = socket_factory or _default_socket_factory
        self._logger = logger or logging.getLogger(TELEPHONY_EVENT_LOGGER)
        self._stopping = False
        self._socket: AriSocket | None = None

    async def run(
        self, handler: Callable[[AriEvent], Awaitable[None]]
    ) -> None:
        """Connect and dispatch events until :meth:`stop` is called.

        Reconnects with capped backoff on transport failures. Malformed
        messages are logged and skipped; handler errors are logged and the
        stream continues so one bad call cannot kill every other call.
        """
        attempt = 0
        while not self._stopping:
            try:
                await self._pump(handler)
            except _StreamStopped:
                break
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._stopping:
                    break
                delay = _RECONNECT_DELAYS[min(attempt, len(_RECONNECT_DELAYS) - 1)]
                attempt += 1
                log_telephony_event(
                    self._logger,
                    "ari_stream_reconnecting",
                    request_id=None,
                    app=self._app,
                    ari_url=self._log_url,
                    error_type=type(exc).__name__,
                    retry_in_seconds=delay,
                )
                await asyncio.sleep(delay)
                continue
            attempt = 0

    async def stop(self) -> None:
        """Signal the stream loop to exit and close the socket."""
        self._stopping = True
        socket, self._socket = self._socket, None
        if socket is not None:
            try:
                await socket.aclose()
            except Exception:
                pass

    async def _pump(
        self, handler: Callable[[AriEvent], Awaitable[None]]
    ) -> None:
        log_telephony_event(
            self._logger, "ari_stream_connecting", request_id=None,
            app=self._app, ari_url=self._log_url,
        )
        socket = await self._socket_factory(self._events_url)
        if self._stopping:
            try:
                await socket.aclose()
            except Exception:
                pass
            raise _StreamStopped
        self._socket = socket
        log_telephony_event(
            self._logger, "ari_stream_connected", request_id=None,
            app=self._app, ari_url=self._log_url,
        )
        try:
            async for message in socket:
                if self._stopping:
                    break
                event = _parse_message(message)
                if event is None:
                    log_telephony_event(
                        self._logger, "ari_event_malformed", request_id=None,
                        app=self._app,
                    )
                    continue
                try:
                    await handler(event)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log_telephony_event(
                        self._logger, "ari_event_handler_failed", request_id=None,
                        app=self._app, event_type=event.type,
                        error_type=type(exc).__name__,
                    )
        finally:
            self._socket = None
            try:
                await socket.aclose()
            except Exception:
                pass
            log_telephony_event(
                self._logger, "ari_stream_disconnected", request_id=None,
                app=self._app, ari_url=self._log_url,
            )


class _StreamStopped(Exception):
    """Internal signal to exit the reconnect loop after stop()."""


def _events_url(
    base_url: str,
    *,
    app: str,
    username: str | None = None,
    password: str | None = None,
) -> str:
    """Build the ARI events WebSocket URL (http->ws, https->wss)."""
    parts = urlsplit(base_url.rstrip("/"))
    scheme = {"http": "ws", "https": "wss"}.get(parts.scheme, "ws")
    query = f"app={quote(app, safe='')}"
    if username:
        credential = username if not password else f"{username}:{password}"
        query += f"&api_key={quote(credential, safe='')}"
    return urlunsplit((scheme, parts.netloc, "/ari/events", query, ""))


def _parse_message(message: object) -> AriEvent | None:
    if not isinstance(message, (str, bytes)):
        return None
    try:
        payload: Any = json.loads(message)
    except (ValueError, TypeError):
        return None
    return parse_ari_event(payload)


async def _default_socket_factory(url: str) -> AriSocket:
    """Open a real ARI WebSocket with the optional websockets package."""
    try:
        import websockets
    except ImportError as exc:
        raise AriEventStreamError(
            "The 'websockets' package is required for the ARI event stream."
        ) from exc
    return await websockets.connect(url)

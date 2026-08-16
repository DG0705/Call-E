"""Asterisk transport boundary and HTTP/ARI foundation.

The transport is the Asterisk-specific communication surface. It maps onto ARI
(Asterisk REST Interface) in production; the HTTP transport below is a
documented foundation and never runs in the test suite.
"""

from typing import Any, Protocol

import httpx

from voice_service.audio import AudioChunk


class AsteriskTransportError(Exception):
    """Raised when an Asterisk transport operation fails."""


class AsteriskTransport(Protocol):
    """Asterisk-specific lifecycle and media operations."""

    async def originate(
        self,
        *,
        endpoint: str,
        context: str,
        extension: str,
        caller_id: str | None = None,
    ) -> str:
        """Originate an outbound call and return the ARI channel id."""
        ...

    async def accept_inbound(
        self, *, caller_number: str, destination_number: str
    ) -> str:
        """Accept the channel handed off for an inbound call."""
        ...

    async def answer(self, channel_id: str) -> None: ...

    async def hangup(self, channel_id: str) -> None: ...

    async def play_media(self, channel_id: str, media: bytes) -> None:
        """Stream encoded audio onto the channel toward the phone."""
        ...


class HttpAsteriskTransport:
    """HTTP foundation mapping telephony operations onto ARI REST calls."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str | None = None,
        password: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def originate(
        self,
        *,
        endpoint: str,
        context: str,
        extension: str,
        caller_id: str | None = None,
    ) -> str:
        params: dict[str, str] = {
            "endpoint": endpoint,
            "app": "call-e",
            "context": context,
            "extension": extension,
        }
        if caller_id:
            params["callerId"] = caller_id
        response = await self._client.post(
            f"{self._base_url}/ari/channels", params=params
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or "id" not in payload:
            raise AsteriskTransportError("ARI did not return a channel id.")
        return str(payload["id"])

    async def accept_inbound(
        self, *, caller_number: str, destination_number: str
    ) -> str:
        raise AsteriskTransportError(
            "Inbound channel handoff requires an ARI event stream; "
            "it is not available in this foundation."
        )

    async def answer(self, channel_id: str) -> None:
        response = await self._client.post(
            f"{self._base_url}/ari/channels/{channel_id}/answer"
        )
        response.raise_for_status()

    async def hangup(self, channel_id: str) -> None:
        response = await self._client.delete(
            f"{self._base_url}/ari/channels/{channel_id}"
        )
        response.raise_for_status()

    async def play_media(self, channel_id: str, media: bytes) -> None:
        raise AsteriskTransportError(
            "RTP media streaming is not implemented in this foundation."
        )

    async def close(self) -> None:
        """Release the HTTP client when this transport owns it."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def __aenter__(self) -> "HttpAsteriskTransport":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

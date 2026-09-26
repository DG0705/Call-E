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

    async def note_stasis_channel(
        self, channel_id: str, *, caller_number: str, destination_number: str
    ) -> None:
        """Record a channel seen in Stasis for a later ``accept_inbound``."""
        ...

    async def answer(self, channel_id: str) -> None: ...

    async def hangup(self, channel_id: str) -> None: ...

    async def play_media(self, channel_id: str, media: bytes) -> None:
        """Stream encoded audio onto the channel toward the phone."""
        ...

    async def create_external_media(
        self, *, app: str, external_host: str, media_format: str = "ulaw"
    ) -> str:
        """Create an ARI external-media channel and return its channel id."""
        ...

    async def create_bridge(self) -> str:
        """Create an ARI mixing bridge and return its bridge id."""
        ...

    async def add_channel_to_bridge(self, bridge_id: str, channel_id: str) -> None:
        """Add one channel to an ARI bridge."""
        ...

    async def destroy_bridge(self, bridge_id: str) -> None:
        """Destroy an ARI bridge best-effort."""
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
        self._auth = (
            (username, password) if username and password else None
        )
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None
        self._pending_inbound: list[dict[str, str]] = []

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
            f"{self._base_url}/ari/channels", params=params, auth=self._auth
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or "id" not in payload:
            raise AsteriskTransportError("ARI did not return a channel id.")
        return str(payload["id"])

    async def note_stasis_channel(
        self, channel_id: str, *, caller_number: str, destination_number: str
    ) -> None:
        """Record a channel seen in Stasis for a later ``accept_inbound``."""
        self._pending_inbound.append(
            {
                "channel_id": channel_id,
                "caller_number": caller_number,
                "destination_number": destination_number,
            }
        )

    async def accept_inbound(
        self, *, caller_number: str, destination_number: str
    ) -> str:
        """Return the Stasis channel handed off for an inbound call.

        The ARI event stream reports channels entering Stasis before the
        application accepts them; :meth:`note_stasis_channel` records each
        one and this method hands the oldest matching channel to the caller.
        """
        for index, pending in enumerate(self._pending_inbound):
            if (
                pending["caller_number"] == caller_number
                and pending["destination_number"] == destination_number
            ):
                del self._pending_inbound[index]
                return pending["channel_id"]
        raise AsteriskTransportError(
            "No Stasis channel is waiting for this inbound call; "
            "the ARI event stream must observe StasisStart first."
        )

    async def answer(self, channel_id: str) -> None:
        response = await self._client.post(
            f"{self._base_url}/ari/channels/{channel_id}/answer",
            auth=self._auth,
        )
        response.raise_for_status()

    async def hangup(self, channel_id: str) -> None:
        response = await self._client.delete(
            f"{self._base_url}/ari/channels/{channel_id}", auth=self._auth
        )
        response.raise_for_status()

    async def play_media(self, channel_id: str, media: bytes) -> None:
        raise AsteriskTransportError(
            "RTP media streaming is not implemented in this foundation."
        )

    async def create_external_media(
        self, *, app: str, external_host: str, media_format: str = "ulaw"
    ) -> str:
        response = await self._client.post(
            f"{self._base_url}/ari/channels/externalMedia",
            params={
                "app": app,
                "externalHost": external_host,
                "format": media_format,
            },
            auth=self._auth,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or "id" not in payload:
            raise AsteriskTransportError(
                "ARI did not return an external-media channel id."
            )
        return str(payload["id"])

    async def create_bridge(self) -> str:
        """Create an ARI mixing bridge for a phone leg and media channel."""
        response = await self._client.post(
            f"{self._base_url}/ari/bridges", auth=self._auth
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or "id" not in payload:
            raise AsteriskTransportError("ARI did not return a bridge id.")
        return str(payload["id"])

    async def add_channel_to_bridge(self, bridge_id: str, channel_id: str) -> None:
        """Add one channel to an ARI bridge."""
        response = await self._client.post(
            f"{self._base_url}/ari/bridges/{bridge_id}/addChannel",
            params={"channel": channel_id},
            auth=self._auth,
        )
        response.raise_for_status()

    async def destroy_bridge(self, bridge_id: str) -> None:
        """Destroy an ARI bridge best-effort."""
        response = await self._client.delete(
            f"{self._base_url}/ari/bridges/{bridge_id}", auth=self._auth
        )
        response.raise_for_status()

    async def close(self) -> None:
        """Release the HTTP client when this transport owns it."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def __aenter__(self) -> "HttpAsteriskTransport":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

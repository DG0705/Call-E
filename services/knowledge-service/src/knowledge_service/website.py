"""SSRF-safe single-page website fetching for knowledge ingestion.

Untrusted customer URLs are validated before any network access: only
http/https, DNS is resolved explicitly and every resolved address is checked
against private/loopback/link-local/multicast/reserved ranges, responses are
size-capped while streaming, and a short timeout bounds the fetch. Only the
extracted visible text flows onward — never raw markup, scripts, or styles.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from knowledge_service.extraction import extract_html_text


class FetchError(Exception):
    """Raised when a website URL cannot be fetched safely."""


_MAX_RESPONSE_BYTES = 2_000_000
_ALLOWED_CONTENT_PREFIXES = ("text/html", "text/plain")


def _is_public_address(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return (
        not parsed.is_private
        and not parsed.is_loopback
        and not parsed.is_link_local
        and not parsed.is_multicast
        and not parsed.is_reserved
        and not parsed.is_unspecified
    )


def validate_website_url(url: str) -> str:
    """Validate a customer URL and return its normalized form.

    Rejects non-http(s) schemes, missing hosts, explicit ports oddities are
    allowed, but any hostname resolving to a non-public address (localhost,
    private ranges, link-local, metadata endpoints) is refused.
    """
    candidate = (url or "").strip()
    if len(candidate) > 2048:
        raise FetchError("URL is too long.")
    parsed = urlparse(candidate)
    if parsed.scheme not in ("http", "https"):
        raise FetchError("Only http and https URLs are allowed.")
    hostname = parsed.hostname or ""
    if not hostname:
        raise FetchError("URL must include a hostname.")
    try:
        resolved = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise FetchError(f"Could not resolve '{hostname}'.") from exc
    addresses = {item[4][0] for item in resolved}
    if not addresses or not all(_is_public_address(address) for address in addresses):
        raise FetchError(f"URL target '{hostname}' is not publicly reachable.")
    return candidate


class FetchedPage:
    """Safe extraction result for one fetched website page."""

    def __init__(
        self, *, url: str, title: str, text: str, content_type: str
    ) -> None:
        self.url = url
        self.title = title
        self.text = text
        self.content_type = content_type


class HttpxWebsiteFetcher:
    """Production website fetcher with timeout and size caps."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        max_bytes: int = _MAX_RESPONSE_BYTES,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._max_bytes = max_bytes
        self._client = client
        self._owned = client is None

    async def fetch_page(self, url: str) -> FetchedPage:
        """Fetch, validate, and extract one website page."""
        normalized = validate_website_url(url)
        client = self._client or httpx.AsyncClient(
            timeout=self._timeout, follow_redirects=True, max_redirects=3
        )
        try:
            response = await client.get(
                normalized,
                headers={"User-Agent": "Call-E-Knowledge/1.0", "Accept": "text/html,text/plain"},
            )
            response.raise_for_status()
            _validate_final_host(str(response.url))
            content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            if content_type and not content_type.startswith(_ALLOWED_CONTENT_PREFIXES):
                raise FetchError(f"Unsupported content type '{content_type}'.")
            body = await self._read_capped(response)
            text = body.decode("utf-8", errors="replace")
            title, visible = extract_html_text(text)
            if not visible.strip():
                raise FetchError("No readable text found on the page.")
            return FetchedPage(
                url=str(response.url),
                title=title or normalized,
                text=visible,
                content_type=content_type or "text/html",
            )
        except httpx.HTTPStatusError as exc:
            raise FetchError(
                f"Page returned status {exc.response.status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise FetchError("Could not fetch the page in time.") from exc
        finally:
            if self._owned:
                await client.aclose()

    async def _read_capped(self, response: httpx.Response) -> bytes:
        chunks: list[bytes] = []
        total = 0
        async for blob in response.aiter_bytes(chunk_size=65_536):
            total += len(blob)
            if total > self._max_bytes:
                raise FetchError("Page exceeds the 2 MB ingestion limit.")
            chunks.append(blob)
        return b"".join(chunks)


def _validate_final_host(url: str) -> None:
    """Refuse redirect chains landing on non-public addresses."""
    hostname = urlparse(url).hostname or ""
    try:
        resolved = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise FetchError(f"Could not resolve '{hostname}'.") from exc
    addresses = {item[4][0] for item in resolved}
    if not addresses or not all(_is_public_address(address) for address in addresses):
        raise FetchError(f"URL target '{hostname}' is not publicly reachable.")


def describe_fetcher_error(error: Exception) -> str:
    """Render a safe human-readable fetch failure for the frontend."""
    if isinstance(error, FetchError):
        return str(error)
    return "Website ingestion failed unexpectedly."

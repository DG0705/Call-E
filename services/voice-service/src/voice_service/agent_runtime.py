"""Boundary for the agent runtime consumed by the voice service."""

import json
import os
from collections.abc import AsyncIterator
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field

DEFAULT_AGENT_SERVICE_URL = "http://agent-service:8000"
AGENT_SERVICE_URL_ENV_VAR = "AGENT_SERVICE_URL"


class AgentConfiguration(BaseModel):
    """Minimal agent fields resolved by the voice service at session creation."""

    id: str
    tenant_id: str
    language: str = "en"
    voice_id: str | None = None
    greeting: str | None = None


class RuntimeResult(BaseModel):
    """Normalized agent runtime response consumed by the voice turn flow."""

    text: str
    provider_name: str
    model_name: str
    usage: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = None
    agent_id: str | None = None
    tool_iterations: int = 0


class AgentRuntimeClient(Protocol):
    """Provider boundary implemented by the real runtime and an HTTP client."""

    async def get_agent(self, *, tenant_id: str, agent_id: str) -> AgentConfiguration: ...

    async def respond(
        self, *, tenant_id: str, agent_id: str, conversation_id: str, message: str
    ) -> RuntimeResult: ...


class RuntimeTextChunk(BaseModel):
    """One streamed piece of a runtime turn for sentence handoff."""

    text_delta: str = ""
    done: bool = False
    result: RuntimeResult | None = None


def _safe_json(raw: str) -> dict[str, Any]:
    """Parse one SSE data line, tolerating malformed frames."""
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


class AgentRuntimeHttpClient:
    """Call the agent-service runtime API over synchronous HTTP."""

    def __init__(
        self,
        *,
        base_url: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None

    async def get_agent(self, *, tenant_id: str, agent_id: str) -> AgentConfiguration:
        response = await self._client.get(
            f"{self._base_url}/api/v1/agents/{agent_id}",
            params={"tenant_id": tenant_id},
        )
        response.raise_for_status()
        payload = response.json()
        return AgentConfiguration(
            id=payload["id"],
            tenant_id=payload["tenant_id"],
            language=payload.get("language", "en"),
            voice_id=payload.get("voice_id"),
            greeting=payload.get("greeting"),
        )

    async def respond(
        self, *, tenant_id: str, agent_id: str, conversation_id: str, message: str
    ) -> RuntimeResult:
        response = await self._client.post(
            f"{self._base_url}/api/v1/agents/{agent_id}/runtime/test",
            params={"tenant_id": tenant_id},
            json={"conversation_id": conversation_id, "message": message},
        )
        response.raise_for_status()
        payload = response.json()
        return RuntimeResult(
            text=payload["response"],
            provider_name=payload["provider"],
            model_name=payload["model"],
            conversation_id=payload["conversation_id"],
            agent_id=payload["agent_id"],
            tool_iterations=int(payload.get("tool_iterations", 0) or 0),
        )

    async def respond_stream(
        self, *, tenant_id: str, agent_id: str, conversation_id: str, message: str
    ) -> AsyncIterator[RuntimeTextChunk]:
        """Stream one runtime turn as text deltas plus a terminal result.

        Consumes the agent-service SSE stream. Tool progress events are
        skipped (the agent service logs them); only speakable text and the
        final result surface here. Yields nothing but raises on transport
        failure so callers fall back to :meth:`respond`.
        """
        async with self._client.stream(
            "POST",
            f"{self._base_url}/api/v1/agents/{agent_id}/runtime/stream",
            params={"tenant_id": tenant_id},
            json={"conversation_id": conversation_id, "message": message},
        ) as response:
            response.raise_for_status()
            event_name = ""
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event_name = line[len("event:") :].strip()
                elif line.startswith("data:"):
                    payload = _safe_json(line[len("data:") :])
                    if event_name == "text":
                        delta = payload.get("delta", "")
                        if delta:
                            yield RuntimeTextChunk(text_delta=str(delta))
                    elif event_name == "done":
                        result = payload.get("result") or {}
                        history = result.get("tool_execution_history") or []
                        yield RuntimeTextChunk(
                            text_delta="",
                            done=True,
                            result=RuntimeResult(
                                text=str(result.get("text", "")),
                                provider_name=str(result.get("provider_name", "")),
                                model_name=str(result.get("model_name", "")),
                                usage=dict(result.get("usage") or {}),
                                conversation_id=result.get("conversation_id") or conversation_id,
                                agent_id=result.get("agent_id") or agent_id,
                                tool_iterations=len(history),
                            ),
                        )
                    elif event_name == "error":
                        raise RuntimeError(f"Runtime stream error: {payload}")
                elif not line.strip():
                    event_name = ""

    async def close(self) -> None:
        """Release the HTTP client when this boundary owns it."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()


def create_agent_runtime_http_client(
    *, base_url: str | None = None, client: httpx.AsyncClient | None = None
) -> AgentRuntimeHttpClient:
    """Build the HTTP agent runtime boundary from the service environment."""
    return AgentRuntimeHttpClient(
        base_url=base_url or os.getenv(
            AGENT_SERVICE_URL_ENV_VAR, DEFAULT_AGENT_SERVICE_URL
        ),
        client=client,
    )

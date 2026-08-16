"""Boundary for the agent runtime consumed by the voice service."""

import os
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


class RuntimeResult(BaseModel):
    """Normalized agent runtime response consumed by the voice turn flow."""

    text: str
    provider_name: str
    model_name: str
    usage: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = None
    agent_id: str | None = None


class AgentRuntimeClient(Protocol):
    """Provider boundary implemented by the real runtime and an HTTP client."""

    async def get_agent(self, *, tenant_id: str, agent_id: str) -> AgentConfiguration: ...

    async def respond(
        self, *, tenant_id: str, agent_id: str, conversation_id: str, message: str
    ) -> RuntimeResult: ...


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
        )

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

"""HTTP knowledge retriever bridging the agent runtime to knowledge-service.

The live runtime previously ran with no retriever at all, so uploaded
customer knowledge never reached the LLM. This adapter resolves the agent's
own ``knowledge_sources`` from its configuration and queries the
knowledge-service search endpoint with them; knowledge-service still enforces
tenant isolation on every request. Retrieval failures degrade to empty
context (logged) so a knowledge outage can never break a phone call.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

from agent_service.runtime.knowledge import RetrievedKnowledge


class AgentConfigurationLoader(Protocol):
    """Minimal agent-configuration surface needed for source resolution."""

    async def get_by_tenant_and_id(
        self, *, tenant_id: str, agent_id: str
    ) -> Any | None: ...


class KnowledgeServiceRetriever:
    """Agent-runtime retriever backed by the knowledge-service HTTP API."""

    def __init__(
        self,
        *,
        base_url: str,
        configuration_loader: AgentConfigurationLoader | None = None,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._configuration_loader = configuration_loader
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._logger = logger or logging.getLogger(__name__)

    async def retrieve(
        self, *, tenant_id: str, agent_id: str, query: str, top_k: int = 3
    ) -> list[RetrievedKnowledge]:
        """Return grounding chunks for an agent, or [] when unavailable."""
        try:
            source_ids = await self._resolve_sources(
                tenant_id=tenant_id, agent_id=agent_id
            )
            if not source_ids:
                return []
            response = await self._client.post(
                f"{self._base_url}/api/v1/knowledge/search",
                json={
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "query": query,
                    "top_k": top_k,
                    "source_ids": source_ids,
                },
            )
            response.raise_for_status()
            return [
                RetrievedKnowledge(
                    document_id=item["document_id"],
                    chunk_id=item["chunk_id"],
                    content=item["content"],
                    score=float(item.get("score", 0.0)),
                )
                for item in response.json().get("results", [])
            ]
        except Exception:
            self._logger.warning(
                "knowledge retrieval unavailable",
                extra={"tenant_id": tenant_id, "agent_id": agent_id},
            )
            return []

    async def _resolve_sources(
        self, *, tenant_id: str, agent_id: str
    ) -> list[str]:
        if self._configuration_loader is None:
            return []
        agent = await self._configuration_loader.get_by_tenant_and_id(
            tenant_id=tenant_id, agent_id=agent_id
        )
        if agent is None:
            return []
        return list(getattr(agent, "knowledge_sources", []) or [])

    async def close(self) -> None:
        """Release the HTTP client when this retriever owns it."""
        close_client = getattr(self._client, "aclose", None)
        if close_client is not None:
            await close_client()

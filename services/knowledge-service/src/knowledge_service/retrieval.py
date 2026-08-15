"""Tenant- and agent-scoped knowledge retrieval and context building."""

from typing import Protocol

from pydantic import BaseModel

from knowledge_service.embeddings import EmbeddingProvider
from knowledge_service.models import KnowledgeDocument
from knowledge_service.storage import VectorRepository


class RetrievedChunk(BaseModel):
    """One knowledge chunk returned to a caller for grounding."""

    document_id: str
    chunk_id: str
    content: str
    score: float


class AgentKnowledgeResolver(Protocol):
    """Resolves which knowledge sources an agent is allowed to use."""

    async def resolve_agent_sources(
        self, *, tenant_id: str, agent_id: str
    ) -> list[str]: ...


class KnowledgeDocumentLookup(Protocol):
    """Narrow document read boundary used by retrieval."""

    async def list_by_tenant_and_sources(
        self, *, tenant_id: str, source_ids: list[str]
    ) -> list[KnowledgeDocument]: ...


class KnowledgeRetriever(Protocol):
    """Contract implemented by knowledge backends feeding the platform."""

    async def retrieve(
        self, *, tenant_id: str, agent_id: str, query: str, top_k: int = 3
    ) -> list[RetrievedChunk]: ...


class MappingAgentKnowledgeResolver:
    """Default agent-to-source resolver backed by an explicit mapping."""

    def __init__(self, mapping: dict[str, list[str]] | None = None) -> None:
        self._mapping = {
            agent_id: list(source_ids)
            for agent_id, source_ids in (mapping or {}).items()
        }

    def register_agent(self, *, agent_id: str, source_ids: list[str]) -> None:
        """Allow an agent to retrieve from the supplied knowledge sources."""
        self._mapping[agent_id] = list(source_ids)

    async def resolve_agent_sources(
        self, *, tenant_id: str, agent_id: str
    ) -> list[str]:
        return self._mapping.get(agent_id, [])


class KnowledgeRetrieverService:
    """Retrieve chunks only within the tenant and agent knowledge boundary."""

    def __init__(
        self,
        *,
        sources: AgentKnowledgeResolver,
        documents: KnowledgeDocumentLookup,
        embedder: EmbeddingProvider,
        repository: VectorRepository,
    ) -> None:
        self._sources = sources
        self._documents = documents
        self._embedder = embedder
        self._repository = repository

    async def retrieve(
        self, *, tenant_id: str, agent_id: str, query: str, top_k: int = 3
    ) -> list[RetrievedChunk]:
        """Return the top-k chunks for an agent, or nothing outside its boundary."""
        if top_k < 1:
            raise ValueError("top_k must be at least 1.")
        source_ids = await self._sources.resolve_agent_sources(
            tenant_id=tenant_id, agent_id=agent_id
        )
        if not source_ids:
            return []
        documents = await self._documents.list_by_tenant_and_sources(
            tenant_id=tenant_id, source_ids=source_ids
        )
        document_ids = [document.id for document in documents]
        if not document_ids:
            return []
        embedding = await self._embedder.embed_text(query)
        matches = await self._repository.search(
            tenant_id=tenant_id,
            vector=embedding.vector,
            top_k=top_k,
            document_ids=document_ids,
        )
        return [
            RetrievedChunk(
                document_id=match.document_id,
                chunk_id=match.chunk_id,
                content=match.content,
                score=match.score,
            )
            for match in matches
        ]


def build_knowledge_context(retrieved: list[RetrievedChunk]) -> str:
    """Format retrieved chunks into a stable grounding context block."""
    if not retrieved:
        return ""
    sections = [f"[{chunk.chunk_id}] {chunk.content}" for chunk in retrieved]
    return "Relevant knowledge:\n" + "\n\n".join(sections)

"""Agent-runtime knowledge retrieval contract and context building."""

from typing import Protocol

from pydantic import BaseModel


class RetrievedKnowledge(BaseModel):
    """One knowledge chunk scoped to an agent for runtime grounding."""

    document_id: str
    chunk_id: str
    content: str
    score: float = 0.0


class KnowledgeRetriever(Protocol):
    """Contract implemented by knowledge backends feeding the agent runtime."""

    async def retrieve(
        self, *, tenant_id: str, agent_id: str, query: str, top_k: int = 3
    ) -> list[RetrievedKnowledge]: ...


def build_knowledge_context(retrieved: list[RetrievedKnowledge]) -> str:
    """Format retrieved knowledge into a stable grounding context block."""
    if not retrieved:
        return ""
    sections = [f"[{item.chunk_id}] {item.content}" for item in retrieved]
    return "Relevant knowledge:\n" + "\n\n".join(sections)

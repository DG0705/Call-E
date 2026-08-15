"""Tests for grounding the agent runtime with retrieved knowledge."""

import asyncio

import pytest

from agent_service.models import AGENTS_COLLECTION, Agent
from agent_service.repositories import AgentRepository
from agent_service.runtime import (
    AgentRuntime,
    MockLLMProvider,
    RetrievedKnowledge,
    build_knowledge_context,
)
from agent_service.runtime.context import (
    ConversationMessage,
    InMemoryConversationStore,
)
from agent_service.runtime.knowledge import KnowledgeRetriever
from agent_service.runtime.tools import (
    ProviderToolCall,
    create_development_tool_registry,
)
from agent_service.services import AgentService


class FakeAgentCollection:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self.documents = documents

    async def find_one(self, filter: dict[str, str]) -> dict[str, object] | None:
        return next(
            (
                document
                for document in self.documents
                if all(document.get(key) == value for key, value in filter.items())
            ),
            None,
        )


class FakeCoreDatabase:
    def __init__(self, agent_documents: list[dict[str, object]]) -> None:
        self.agents = FakeAgentCollection(agent_documents)

    async def list_collection_names(self, **kwargs: object) -> list[str]:
        return [AGENTS_COLLECTION]

    def __getitem__(self, name: str) -> FakeAgentCollection:
        assert name == AGENTS_COLLECTION
        return self.agents


class RecordingProvider(MockLLMProvider):
    """Mock provider that records the grounding instruction per generation."""

    def __init__(self, *, planned_tool_calls: list[ProviderToolCall] | None = None) -> None:
        super().__init__(planned_tool_calls=planned_tool_calls)
        self.calls: list[tuple[str, list[ConversationMessage]]] = []

    async def generate_response(
        self,
        *,
        system_instruction: str,
        messages: list[ConversationMessage],
        tools: object = None,
    ):
        self.calls.append((system_instruction, messages.copy()))
        return await super().generate_response(
            system_instruction=system_instruction, messages=messages, tools=tools
        )


class FakeKnowledgeRetriever:
    """Deterministic retriever that records its invocation arguments."""

    def __init__(self, results: list[RetrievedKnowledge] | None = None) -> None:
        self.results = results or []
        self.calls: list[dict[str, object]] = []

    async def retrieve(
        self, *, tenant_id: str, agent_id: str, query: str, top_k: int = 3
    ) -> list[RetrievedKnowledge]:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "query": query,
                "top_k": top_k,
            }
        )
        return self.results


def agent_document(*, knowledge_sources: list[str]) -> dict[str, object]:
    return {
        "_id": "agent-1",
        "tenant_id": "tenant-1",
        "name": "Receptionist",
        "role": "customer support assistant",
        "system_prompt": "Help customers clearly.",
        "personality": "warm and concise",
        "language": "en",
        "voice_id": "neutral-voice",
        "goals": ["Resolve simple questions"],
        "allowed_tools": ["echo_customer_context"],
        "knowledge_sources": knowledge_sources,
        "created_at": "2026-08-03T12:00:00Z",
        "updated_at": "2026-08-03T12:00:00Z",
    }


def _runtime(*, retriever: KnowledgeRetriever | None, provider: MockLLMProvider):
    database = FakeCoreDatabase([agent_document(knowledge_sources=["support-handbook"])])
    store = InMemoryConversationStore()
    runtime = AgentRuntime(
        configuration_loader=AgentService(AgentRepository(database)),
        provider=provider,
        conversation_store=store,
        tool_registry=create_development_tool_registry(),
        knowledge_retriever=retriever,
    )
    return runtime, store


def test_build_knowledge_context_formats_and_handles_empty() -> None:
    context = build_knowledge_context(
        [
            RetrievedKnowledge(
                document_id="document-1",
                chunk_id="document-1:0",
                content="Refunds are available.",
                score=0.8,
            )
        ]
    )

    assert context == "Relevant knowledge:\n[document-1:0] Refunds are available."
    assert build_knowledge_context([]) == ""


def test_runtime_injects_retrieved_knowledge_into_system_instruction() -> None:
    retriever = FakeKnowledgeRetriever(
        [RetrievedKnowledge(document_id="document-1", chunk_id="document-1:0", content="Refunds are available.")]
    )
    provider = RecordingProvider()
    runtime, _ = _runtime(retriever=retriever, provider=provider)

    result = asyncio.run(
        runtime.respond(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            message="Can I get a refund?",
        )
    )

    assert result.text == "Mock response: Can I get a refund?"
    assert retriever.calls == [
        {
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "query": "Can I get a refund?",
            "top_k": 3,
        }
    ]
    instruction, _ = provider.calls[0]
    assert "Relevant knowledge:" in instruction
    assert "Refunds are available." in instruction


def test_runtime_does_not_persist_knowledge_in_conversation() -> None:
    retriever = FakeKnowledgeRetriever(
        [RetrievedKnowledge(document_id="document-1", chunk_id="document-1:0", content="Refunds are available.")]
    )
    runtime, store = _runtime(retriever=retriever, provider=RecordingProvider())

    asyncio.run(
        runtime.respond(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            message="Can I get a refund?",
        )
    )
    context = asyncio.run(
        store.get(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    assert context is not None
    assert [message.role for message in context.messages] == ["system", "user", "assistant"]
    assert "Relevant knowledge:" not in context.messages[0].content


def test_runtime_skips_retrieval_without_retriever() -> None:
    retriever = FakeKnowledgeRetriever()
    runtime, _ = _runtime(retriever=retriever, provider=RecordingProvider())
    runtime._knowledge_retriever = None

    asyncio.run(
        runtime.respond(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            message="Hello",
        )
    )

    assert retriever.calls == []


def test_runtime_skips_retrieval_for_agent_without_sources() -> None:
    database = FakeCoreDatabase([agent_document(knowledge_sources=[])])
    retriever = FakeKnowledgeRetriever()
    provider = RecordingProvider()
    runtime = AgentRuntime(
        configuration_loader=AgentService(AgentRepository(database)),
        provider=provider,
        conversation_store=InMemoryConversationStore(),
        knowledge_retriever=retriever,
    )

    asyncio.run(
        runtime.respond(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            message="Hello",
        )
    )

    assert retriever.calls == []
    instruction, _ = provider.calls[0]
    assert "Relevant knowledge:" not in instruction


def test_runtime_grounds_tool_loop_once_per_turn() -> None:
    retriever = FakeKnowledgeRetriever(
        [RetrievedKnowledge(document_id="document-1", chunk_id="document-1:0", content="Refunds are available.")]
    )
    provider = RecordingProvider(
        planned_tool_calls=[
            ProviderToolCall(
                call_id="call-1",
                tool_name="echo_customer_context",
                arguments={"message": "hi"},
            )
        ]
    )
    runtime, _ = _runtime(retriever=retriever, provider=provider)

    result = asyncio.run(
        runtime.respond(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            message="Can I get a refund?",
        )
    )

    assert result.text == "Mock response: Can I get a refund?"
    assert len(provider.calls) == 2
    assert len(retriever.calls) == 1
    assert provider.calls[0][0] == provider.calls[1][0]
    assert "Relevant knowledge:" in provider.calls[1][0]
    assert [message.role for message in provider.calls[1][1]] == [
        "system",
        "user",
        "assistant",
        "tool",
    ]


def test_runtime_without_results_omits_knowledge_block() -> None:
    retriever = FakeKnowledgeRetriever()
    provider = RecordingProvider()
    runtime, _ = _runtime(retriever=retriever, provider=provider)

    asyncio.run(
        runtime.respond(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            message="Hello",
        )
    )

    assert retriever.calls == [
        {
            "tenant_id": "tenant-1",
            "agent_id": "agent-1",
            "query": "Hello",
            "top_k": 3,
        }
    ]
    instruction, _ = provider.calls[0]
    assert "Relevant knowledge:" not in instruction


def test_runtime_rejects_invalid_knowledge_top_k() -> None:
    database = FakeCoreDatabase([agent_document(knowledge_sources=["support-handbook"])])
    with pytest.raises(ValueError):
        AgentRuntime(
            configuration_loader=AgentService(AgentRepository(database)),
            provider=MockLLMProvider(),
            conversation_store=InMemoryConversationStore(),
            knowledge_retriever=FakeKnowledgeRetriever(),
            knowledge_top_k=0,
        )

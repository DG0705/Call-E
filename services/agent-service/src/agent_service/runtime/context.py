"""Typed conversation context and its persistence boundary."""

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from agent_service.runtime.tools import ProviderToolCall


MessageRole = Literal["system", "user", "assistant", "tool"]


class ConversationMessage(BaseModel):
    """One provider-neutral conversation message."""

    role: MessageRole
    content: str
    tool_call_id: str | None = None
    tool_calls: list[ProviderToolCall] = Field(default_factory=list)


class ConversationContext(BaseModel):
    """Conversation state belonging to exactly one tenant and agent."""

    agent_id: str
    tenant_id: str
    conversation_id: str
    messages: list[ConversationMessage] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConversationStore(Protocol):
    """Persistence boundary for runtime conversation state."""

    async def get(
        self, *, tenant_id: str, agent_id: str, conversation_id: str
    ) -> ConversationContext | None: ...

    async def save(self, context: ConversationContext) -> None: ...


class InMemoryConversationStore:
    """Development-only conversation store with no external dependencies."""

    def __init__(self) -> None:
        self._contexts: dict[tuple[str, str, str], ConversationContext] = {}

    async def get(
        self, *, tenant_id: str, agent_id: str, conversation_id: str
    ) -> ConversationContext | None:
        return self._contexts.get((tenant_id, agent_id, conversation_id))

    async def save(self, context: ConversationContext) -> None:
        key = (context.tenant_id, context.agent_id, context.conversation_id)
        self._contexts[key] = context

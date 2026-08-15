"""MongoDB-backed persistent conversation memory for the agent runtime."""

from datetime import UTC, datetime
from typing import Any, Protocol

from agent_service.runtime.context import ConversationContext, ConversationStore


CONVERSATIONS_COLLECTION = "conversations"
CONVERSATION_LOOKUP_INDEX = "tenant_agent_conversation"


class ConversationCollection(Protocol):
    """Mongo collection operations used by persistent conversation memory."""

    async def create_index(self, keys: list[tuple[str, int]], **kwargs: Any) -> str: ...

    async def find_one(self, filter: dict[str, str]) -> dict[str, Any] | None: ...

    async def update_one(
        self, filter: dict[str, str], update: dict[str, Any], **kwargs: Any
    ) -> Any: ...


class ConversationDatabase(Protocol):
    """Small database surface needed by the conversation store."""

    def __getitem__(self, name: str) -> ConversationCollection: ...


class MongoConversationStore(ConversationStore):
    """Tenant- and agent-isolated conversation persistence in MongoDB."""

    def __init__(self, database: ConversationDatabase) -> None:
        self._collection = database[CONVERSATIONS_COLLECTION]

    async def ensure_indexes(self) -> None:
        """Create the single lookup index used by the current runtime flow."""
        await self._collection.create_index(
            [("tenant_id", 1), ("agent_id", 1), ("conversation_id", 1)],
            name=CONVERSATION_LOOKUP_INDEX,
            unique=True,
        )

    async def get(
        self, *, tenant_id: str, agent_id: str, conversation_id: str
    ) -> ConversationContext | None:
        """Load a conversation only when all ownership identifiers match."""
        document = await self._collection.find_one(
            self._identity(
                tenant_id=tenant_id, agent_id=agent_id, conversation_id=conversation_id
            )
        )
        return ConversationContext.model_validate(document) if document is not None else None

    async def save(self, context: ConversationContext) -> None:
        """Upsert context without allowing an existing creation timestamp to change."""
        now = datetime.now(UTC)
        if context.created_at is None:
            context.created_at = now
        context.updated_at = now
        await self._collection.update_one(
            self._identity(
                tenant_id=context.tenant_id,
                agent_id=context.agent_id,
                conversation_id=context.conversation_id,
            ),
            {
                "$set": {
                    "messages": [message.model_dump() for message in context.messages],
                    "metadata": context.metadata,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "conversation_id": context.conversation_id,
                    "tenant_id": context.tenant_id,
                    "agent_id": context.agent_id,
                    "created_at": context.created_at,
                },
            },
            upsert=True,
        )

    @staticmethod
    def _identity(
        *, tenant_id: str, agent_id: str, conversation_id: str
    ) -> dict[str, str]:
        return {
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "conversation_id": conversation_id,
        }

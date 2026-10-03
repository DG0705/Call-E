"""The reusable, provider-neutral agent runtime."""

import logging
import time
from collections.abc import AsyncIterator
from typing import Protocol

from pydantic import BaseModel, Field

from agent_service.models import Agent
from agent_service.runtime.context import (
    ConversationContext,
    ConversationMessage,
    ConversationStore,
)
from agent_service.runtime.knowledge import (
    KnowledgeRetriever,
    build_knowledge_context,
)
from agent_service.runtime.observability import (
    AGENT_EVENT_LOGGER,
    log_agent_event,
)
from agent_service.runtime.provider import LLMProvider, LLMResponse, LLMStreamEvent
from agent_service.runtime.tools import (
    ProviderToolCall,
    ToolCall,
    ToolEngine,
    ToolRegistry,
    ToolResult,
)


class AgentConfigurationLoader(Protocol):
    """Application-facing configuration boundary used by the runtime."""

    async def get_by_tenant_and_id(
        self, *, tenant_id: str, agent_id: str
    ) -> Agent | None: ...


class AgentNotFoundError(Exception):
    """Raised when an agent does not exist for the supplied tenant."""


class RuntimeResult(LLMResponse):
    """Provider result paired with the persisted conversation context."""

    conversation_id: str
    agent_id: str
    tool_execution_history: list[dict[str, object]] = Field(default_factory=list)


class RuntimeStreamEvent(BaseModel):
    """One incremental piece of a runtime turn for streaming callers.

    ``text`` carries speakable assistant fragments as they arrive;
    ``tool`` marks tool execution progress (names only, never arguments or
    results); ``done`` terminates the turn with the complete result.
    """

    type: str
    delta: str = ""
    tool_name: str | None = None
    call_id: str | None = None
    success: bool | None = None
    result: RuntimeResult | None = None


class ToolExecutionRecord(BaseModel):
    """One tool call and its result, captured during a single respond() call."""

    tool_name: str
    arguments: dict[str, object] = Field(default_factory=dict)
    call_id: str = ""
    success: bool = True
    result: object = None
    error: str | None = None


class AgentRuntime:
    """Run agent conversations using supplied services, not database clients."""

    def __init__(
        self,
        *,
        configuration_loader: AgentConfigurationLoader,
        provider: LLMProvider,
        conversation_store: ConversationStore,
        tool_registry: ToolRegistry | None = None,
        max_tool_iterations: int = 3,
        knowledge_retriever: KnowledgeRetriever | None = None,
        knowledge_top_k: int = 3,
        logger: logging.Logger | None = None,
    ) -> None:
        self._configuration_loader = configuration_loader
        self._provider = provider
        self._conversation_store = conversation_store
        self._tool_engine = ToolEngine(tool_registry) if tool_registry is not None else None
        if max_tool_iterations < 1:
            raise ValueError("max_tool_iterations must be at least 1.")
        self._max_tool_iterations = max_tool_iterations
        if knowledge_top_k < 1:
            raise ValueError("knowledge_top_k must be at least 1.")
        self._knowledge_retriever = knowledge_retriever
        self._knowledge_top_k = knowledge_top_k
        self._logger = logger or logging.getLogger(AGENT_EVENT_LOGGER)

    async def get_agent(self, *, tenant_id: str, agent_id: str) -> Agent:
        """Load the tenant-scoped configuration required by the runtime."""
        agent = await self._configuration_loader.get_by_tenant_and_id(
            tenant_id=tenant_id, agent_id=agent_id
        )
        if agent is None:
            raise AgentNotFoundError(agent_id)
        return agent

    async def respond(
        self, *, tenant_id: str, agent_id: str, conversation_id: str, message: str
    ) -> RuntimeResult:
        """Append user input, call the provider, and retain local context.

        Buffered facade over :meth:`respond_stream`; the contract is unchanged
        for non-streaming callers.
        """
        final: RuntimeResult | None = None
        async for event in self.respond_stream(
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            message=message,
        ):
            if event.type == "done" and event.result is not None:
                final = event.result
        if final is None:
            raise ValueError("Runtime stream ended without a result.")
        return final

    async def respond_stream(
        self, *, tenant_id: str, agent_id: str, conversation_id: str, message: str
    ) -> AsyncIterator[RuntimeStreamEvent]:
        """Stream one turn as text, tool-progress, and terminal events.

        Assistant text deltas are user-facing fragments safe to speak as they
        arrive. Tool arguments, results, and internal reasoning never appear
        in ``text`` events. Cancellation propagates to the provider stream so
        barge-in stops generation promptly.
        """
        agent = await self.get_agent(tenant_id=tenant_id, agent_id=agent_id)
        log_agent_event(
            self._logger,
            "agent_turn_started",
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
        )
        turn_start = time.monotonic()
        knowledge_ms = 0
        llm_ms = 0
        first_token_holder: dict[str, int] = {}
        first_sentence_holder: dict[str, int] = {}
        tool_ms = 0
        knowledge_start = time.monotonic()
        turn_instruction = await self._build_turn_instruction(
            agent, message, conversation_id=conversation_id
        )
        knowledge_ms = int((time.monotonic() - knowledge_start) * 1000)
        context = await self._conversation_store.get(
            tenant_id=tenant_id, agent_id=agent_id, conversation_id=conversation_id
        )
        if context is None:
            context = ConversationContext(
                tenant_id=tenant_id,
                agent_id=agent_id,
                conversation_id=conversation_id,
                messages=[
                    ConversationMessage(
                        role="system", content=self._build_system_instruction(agent)
                    )
                ],
            )
        context.messages.append(ConversationMessage(role="user", content=message))

        async def _stream_generation() -> AsyncIterator[LLMStreamEvent]:
            start = time.monotonic()
            try:
                async for event in self._generate_events(
                    agent,
                    context,
                    system_instruction=turn_instruction,
                    llm_start=start,
                    first_token_ms=first_token_holder,
                    first_sentence_ms=first_sentence_holder,
                ):
                    yield event
            finally:
                nonlocal llm_ms
                llm_ms += int((time.monotonic() - start) * 1000)

        first_token_logged = False
        tool_history: list[dict[str, object]] = []
        iterations = 0
        provider_response: LLMResponse | None = None
        while True:
            async for event in _stream_generation():
                if event.text_delta:
                    if not first_token_logged:
                        first_token_logged = True
                        log_agent_event(
                            self._logger,
                            "RUNTIME_FIRST_TOKEN",
                            tenant_id=tenant_id,
                            agent_id=agent_id,
                            conversation_id=conversation_id,
                            elapsed_ms=int(
                                (time.monotonic() - turn_start) * 1000
                            ),
                            message="RUNTIME_FIRST_TOKEN",
                        )
                    yield RuntimeStreamEvent(type="text", delta=event.text_delta)
                if event.done and event.full_response is not None:
                    provider_response = event.full_response
            if provider_response is None:
                raise ValueError("LLM stream ended without a completion event.")
            if not provider_response.tool_calls:
                break
            if self._tool_engine is None:
                provider_response = self._tool_engine_unavailable_response(provider_response)
                break
            self._append_assistant_tool_calls(context, provider_response)
            if iterations >= self._max_tool_iterations:
                for provider_call in provider_response.tool_calls:
                    self._append_tool_result(context, self._limit_result(provider_call))
                provider_response = LLMResponse(
                    text="Tool execution limit exceeded.",
                    provider_name=provider_response.provider_name,
                    model_name=provider_response.model_name,
                    usage=provider_response.usage,
                )
                break
            for provider_call in provider_response.tool_calls:
                log_agent_event(
                    self._logger,
                    "tool_called",
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                    tool_name=provider_call.tool_name,
                    call_id=provider_call.call_id,
                    success=None,
                )
                yield RuntimeStreamEvent(
                    type="tool",
                    tool_name=provider_call.tool_name,
                    call_id=provider_call.call_id,
                )
                tool_start = time.monotonic()
                try:
                    result = await self._tool_engine.execute(
                        agent=agent,
                        call=ToolCall(
                            tool_name=provider_call.tool_name,
                            arguments=provider_call.arguments,
                            call_id=provider_call.call_id,
                            tenant_id=tenant_id,
                            agent_id=agent_id,
                            conversation_id=conversation_id,
                        ),
                    )
                finally:
                    tool_ms += int((time.monotonic() - tool_start) * 1000)
                log_agent_event(
                    self._logger,
                    "tool_completed",
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    conversation_id=conversation_id,
                    tool_name=result.tool_name,
                    call_id=result.call_id,
                    success=result.success,
                )
                yield RuntimeStreamEvent(
                    type="tool",
                    tool_name=result.tool_name,
                    call_id=result.call_id,
                    success=result.success,
                )
                self._append_tool_result(context, result)
                tool_history.append({
                    "tool_name": result.tool_name,
                    "arguments": dict(provider_call.arguments),
                    "call_id": result.call_id,
                    "success": result.success,
                    "result": result.result,
                    "error": result.error,
                })
            iterations += 1
        assert provider_response is not None
        context.messages.append(
            ConversationMessage(role="assistant", content=provider_response.text)
        )
        await self._conversation_store.save(context)
        log_agent_event(
            self._logger,
            "response_generated",
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            provider_name=provider_response.provider_name,
            model_name=provider_response.model_name,
        )
        log_agent_event(
            self._logger,
            "runtime_turn_completed",
            tenant_id=tenant_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
            knowledge_ms=knowledge_ms,
            llm_ms=llm_ms,
            llm_first_token_ms=first_token_holder.get("ms"),
            llm_first_sentence_ms=first_sentence_holder.get("ms"),
            tool_ms=tool_ms,
            tool_iterations=iterations,
            turn_ms=int((time.monotonic() - turn_start) * 1000),
        )
        yield RuntimeStreamEvent(
            type="done",
            result=RuntimeResult(
                conversation_id=conversation_id,
                agent_id=agent_id,
                tool_execution_history=tool_history,
                **provider_response.model_dump(),
            ),
        )

    async def _generate(
        self, agent: Agent, context: ConversationContext, *, system_instruction: str
    ) -> LLMResponse:
        tools = (
            self._tool_engine.registry.available_for(agent)
            if self._tool_engine is not None
            else []
        )
        return await self._provider.generate_response(
            system_instruction=system_instruction,
            messages=context.messages,
            tools=tools,
        )

    async def _generate_events(
        self,
        agent: Agent,
        context: ConversationContext,
        *,
        system_instruction: str,
        llm_start: float,
        first_token_ms: dict[str, int],
        first_sentence_ms: dict[str, int],
    ) -> AsyncIterator[LLMStreamEvent]:
        """Yield one generation's provider events, timing first token/sentence.

        The terminal completion event is yielded last; only it feeds the tool
        loop, so partial tool fragments can never execute. Providers without
        streaming fall back to their buffered default. Cancellation
        propagates so barge-in stops generation promptly.
        """
        tools = (
            self._tool_engine.registry.available_for(agent)
            if self._tool_engine is not None
            else []
        )
        stream = getattr(self._provider, "generate_response_stream", None)
        if stream is None:
            buffered_start = time.monotonic()
            response = await self._generate(
                agent, context, system_instruction=system_instruction
            )
            buffered_ms = int((time.monotonic() - buffered_start) * 1000)
            first_token_ms["ms"] = buffered_ms
            if _has_sentence_end(response.text):
                first_sentence_ms["ms"] = buffered_ms
            yield LLMStreamEvent(
                text_delta=response.text,
                done=True,
                full_response=response,
            )
            return
        text_so_far: list[str] = []
        try:
            events = stream(
                system_instruction=system_instruction,
                messages=context.messages,
                tools=tools,
            )
            first_event = await events.__anext__()
        except (TypeError, AttributeError, StopAsyncIteration):
            # Provider cannot stream with this client (e.g. SDK signature
            # mismatch): fall back to the buffered call rather than failing.
            buffered_start = time.monotonic()
            response = await self._generate(
                agent, context, system_instruction=system_instruction
            )
            buffered_ms = int((time.monotonic() - buffered_start) * 1000)
            first_token_ms["ms"] = buffered_ms
            if _has_sentence_end(response.text):
                first_sentence_ms["ms"] = buffered_ms
            yield LLMStreamEvent(
                text_delta=response.text,
                done=True,
                full_response=response,
            )
            return

        async def _chained() -> AsyncIterator[LLMStreamEvent]:
            yield first_event
            async for event in events:
                yield event

        async for event in _chained():
            if event.text_delta:
                if "ms" not in first_token_ms:
                    first_token_ms["ms"] = int(
                        (time.monotonic() - llm_start) * 1000
                    )
                text_so_far.append(event.text_delta)
                if "ms" not in first_sentence_ms and _has_sentence_end(
                    "".join(text_so_far)
                ):
                    first_sentence_ms["ms"] = int(
                        (time.monotonic() - llm_start) * 1000
                    )
            yield event

    async def _build_turn_instruction(
        self, agent: Agent, query: str, *, conversation_id: str
    ) -> str:
        """Build the per-turn instruction, grounding it with agent knowledge."""
        instruction = self._build_system_instruction(agent)
        if self._knowledge_retriever is None or not agent.knowledge_sources:
            return instruction
        log_agent_event(
            self._logger,
            "RAG_START",
            tenant_id=agent.tenant_id,
            agent_id=agent.id,
            conversation_id=conversation_id,
            message="RAG_START",
        )
        rag_start = time.monotonic()
        retrieved = await self._knowledge_retriever.retrieve(
            tenant_id=agent.tenant_id,
            agent_id=agent.id,
            query=query,
            top_k=self._knowledge_top_k,
        )
        log_agent_event(
            self._logger,
            "RAG_COMPLETED",
            tenant_id=agent.tenant_id,
            agent_id=agent.id,
            conversation_id=conversation_id,
            duration_ms=int((time.monotonic() - rag_start) * 1000),
            chunks=len(retrieved),
            message="RAG_COMPLETED",
        )
        knowledge = build_knowledge_context(retrieved)
        if knowledge:
            instruction = f"{instruction}\n\n{knowledge}"
        return instruction

    @staticmethod
    def _append_assistant_tool_calls(
        context: ConversationContext, response: LLMResponse
    ) -> None:
        """Persist the assistant turn that requested tools before its results."""
        context.messages.append(
            ConversationMessage(
                role="assistant",
                content=response.text,
                tool_calls=response.tool_calls,
            )
        )

    @staticmethod
    def _append_tool_result(context: ConversationContext, result: ToolResult) -> None:
        context.messages.append(
            ConversationMessage(
                role="tool",
                content=result.model_dump_json(),
                tool_call_id=result.call_id,
            )
        )

    @staticmethod
    def _limit_result(
        call: ProviderToolCall,
    ) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            success=False,
            error="Maximum tool iterations exceeded.",
            metadata={"code": "max_tool_iterations"},
        )

    @staticmethod
    def _tool_engine_unavailable_response(response: LLMResponse) -> LLMResponse:
        return LLMResponse(
            text="Tool execution is unavailable.",
            provider_name=response.provider_name,
            model_name=response.model_name,
            usage=response.usage,
        )

    @staticmethod
    def _build_system_instruction(agent: Agent) -> str:
        """Build the provider-neutral instruction from agent configuration."""
        parts = [
            f"You are {agent.name}, acting as a {agent.role}.",
            f"Personality: {agent.personality}.",
            f"Respond in {agent.language}.",
        ]
        if agent.system_prompt:
            parts.append(agent.system_prompt)
        if agent.goals:
            parts.append(f"Goals: {', '.join(agent.goals)}.")
        return "\n".join(parts)


def _has_sentence_end(text: str) -> bool:
    """Detect a completed speakable sentence without splitting words.

    A sentence end is `.`, `!`, or `?` followed by whitespace or the end of
    the buffer, with at least a few words buffered (so decimals and fragments
    do not count). Tool-call JSON never matches this shape.
    """
    stripped = text.strip()
    if len(stripped.split()) < 3:
        return False
    for index, char in enumerate(stripped):
        if char in ".!?":
            rest = stripped[index + 1 :]
            if not rest or rest[0].isspace():
                return True
    return False

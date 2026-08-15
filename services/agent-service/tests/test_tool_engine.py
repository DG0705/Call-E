"""Tests for the provider-neutral, tenant-safe Agent Runtime tool engine."""

import asyncio
from datetime import UTC, datetime
import json
import logging

import pytest
from fastapi.testclient import TestClient

from agent_service.app import create_agent_app
from agent_service.models import Agent
from agent_service.runtime.context import (
    ConversationContext,
    ConversationMessage,
    InMemoryConversationStore,
)
from agent_service.runtime.provider import LLMResponse, MockLLMProvider
from agent_service.runtime.runtime import AgentRuntime
from agent_service.runtime.tools import (
    EchoCustomerContextTool,
    GetCurrentTimeTool,
    ProviderToolCall,
    ToolCall,
    ToolDefinition,
    ToolEngine,
    ToolExecutionContext,
    ToolRegistry,
    ToolResult,
    create_development_tool_registry,
)


class StaticAgentLoader:
    def __init__(self, agent: Agent) -> None:
        self.agent = agent

    async def get_by_tenant_and_id(
        self, *, tenant_id: str, agent_id: str
    ) -> Agent | None:
        if self.agent.tenant_id == tenant_id and self.agent.id == agent_id:
            return self.agent
        return None


class NoopTenantService:
    async def collection_exists(self) -> bool:
        return True


class NoopAgentService(NoopTenantService):
    async def get_by_tenant_and_id(
        self, *, tenant_id: str, agent_id: str
    ) -> Agent | None:
        return None


class CountingTool:
    def __init__(self, definition: ToolDefinition) -> None:
        self._definition = definition
        self.calls = 0

    def definition(self) -> ToolDefinition:
        return self._definition

    async def execute(
        self, context: ToolExecutionContext, arguments: dict[str, object]
    ) -> ToolResult:
        self.calls += 1
        return ToolResult(
            call_id=context.call_id,
            tool_name=self._definition.tool_name,
            success=True,
            result={"value": arguments["value"]},
        )


class LoopingToolProvider:
    async def generate_response(
        self,
        *,
        system_instruction: str,
        messages: list[ConversationMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        return LLMResponse(
            text="",
            provider_name="looping-test",
            model_name="looping-test-v1",
            tool_calls=[
                ProviderToolCall(
                    call_id=f"call-{len(messages)}",
                    tool_name="echo_customer_context",
                    arguments={"message": "again"},
                )
            ],
        )


def agent(*, allowed_tools: list[str] | None = None) -> Agent:
    now = datetime.now(UTC)
    return Agent(
        id="agent-1",
        tenant_id="tenant-1",
        name="Tool Tester",
        allowed_tools=allowed_tools or ["echo_customer_context", "get_current_time"],
        created_at=now,
        updated_at=now,
    )


def tool_call(**overrides: object) -> ToolCall:
    values: dict[str, object] = {
        "tool_name": "echo_customer_context",
        "arguments": {"message": "hello"},
        "call_id": "call-1",
        "tenant_id": "tenant-1",
        "agent_id": "agent-1",
        "conversation_id": "conversation-1",
    }
    values.update(overrides)
    return ToolCall.model_validate(values)


def test_tool_models_are_typed_and_json_serializable() -> None:
    definition = EchoCustomerContextTool().definition()
    call = tool_call()
    result = ToolResult(
        call_id=call.call_id,
        tool_name=call.tool_name,
        success=True,
        result={"received_message": "hello"},
    )
    context = ToolExecutionContext(
        tenant_id=call.tenant_id,
        agent_id=call.agent_id,
        conversation_id=call.conversation_id,
        call_id=call.call_id,
    )

    assert definition.risk_level == "low"
    assert json.loads(result.model_dump_json())["success"] is True
    assert context.call_id == "call-1"


def test_registry_registers_looks_up_lists_and_rejects_duplicates() -> None:
    registry = ToolRegistry()
    tool = EchoCustomerContextTool()
    registry.register(tool)

    assert registry.get("echo_customer_context") is tool
    assert [definition.tool_name for definition in registry.list()] == [
        "echo_customer_context"
    ]
    with pytest.raises(ValueError, match="already registered"):
        registry.register(EchoCustomerContextTool())


def test_engine_authorizes_validates_and_audits(caplog: pytest.LogCaptureFixture) -> None:
    definition = ToolDefinition(
        tool_name="count",
        description="Count validated calls.",
        version="v1",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    )
    tool = CountingTool(definition)
    registry = ToolRegistry()
    registry.register(tool)
    engine = ToolEngine(registry)
    permitted_agent = agent(allowed_tools=["count"])

    with caplog.at_level(logging.INFO, logger="agent_service.tool_engine"):
        valid = asyncio.run(
            engine.execute(
                agent=permitted_agent,
                call=tool_call(tool_name="count", arguments={"value": "ok"}),
            )
        )
        invalid = asyncio.run(
            engine.execute(agent=permitted_agent, call=tool_call(tool_name="count", arguments={}))
        )

    assert valid.success is True
    assert invalid.success is False
    assert invalid.metadata["code"] == "invalid_arguments"
    assert tool.calls == 1
    assert any(record.message == "tool_execution_audit" for record in caplog.records)


@pytest.mark.parametrize(
    ("definition_updates", "call_updates", "allowed_tools", "code"),
    [
        ({"enabled": False}, {}, ["count"], "tool_disabled"),
        ({}, {"tenant_id": "tenant-2"}, ["count"], "tenant_mismatch"),
        ({"tenant_id": "tenant-2"}, {}, ["count"], "tenant_mismatch"),
        ({}, {}, [], "tool_not_allowed"),
    ],
)
def test_engine_rejects_unauthorized_tools(
    definition_updates: dict[str, object],
    call_updates: dict[str, object],
    allowed_tools: list[str],
    code: str,
) -> None:
    definition = ToolDefinition(
        tool_name="count",
        description="Count validated calls.",
        version="v1",
        input_schema={"type": "object"},
        **definition_updates,
    )
    tool = CountingTool(definition)
    registry = ToolRegistry()
    registry.register(tool)

    result = asyncio.run(
        ToolEngine(registry).execute(
            agent=agent(allowed_tools=allowed_tools),
            call=tool_call(tool_name="count", **call_updates),
        )
    )

    assert result.success is False
    assert result.metadata["code"] == code
    assert tool.calls == 0


def test_development_tools_are_safe_and_structured() -> None:
    registry = create_development_tool_registry()
    engine = ToolEngine(registry)
    configured_agent = agent()

    time_result = asyncio.run(
        engine.execute(
            agent=configured_agent,
            call=tool_call(
                tool_name="get_current_time", arguments={"timezone": "UTC"}
            ),
        )
    )
    echo_result = asyncio.run(
        engine.execute(agent=configured_agent, call=tool_call())
    )

    assert time_result.success is True
    assert time_result.result["timezone"] == "UTC"
    assert echo_result.model_dump()["result"] == {"received_message": "hello"}


def test_runtime_executes_tool_returns_result_to_provider_and_finishes() -> None:
    store = InMemoryConversationStore()
    runtime = AgentRuntime(
        configuration_loader=StaticAgentLoader(agent()),
        provider=MockLLMProvider(
            planned_tool_calls=[
                ProviderToolCall(
                    call_id="call-1",
                    tool_name="echo_customer_context",
                    arguments={"message": "Rahul"},
                )
            ]
        ),
        conversation_store=store,
        tool_registry=create_development_tool_registry(),
    )

    result = asyncio.run(
        runtime.respond(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            message="Echo Rahul",
        )
    )
    context = asyncio.run(
        store.get(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    assert result.text == "Mock response: Echo Rahul"
    assert context is not None
    tool_result = json.loads(next(message.content for message in context.messages if message.role == "tool"))
    assert tool_result == {
        "call_id": "call-1",
        "tool_name": "echo_customer_context",
        "success": True,
        "result": {"received_message": "Rahul"},
        "error": None,
        "metadata": {},
    }


def test_runtime_stops_at_maximum_tool_iterations() -> None:
    store = InMemoryConversationStore()
    runtime = AgentRuntime(
        configuration_loader=StaticAgentLoader(agent()),
        provider=LoopingToolProvider(),
        conversation_store=store,
        tool_registry=create_development_tool_registry(),
        max_tool_iterations=1,
    )

    result = asyncio.run(
        runtime.respond(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            message="Loop",
        )
    )
    context = asyncio.run(
        store.get(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    assert result.text == "Tool execution limit exceeded."
    assert context is not None
    assert any("max_tool_iterations" in message.content for message in context.messages)


def test_registry_available_for_filters_by_enabled_allowed_and_tenant() -> None:
    registry = create_development_tool_registry()
    registry.register(
        CountingTool(
            ToolDefinition(
                tool_name="tenant_only",
                description="Tenant scoped.",
                version="v1",
                input_schema={"type": "object"},
                tenant_id="tenant-2",
            )
        )
    )
    disabled = CountingTool(
        ToolDefinition(
            tool_name="disabled_tool",
            description="Disabled.",
            version="v1",
            input_schema={"type": "object"},
            enabled=False,
        )
    )
    registry.register(disabled)

    names = [
        definition.tool_name
        for definition in registry.available_for(agent(allowed_tools=["echo_customer_context", "tenant_only", "disabled_tool"]))
    ]

    assert names == ["echo_customer_context"]


def test_engine_rejects_unknown_and_failing_tools() -> None:
    class BrokenTool:
        def definition(self) -> ToolDefinition:
            return ToolDefinition(
                tool_name="broken",
                description="Always fails.",
                version="v1",
                input_schema={"type": "object"},
            )

        async def execute(
            self, context: ToolExecutionContext, arguments: dict[str, object]
        ) -> ToolResult:
            raise RuntimeError("boom")

    registry = ToolRegistry()
    registry.register(BrokenTool())
    engine = ToolEngine(registry)

    missing = asyncio.run(
        engine.execute(agent=agent(allowed_tools=["missing"]), call=tool_call(tool_name="missing"))
    )
    broken = asyncio.run(
        engine.execute(
            agent=agent(allowed_tools=["broken"]),
            call=tool_call(tool_name="broken", arguments={}),
        )
    )

    assert missing.metadata["code"] == "tool_not_found"
    assert broken.metadata["code"] == "execution_failed"
    assert broken.success is False


def test_engine_rejects_agent_mismatch_and_records_audit_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    registry = create_development_tool_registry()
    engine = ToolEngine(registry)

    with caplog.at_level(logging.INFO, logger="agent_service.tool_engine"):
        result = asyncio.run(
            engine.execute(
                agent=agent(),
                call=tool_call(agent_id="other-agent"),
            )
        )

    assert result.success is False
    assert result.metadata["code"] == "agent_mismatch"
    audit = next(record for record in caplog.records if record.message == "tool_execution_audit")
    assert audit.tool_audit["tool_name"] == "echo_customer_context"
    assert audit.tool_audit["success"] is False
    assert audit.tool_audit["tenant_id"] == "tenant-1"


def test_tool_test_endpoint_executes_mock_tool_flow_and_propagates_request_id() -> None:
    runtime = AgentRuntime(
        configuration_loader=StaticAgentLoader(agent()),
        provider=MockLLMProvider(
            planned_tool_calls=[
                ProviderToolCall(
                    call_id="call-1",
                    tool_name="echo_customer_context",
                    arguments={"message": "endpoint"},
                )
            ]
        ),
        conversation_store=InMemoryConversationStore(),
        tool_registry=create_development_tool_registry(),
    )
    client = TestClient(
        create_agent_app(
            tenant_service=NoopTenantService(),
            agent_service=NoopAgentService(),
            agent_runtime=runtime,
        )
    )

    response = client.post(
        "/api/v1/agents/agent-1/runtime/tool-test?tenant_id=tenant-1",
        headers={"X-Request-ID": "tool-request"},
        json={"conversation_id": "conversation-1", "message": "Use a tool"},
    )

    assert response.status_code == 200
    assert response.json()["response"] == "Mock response: Use a tool"
    assert response.json()["request_id"] == "tool-request"
    assert response.headers["X-Request-ID"] == "tool-request"
    assert response.json()["provider"] == "mock"
    assert response.json()["agent_id"] == "agent-1"
    assert response.json()["conversation_id"] == "conversation-1"


def test_runtime_persists_conversation_after_tool_loop() -> None:
    store = InMemoryConversationStore()
    runtime = AgentRuntime(
        configuration_loader=StaticAgentLoader(agent()),
        provider=MockLLMProvider(
            planned_tool_calls=[
                ProviderToolCall(
                    call_id="call-1",
                    tool_name="get_current_time",
                    arguments={"timezone": "UTC"},
                )
            ]
        ),
        conversation_store=store,
        tool_registry=create_development_tool_registry(),
    )

    first = asyncio.run(
        runtime.respond(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            message="What time is it?",
        )
    )
    second = asyncio.run(
        runtime.respond(
            tenant_id="tenant-1",
            agent_id="agent-1",
            conversation_id="conversation-1",
            message="Thanks",
        )
    )
    isolated = asyncio.run(
        store.get(
            tenant_id="tenant-2", agent_id="agent-1", conversation_id="conversation-1"
        )
    )
    context = asyncio.run(
        store.get(
            tenant_id="tenant-1", agent_id="agent-1", conversation_id="conversation-1"
        )
    )

    assert first.provider_name == "mock"
    assert second.text == "Mock response: Thanks"
    assert isolated is None
    assert context is not None
    assert [message.role for message in context.messages].count("user") == 2
    assert any(message.role == "tool" for message in context.messages)

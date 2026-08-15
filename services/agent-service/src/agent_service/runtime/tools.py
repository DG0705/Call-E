"""Provider-neutral tool engine for safe, authorized agent actions."""

from datetime import UTC, datetime
import logging
from typing import Literal, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jsonschema import Draft202012Validator, ValidationError
from pydantic import BaseModel, Field, JsonValue

from agent_service.models import Agent


ToolRiskLevel = Literal["low", "medium", "high"]


class ToolDefinition(BaseModel):
    """A provider-neutral description of an executable agent tool."""

    tool_name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    version: str = Field(min_length=1)
    input_schema: dict[str, JsonValue]
    tenant_id: str | None = None
    enabled: bool = True
    risk_level: ToolRiskLevel = "low"
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class ToolCall(BaseModel):
    """A tenant-scoped request for one registered tool execution."""

    tool_name: str = Field(min_length=1)
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    call_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)


class ToolResult(BaseModel):
    """Structured, JSON-serializable result of an attempted tool call."""

    call_id: str
    tool_name: str
    success: bool
    result: JsonValue | None = None
    error: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class ToolExecutionContext(BaseModel):
    """The restricted runtime state exposed to a tool implementation."""

    tenant_id: str
    agent_id: str
    conversation_id: str
    call_id: str
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class ProviderToolCall(BaseModel):
    """Provider-neutral tool-call shape emitted by an LLM adapter."""

    call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class Tool(Protocol):
    """Contract implemented by safe, provider-neutral business tools."""

    def definition(self) -> ToolDefinition: ...

    async def execute(
        self, context: ToolExecutionContext, arguments: dict[str, JsonValue]
    ) -> ToolResult: ...


class ToolRegistry:
    """Injectable registry that owns a controlled set of tool implementations."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        definition = tool.definition()
        if definition.tool_name in self._tools:
            raise ValueError(f"Tool '{definition.tool_name}' is already registered.")
        self._tools[definition.tool_name] = tool

    def get(self, tool_name: str) -> Tool | None:
        return self._tools.get(tool_name)

    def list(self) -> list[ToolDefinition]:
        return [tool.definition() for tool in self._tools.values()]

    def available_for(self, agent: Agent) -> list[ToolDefinition]:
        """List only enabled, tenant-compatible tools allowed to this agent."""
        return [
            definition
            for definition in self.list()
            if definition.enabled
            and definition.tool_name in agent.allowed_tools
            and (definition.tenant_id is None or definition.tenant_id == agent.tenant_id)
        ]


class ToolEngine:
    """Authorize, validate, execute, and audit registered tool calls."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        self._logger = logging.getLogger("agent_service.tool_engine")

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    async def execute(self, *, agent: Agent, call: ToolCall) -> ToolResult:
        """Execute one call only after all authorization and validation checks pass."""
        result = self._authorize(agent=agent, call=call)
        if result is None:
            tool = self._registry.get(call.tool_name)
            assert tool is not None
            definition = tool.definition()
            try:
                Draft202012Validator(definition.input_schema).validate(call.arguments)
            except ValidationError as exc:
                result = self._failure(call, "invalid_arguments", exc.message)
            else:
                context = ToolExecutionContext(
                    tenant_id=call.tenant_id,
                    agent_id=call.agent_id,
                    conversation_id=call.conversation_id,
                    call_id=call.call_id,
                )
                try:
                    result = await tool.execute(context, call.arguments)
                except Exception:
                    self._logger.exception("tool_execution_failed", extra={"tool": call.tool_name})
                    result = self._failure(call, "execution_failed", "Tool execution failed.")
                else:
                    result = result.model_copy(
                        update={"call_id": call.call_id, "tool_name": call.tool_name}
                    )
        self._audit(call, result)
        return result

    def _authorize(self, *, agent: Agent, call: ToolCall) -> ToolResult | None:
        tool = self._registry.get(call.tool_name)
        if tool is None:
            return self._failure(call, "tool_not_found", "Requested tool is not registered.")
        definition = tool.definition()
        if call.tenant_id != agent.tenant_id:
            return self._failure(call, "tenant_mismatch", "Tool call tenant does not match agent.")
        if definition.tenant_id is not None and definition.tenant_id != call.tenant_id:
            return self._failure(call, "tenant_mismatch", "Tool is not available to this tenant.")
        if not definition.enabled:
            return self._failure(call, "tool_disabled", "Requested tool is disabled.")
        if call.tool_name not in agent.allowed_tools:
            return self._failure(call, "tool_not_allowed", "Agent is not allowed to use this tool.")
        return None

    @staticmethod
    def _failure(call: ToolCall, code: str, error: str) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            success=False,
            error=error,
            metadata={"code": code},
        )

    def _audit(self, call: ToolCall, result: ToolResult) -> None:
        event = {
            "tenant_id": call.tenant_id,
            "agent_id": call.agent_id,
            "conversation_id": call.conversation_id,
            "call_id": call.call_id,
            "tool_name": call.tool_name,
            "success": result.success,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self._logger.info("tool_execution_audit", extra={"tool_audit": event})


class GetCurrentTimeTool:
    """Read-only development tool returning the current time for a timezone."""

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            tool_name="get_current_time",
            description="Get the current time in an IANA timezone.",
            version="v1",
            input_schema={
                "type": "object",
                "properties": {"timezone": {"type": "string", "minLength": 1}},
                "required": ["timezone"],
                "additionalProperties": False,
            },
            risk_level="low",
        )

    async def execute(
        self, context: ToolExecutionContext, arguments: dict[str, JsonValue]
    ) -> ToolResult:
        timezone = str(arguments["timezone"])
        try:
            current_time = datetime.now(ZoneInfo(timezone)).isoformat()
        except ZoneInfoNotFoundError:
            return ToolResult(
                call_id=context.call_id,
                tool_name=self.definition().tool_name,
                success=False,
                error="Unknown timezone.",
                metadata={"code": "invalid_timezone"},
            )
        return ToolResult(
            call_id=context.call_id,
            tool_name=self.definition().tool_name,
            success=True,
            result={"timezone": timezone, "current_time": current_time},
        )


class EchoCustomerContextTool:
    """Safe development tool that returns the provided message unchanged."""

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            tool_name="echo_customer_context",
            description="Echo customer context for development runtime testing.",
            version="v1",
            input_schema={
                "type": "object",
                "properties": {"message": {"type": "string", "minLength": 1}},
                "required": ["message"],
                "additionalProperties": False,
            },
            risk_level="low",
        )

    async def execute(
        self, context: ToolExecutionContext, arguments: dict[str, JsonValue]
    ) -> ToolResult:
        return ToolResult(
            call_id=context.call_id,
            tool_name=self.definition().tool_name,
            success=True,
            result={"received_message": arguments["message"]},
        )


def create_development_tool_registry() -> ToolRegistry:
    """Create the controlled development tool set used by the application."""
    registry = ToolRegistry()
    registry.register(GetCurrentTimeTool())
    registry.register(EchoCustomerContextTool())
    return registry

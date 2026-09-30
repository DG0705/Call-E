"""Groq implementation of the provider-neutral LLM interface."""

from collections.abc import AsyncIterator, Mapping
import json
from typing import Any, Protocol

from agent_service.runtime.context import ConversationMessage

from agent_service.runtime.provider import (
    LLMResponse,
    LLMStreamEvent,
    ToolCallFragment,
)
from agent_service.runtime.tools import ProviderToolCall, ToolDefinition


class GroqCompletions(Protocol):
    async def create(self, **kwargs: Any) -> Any: ...


class GroqChat(Protocol):
    completions: GroqCompletions


class GroqClient(Protocol):
    chat: GroqChat


class GroqProvider:
    """Generate responses using Groq's official asynchronous Python SDK."""

    provider_name = "groq"

    def __init__(
        self, *, api_key: str, model: str, client: GroqClient | None = None
    ) -> None:
        if not api_key:
            raise ValueError("GROQ_API_KEY is required to configure GroqProvider.")
        if not model:
            raise ValueError("GROQ_MODEL is required to configure GroqProvider.")
        self._model = model
        self._client = client or self._create_client(api_key)

    async def generate_response(
        self,
        *,
        system_instruction: str,
        messages: list[ConversationMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        """Send the runtime-built instruction and context to Groq unchanged."""
        request: dict[str, Any] = {
            "model": self._model,
            "messages": _to_groq_messages(system_instruction, messages),
        }
        if tools:
            request["tools"] = [_to_groq_tool(tool) for tool in tools]
        completion = await self._client.chat.completions.create(**request)
        text = completion.choices[0].message.content or ""
        return LLMResponse(
            text=text,
            provider_name=self.provider_name,
            model_name=self._model,
            usage=_normalize_usage(getattr(completion, "usage", None)),
            tool_calls=_parse_tool_calls(completion.choices[0].message),
        )

    @staticmethod
    def _create_client(api_key: str) -> GroqClient:
        """Import the optional SDK only when the Groq provider is selected."""
        from groq import AsyncGroq

        return AsyncGroq(api_key=api_key)

    def generate_response_stream(
        self,
        *,
        system_instruction: str,
        messages: list[ConversationMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        """Stream generation as text and tool-call deltas arrive.

        Tool-call fragments stream by index and are assembled only at
        completion: incomplete fragments (missing id or name) are dropped, so
        the tool engine never executes a partial call and no call executes
        twice. A malformed arguments payload falls back to ``{}``.
        """
        return self._stream_generation(
            system_instruction=system_instruction, messages=messages, tools=tools
        )

    async def _stream_generation(
        self,
        *,
        system_instruction: str,
        messages: list[ConversationMessage],
        tools: list[ToolDefinition] | None,
    ) -> AsyncIterator[LLMStreamEvent]:
        request: dict[str, Any] = {
            "model": self._model,
            "messages": _to_groq_messages(system_instruction, messages),
            "stream": True,
        }
        if tools:
            request["tools"] = [_to_groq_tool(tool) for tool in tools]
        stream = await self._client.chat.completions.create(**request)
        text_parts: list[str] = []
        fragments: dict[int, dict[str, Any]] = {}
        usage: dict[str, int] = {}
        async for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            delta = getattr(choices[0], "delta", None) if choices else None
            content = getattr(delta, "content", None)
            if content:
                text_parts.append(str(content))
                yield LLMStreamEvent(text_delta=str(content))
            for tool_call in getattr(delta, "tool_calls", None) or []:
                index = getattr(tool_call, "index", 0) or 0
                fragment = fragments.setdefault(
                    int(index), {"id": None, "name": None, "arguments": ""}
                )
                if getattr(tool_call, "id", None):
                    fragment["id"] = tool_call.id
                function = getattr(tool_call, "function", None)
                if function is not None:
                    if getattr(function, "name", None):
                        fragment["name"] = function.name
                    if getattr(function, "arguments", None):
                        fragment["arguments"] += str(function.arguments)
                yield LLMStreamEvent(
                    tool_call_delta=ToolCallFragment(
                        index=int(index),
                        call_id=str(fragment["id"])
                        if fragment["id"]
                        else None,
                        tool_name=str(fragment["name"])
                        if fragment["name"]
                        else None,
                        arguments_text=str(fragment["arguments"] or ""),
                    )
                )
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage is not None:
                usage = _normalize_usage(chunk_usage)
        tool_calls: list[ProviderToolCall] = []
        for fragment in fragments.values():
            if not fragment["id"] or not fragment["name"]:
                continue
            try:
                arguments = json.loads(fragment["arguments"] or "{}")
            except (TypeError, json.JSONDecodeError):
                arguments = {}
            if not isinstance(arguments, dict):
                arguments = {}
            tool_calls.append(
                ProviderToolCall(
                    call_id=str(fragment["id"]),
                    tool_name=str(fragment["name"]),
                    arguments=arguments,
                )
            )
        yield LLMStreamEvent(
            done=True,
            full_response=LLMResponse(
                text="".join(text_parts),
                provider_name=self.provider_name,
                model_name=self._model,
                usage=usage,
                tool_calls=tool_calls,
            ),
        )


def _normalize_usage(usage: Any) -> dict[str, int]:
    """Expose common completion usage fields when Groq supplies them."""
    names = ("prompt_tokens", "completion_tokens", "total_tokens")
    values: dict[str, int] = {}
    for name in names:
        value = usage.get(name) if isinstance(usage, Mapping) else getattr(usage, name, None)
        if value is not None:
            values[name] = int(value)
    return values


def _to_groq_tool(definition: ToolDefinition) -> dict[str, Any]:
    """Convert a neutral definition into Groq's function-tool request shape."""
    return {
        "type": "function",
        "function": {
            "name": definition.tool_name,
            "description": definition.description,
            "parameters": definition.input_schema,
        },
    }


def _to_groq_messages(
    system_instruction: str, messages: list[ConversationMessage]
) -> list[dict[str, Any]]:
    """Convert neutral messages into the chat shape Groq requires for tools."""
    converted: list[dict[str, Any]] = [
        {"role": "system", "content": system_instruction}
    ]
    for message in messages:
        if message.role == "system":
            continue
        if message.role == "assistant" and message.tool_calls:
            converted.append(
                {
                    "role": "assistant",
                    "content": message.content or None,
                    "tool_calls": [_to_groq_tool_call(call) for call in message.tool_calls],
                }
            )
        elif message.role == "tool":
            tool_message: dict[str, Any] = {"role": "tool", "content": message.content}
            if message.tool_call_id is not None:
                tool_message["tool_call_id"] = message.tool_call_id
            converted.append(tool_message)
        else:
            converted.append({"role": message.role, "content": message.content})
    return converted


def _to_groq_tool_call(call: ProviderToolCall) -> dict[str, Any]:
    """Serialize a neutral tool call to the shape Groq expects on assistant turns."""
    return {
        "id": call.call_id,
        "type": "function",
        "function": {"name": call.tool_name, "arguments": json.dumps(call.arguments)},
    }


def _parse_tool_calls(message: Any) -> list[ProviderToolCall]:
    """Convert Groq SDK tool calls without leaking provider types to runtime."""
    parsed: list[ProviderToolCall] = []
    for tool_call in getattr(message, "tool_calls", None) or []:
        function = getattr(tool_call, "function", None)
        call_id = getattr(tool_call, "id", None)
        tool_name = getattr(function, "name", None) if function is not None else None
        if not call_id or not tool_name:
            continue
        try:
            arguments = json.loads(getattr(function, "arguments", "{}") or "{}")
        except (TypeError, json.JSONDecodeError):
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        parsed.append(
            ProviderToolCall(
                call_id=call_id,
                tool_name=tool_name,
                arguments=arguments,
            )
        )
    return parsed

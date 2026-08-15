# agent-service

The agent service hosts the tenant-scoped Agent Runtime foundation. The runtime
loads provider-neutral agent configuration, keeps a small conversation context,
and delegates response generation to an interchangeable LLM provider. The local
mock provider is used by default, so development and tests need no API key.

## LLM providers

`LLM_PROVIDER=mock` is the default. It uses a deterministic local response and
never makes a network request. Set `LLM_PROVIDER=groq` to use the Groq provider
through the same provider-neutral runtime boundary. Groq is enabled only when
both its API key and model are configured:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=your-configured-secret
GROQ_MODEL=your-configured-model
```

If `LLM_PROVIDER=groq` is set without `GROQ_API_KEY`, the service safely uses
the mock provider instead. No provider API key is required for local tests.

Groq request/response translation stays inside `GroqProvider`. `AgentRuntime`
only sees provider-neutral `LLMResponse` and `ProviderToolCall` values.

## Tool Engine

The Tool Engine is the only path through which an agent can request an external
action. The LLM reasons; tools execute. Tools are provider-neutral
`ToolDefinition` objects registered in an injectable `ToolRegistry`. The runtime
exposes only enabled tools that match the agent's tenant and `allowed_tools`
configuration.

### Architecture

```text
LLM
 ↓
Tool Call
 ↓
Authorization
 ↓
Argument Validation
 ↓
Tool Execution
 ↓
Tool Result
 ↓
LLM
 ↓
Final Response
```

### Authorization flow

Before any tool runs, `ToolEngine` checks:

1. The tool exists in the registry.
2. The call `tenant_id` matches the loaded agent tenant.
3. The call `agent_id` matches the loaded agent.
4. The tool's own `tenant_id` (when set) matches the call tenant.
5. The tool is enabled.
6. The agent's `allowed_tools` contains the tool name.

Failures return a structured `ToolResult` with `success=false` and a
`metadata.code` such as `tool_not_found`, `tenant_mismatch`, `agent_mismatch`,
`tool_disabled`, or `tool_not_allowed`.

### Validation flow

Authorized calls validate `arguments` against the tool's JSON Schema
(`input_schema`) before execution. Schema failures return
`metadata.code=invalid_arguments` and never invoke the tool.

### Execution flow

1. Load agent configuration for `tenant_id` + `agent_id`.
2. Load or create the conversation for `tenant_id` + `agent_id` + `conversation_id`.
3. Resolve allowed tool definitions from the registry.
4. Provide those definitions to the LLM provider.
5. Receive zero or more provider-neutral `ProviderToolCall` values.
6. Persist the assistant turn that requested the tools (including its
   provider-neutral `tool_calls`).
7. Authorize and validate each call.
8. Execute with a restricted `ToolExecutionContext` (`tenant_id`, `agent_id`,
   `conversation_id`, `call_id`, `metadata` only — no database handles or secrets).
9. Append each JSON-serializable `ToolResult` to the conversation as a `tool`
   message that keeps its `tool_call_id`, so provider adapters can replay the
   conversation in the shape their API requires.
10. Continue LLM generation with the updated conversation.
11. Stop when the provider returns text without tool calls, or when
    `MAX_TOOL_ITERATIONS` is reached (default `5`).
12. Persist the conversation and return the final response.

Each attempt emits a structured audit log (`tool_execution_audit`) with tenant,
agent, conversation, call, tool name, success, and timestamp. Argument and
result payloads are intentionally omitted from the audit record.

### Development tools

Safe development-only tools currently registered:

| Tool | Input | Output | Notes |
|------|-------|--------|-------|
| `get_current_time` | `timezone` (IANA) | `timezone`, `current_time` | Read-only |
| `echo_customer_context` | `message` | `received_message` | Echo only |

Real CRM, payment, and booking tools are intentionally not implemented yet.

### Runtime tool-test endpoint

```http
POST /api/v1/agents/{agent_id}/runtime/tool-test?tenant_id={tenant_id}
```

Body:

```json
{
  "conversation_id": "demo-1",
  "message": "Echo Rahul"
}
```

The endpoint uses the configured Agent Runtime with the agent's
`allowed_tools`, conversation identity, and registered development tools. With
`LLM_PROVIDER=mock` (or a test-injected `MockLLMProvider` that emits planned
tool calls), the full authorize → validate → execute → continue loop can be
exercised without Groq, network access, or external services.

Example:

```bash
curl -X POST 'http://localhost/api/v1/agents/agent-1/runtime/tool-test?tenant_id=tenant-1' \
  -H 'Content-Type: application/json' \
  -d '{"conversation_id":"demo-1","message":"Hello"}'
```

### Example lifecycle

1. Client calls `runtime/tool-test` with tenant, agent, conversation, and message.
2. Runtime loads the agent and conversation, then asks the mock provider for a reply.
3. Mock provider returns a `ProviderToolCall` for `echo_customer_context`.
4. Tool Engine authorizes the agent/tool/tenant combination and validates arguments.
5. The tool returns `{"received_message":"..."}` inside a `ToolResult`.
6. Runtime appends the tool result, asks the provider again, and receives final text.
7. Conversation state is persisted under the compound identity
   `tenant_id` + `agent_id` + `conversation_id`.

## Current endpoints

- `GET /health`
- `GET /api/v1/tenants/status`
- `GET /api/v1/tenants/ping-db`
- `GET /api/v1/agents/status`
- `GET /api/v1/agents/ping-db`
- `GET /api/v1/agents/{agent_id}?tenant_id={tenant_id}`
- `POST /api/v1/agents/{agent_id}/runtime/test?tenant_id={tenant_id}`
- `POST /api/v1/agents/{agent_id}/runtime/tool-test?tenant_id={tenant_id}`

The `ping-db` routes inspect their MongoDB collection without creating or
modifying data. Normal agent-service runtime wiring persists conversation memory
in MongoDB. Conversations are identified and isolated by the compound identity
`tenant_id`, `agent_id`, and `conversation_id`, so a conversation cannot be
read across tenants or agents. The complete provider-neutral message history is
reused on later runtime-test requests with the same identity.

For unit tests or explicitly local wiring, `InMemoryConversationStore` remains
available as an injected `ConversationStore`. Production application wiring
uses `MongoConversationStore` and creates its compound lookup index at startup.

Example runtime test request:

```bash
curl -X POST 'http://localhost/api/v1/agents/agent-1/runtime/test?tenant_id=tenant-1' \
  -H 'Content-Type: application/json' \
  -d '{"conversation_id":"demo-1","message":"Hello"}'
```

Phone calling, telephony, STT/TTS, RAG, and production LLM providers other than
Groq deliberately come later. This service does not implement those integrations
or business workflows.

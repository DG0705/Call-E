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

## Tool Engine

The Tool Engine is the only path through which an agent can request an external
action. Tools are provider-neutral `ToolDefinition` objects registered in an
injectable `ToolRegistry`; the runtime exposes only enabled tools that match the
agent's tenant and `allowed_tools` configuration. Before execution, the engine
checks tenant scope and agent authorization, validates JSON arguments against
the tool input schema, then supplies a restricted `ToolExecutionContext`.

Current development tools are read-only `get_current_time` and test-only
`echo_customer_context`. Each attempt emits a structured audit log record. The
engine caps provider tool loops with `MAX_TOOL_ITERATIONS` (default `5`).

```text
LLM
 ↓
ToolCall
 ↓
Authorization
 ↓
Validation
 ↓
Tool Execution
 ↓
ToolResult
 ↓
LLM
 ↓
Final Response
```

Current endpoints:

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


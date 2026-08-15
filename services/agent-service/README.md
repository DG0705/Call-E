# agent-service

The agent service hosts the tenant-scoped Agent Runtime foundation. The runtime
loads provider-neutral agent configuration, keeps a small conversation context,
and delegates response generation to an interchangeable LLM provider. The local
mock provider is used by default, so development and tests need no API key.

Current endpoints:

- `GET /health`
- `GET /api/v1/tenants/status`
- `GET /api/v1/tenants/ping-db`
- `GET /api/v1/agents/status`
- `GET /api/v1/agents/ping-db`
- `GET /api/v1/agents/{agent_id}?tenant_id={tenant_id}`
- `POST /api/v1/agents/{agent_id}/runtime/test?tenant_id={tenant_id}`

The `ping-db` routes inspect their MongoDB collection without creating or
modifying data. The runtime test endpoint is development-only and stores its
conversation context in memory.

Example runtime test request:

```bash
curl -X POST 'http://localhost/api/v1/agents/agent-1/runtime/test?tenant_id=tenant-1' \
  -H 'Content-Type: application/json' \
  -d '{"conversation_id":"demo-1","message":"Hello"}'
```

Phone calling, telephony, STT/TTS, tool execution, RAG, and production LLM
providers deliberately come later. This service does not implement those
integrations or business workflows.


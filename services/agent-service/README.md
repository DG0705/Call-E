# agent-service

The agent service hosts the minimal, read-only platform core boundary for tenants
and agents. It does not implement telephony, AI, billing, or business workflows.

Public core routes:

- `GET /api/v1/tenants/status`
- `GET /api/v1/tenants/ping-db`
- `GET /api/v1/agents/status`
- `GET /api/v1/agents/ping-db`

The `ping-db` routes inspect their MongoDB collection without creating or
modifying data.


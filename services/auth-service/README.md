# auth-service

The auth service currently provides the platform's authentication foundation
only; it does not implement login, registration, credentials, or tokens.

Public routes:

- `GET /health`
- `GET /api/v1/auth/status`
- `GET /api/v1/auth/ping-db` — read-only MongoDB check for the future
  `auth_accounts` collection. It never creates or modifies records.

Through Docker Compose, the foundation status is available at:

```text
http://localhost/api/v1/auth/status
```

The database check is available at:

```text
http://localhost/api/v1/auth/ping-db
```

Run locally with:

```powershell
uv run uvicorn auth_service.main:app --reload
```

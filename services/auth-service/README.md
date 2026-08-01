# auth-service

The auth service currently provides the platform's authentication foundation
only; it does not implement login, registration, credentials, or tokens.

Public routes:

- `GET /health`
- `GET /api/v1/auth/status`

Through Docker Compose, the foundation status is available at:

```text
http://localhost/api/v1/auth/status
```

Run locally with:

```powershell
uv run uvicorn auth_service.main:app --reload
```

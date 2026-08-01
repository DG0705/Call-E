# api-gateway

The API Gateway is Call-E's public HTTP entry point. It owns platform-level
routes and currently exposes:

- `GET /health`
- `GET /api/v1/status`
- `GET /api/v1/info`
- `GET /api/v1/ping`

All public routes use the shared versioned platform response helper. When
running through Docker Compose, call the routes through Traefik:

```text
http://localhost/health
http://localhost/api/v1/status
http://localhost/api/v1/info
http://localhost/api/v1/ping
```

Run locally with:

```powershell
uv run uvicorn api_gateway.main:app --reload
```

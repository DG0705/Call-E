# Call-E

Call-E is a Python 3.13 microservice monorepo managed with [uv](https://docs.astral.sh/uv/).

## Services

| Service | Responsibility |
| --- | --- |
| api-gateway | Public API entry point |
| call-orchestrator | Call workflow coordination |
| auth-service | Authentication and authorization |
| contacts-service | Contact management |
| campaign-service | Campaign management |
| voice-service | Voice synthesis boundary |
| transcription-service | Speech transcription boundary |
| ai-service | AI provider boundary |
| analytics-service | Analytics boundary |
| notification-service | Notification delivery boundary |

Each service has the same layout:

```text
services/<service>/
├── .env.example
├── Dockerfile
├── pyproject.toml
├── src/<service_package>/
│   ├── __init__.py
│   └── main.py
└── tests/
    └── __init__.py
```

## Quick start

```powershell
uv sync --all-packages
uv run --package call-e-api-gateway uvicorn api_gateway.main:app --reload
```

The health endpoint is available at `GET /health`.

## Docker

Build a service from its own directory:

```powershell
docker build -t call-e-api-gateway ./services/api-gateway
docker run --rm -p 8000:8000 call-e-api-gateway
```

Use `docker compose up --build` to start all service placeholders.

## Development

- Copy each `.env.example` to `.env` before adding service configuration.
- Keep business logic inside the service that owns its boundary.
- Add dependencies to the owning service's `pyproject.toml`.


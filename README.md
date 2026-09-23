# Call-E

Call-E is a Python 3.13 microservice monorepo managed with [uv](https://docs.astral.sh/uv/). The local platform stack uses Docker Compose, Traefik, MongoDB, and RabbitMQ. The services are deliberately logic-free foundations for future development and import shared primitives from the workspace-owned `call-e-shared` package.

The shared package also provides a stable versioned JSON response helper used
by the API Gateway public routes: `/api/v1/status`, `/api/v1/info`, and
`/api/v1/ping`.

The shared response helper is also used by the shared health route, keeping all
public API Gateway responses on one stable JSON contract.

## Prerequisites

- Docker Desktop 4.30+ with Docker Compose v2
- Docker Engine configured to run Linux containers
- uv and Python 3.13, only for running services outside Docker

## Setup

Create the local runtime environment file and set non-empty local credentials:

```powershell
Copy-Item .env.example .env
```

Update these values in `.env`:

```dotenv
MONGO_INITDB_ROOT_USERNAME=call_e_admin
MONGO_INITDB_ROOT_PASSWORD=use-a-strong-local-password
RABBITMQ_DEFAULT_USER=call_e
RABBITMQ_DEFAULT_PASS=use-a-strong-local-password
TRAEFIK_DASHBOARD=true
```

The `.env` file is ignored by Git. Do not commit credentials. The root
`.env.example` documents every variable: core credentials plus the
`LLM_PROVIDER`/`GROQ_*`, `VOICE_STT_PROVIDER`/`DEEPGRAM_*`,
`VOICE_TTS_PROVIDER`/`ELEVENLABS_*`, `TELEPHONY_PROVIDER`/`ASTERISK_*`, and
`KAARI_DEV_EXTENSION` settings (all default to `mock`).

## Running the Kaari phone-call development stack

Exact setup (see `services/voice-service/README.md` for the full call guide):

1. `Copy-Item .env.example .env`
2. Fill real credentials in `.env` (or leave `mock` providers for local dev).
3. Set local Asterisk passwords in
   `services/voice-service/telephony/asterisk/config/pjsip.conf` (`dev-phone`)
   and `ari.conf` (`call-e-user`); never commit them.
4. Start core services: `docker compose up -d --build mongodb rabbitmq
   traefik agent-service knowledge-service voice-service`
5. Start Asterisk: `docker compose -f docker-compose.yml
   -f docker-compose.asterisk.yml up -d --build asterisk`
6. Verify: `.venv\Scripts\python.exe tools\dev_check.py` (expect `RESULT: OK`).
7. Register a SIP softphone against `localhost:5060` as `dev-phone`.
8. Dial Kaari extension `1000` (or `$KAARI_DEV_EXTENSION`).
9. Conduct the test conversation (greeting → requirement → pricing → lead).
10. Inspect MongoDB: `conversations` for the transcript, `leads` for the
    created sales lead (`tenant_id=kaari-planters`).

Live provider smoke (real Groq/Deepgram/ElevenLabs/ARI calls, local only):

```powershell
.venv\Scripts\python.exe tools\smoke_live_providers.py --live
```

Note: on Docker Desktop for Windows the Traefik docker provider may fail to
read the Engine socket, so host-port routes can 404 while services stay
healthy in-network; use `docker compose exec <service>` to reach them.

## Running locally

```powershell
docker compose up --build
```

Compose creates the `call-e-network` bridge network and persistent MongoDB and RabbitMQ volumes. All FastAPI services wait for MongoDB and RabbitMQ to pass their health checks before starting.

Stop the stack while retaining data:

```powershell
docker compose down
```

Remove the stack and its local data volumes:

```powershell
docker compose down --volumes
```

View service status or logs:

```powershell
docker compose ps
docker compose logs -f api-gateway
```

## Routes

Traefik is the public entry point on port 80. A route prefix is stripped before it reaches each FastAPI application, so the health endpoint follows this pattern:

| Service | Health URL |
| --- | --- |
| API Gateway | http://localhost/health |
| Auth | http://localhost/auth-service/health |
| AI | http://localhost/ai-service/health |
| Voice | http://localhost/voice-service/health |
| Call | http://localhost/call-service/health |
| Tool | http://localhost/tool-service/health |
| Knowledge | http://localhost/knowledge-service/health |
| Analytics | http://localhost/analytics-service/health |
| Notification | http://localhost/notification-service/health |
| Agent | http://localhost/agent-service/health |

Each service also serves `/health` inside the Docker network at `http://<service-name>:8000/health`.

The auth-service foundation is available at
`http://localhost/api/v1/auth/status`. It reports only platform readiness;
authentication workflows are intentionally not implemented.
The shared `AuthContext` value object provides a minimal future boundary for
authenticated subjects and sessions without implementing authentication.

The read-only platform core routes are available through Traefik at
`/api/v1/tenants/status`, `/api/v1/tenants/ping-db`,
`/api/v1/agents/status`, and `/api/v1/agents/ping-db` (and `/health`).
The status routes report stable platform readiness; the optional `ping-db`
routes only check collection visibility. No workflows or mutations are
implemented.

## Operations UIs

- Traefik dashboard: http://localhost:8080/dashboard/
- RabbitMQ management UI: http://localhost:15672/ (use `RABBITMQ_DEFAULT_USER` and `RABBITMQ_DEFAULT_PASS`)

## MongoDB

MongoDB is intentionally not published to the host. Other containers connect using:

```text
mongodb://<MONGO_INITDB_ROOT_USERNAME>:<MONGO_INITDB_ROOT_PASSWORD>@mongodb:27017/?authSource=admin
```

Its data persists in the `call-e-mongodb-data` Docker volume. RabbitMQ data persists in `call-e-rabbitmq-data`.

## Repository layout

```text
services/<service>/
├── .env.example
├── .dockerignore
├── Dockerfile
├── pyproject.toml
├── src/<service_package>/
│   ├── __init__.py
│   └── main.py
└── tests/
    └── __init__.py
```

Every service image uses a multi-stage build: uv resolves dependencies in the builder stage and a small Python 3.13 slim runtime runs the application as an unprivileged user.

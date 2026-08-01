# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:latest AS uv

FROM python:3.13-slim AS builder

COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml ./
COPY shared/pyproject.toml shared/README.md ./shared/
COPY services/campaign-service/pyproject.toml services/campaign-service/README.md ./services/campaign-service/
RUN uv sync --no-dev --package call-e-campaign-service --no-install-project

COPY shared/src ./shared/src
COPY services/campaign-service/src ./services/campaign-service/src
RUN uv sync --no-dev --package call-e-campaign-service

FROM python:3.13-slim AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system app && useradd --system --gid app --home /app app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv ./.venv
COPY --from=builder --chown=app:app /app/shared/src ./shared/src
COPY --from=builder --chown=app:app /app/services/campaign-service/src ./services/campaign-service/src

USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "campaign_service.main:app", "--host", "0.0.0.0", "--port", "8000"]

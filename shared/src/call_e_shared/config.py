"""Service configuration helpers."""

from dataclasses import dataclass
import os

from call_e_shared.constants import (
    APP_ENV_ENV_VAR,
    DEFAULT_ENVIRONMENT,
    DEFAULT_LOG_LEVEL,
    DEFAULT_PORT,
    LOG_LEVEL_ENV_VAR,
    PORT_ENV_VAR,
    SERVICE_NAME_ENV_VAR,
)


@dataclass(frozen=True, slots=True)
class ServiceSettings:
    """Runtime settings common to every service."""

    service_name: str
    port: int = DEFAULT_PORT
    environment: str = DEFAULT_ENVIRONMENT
    log_level: str = DEFAULT_LOG_LEVEL


def load_settings(*, default_service_name: str) -> ServiceSettings:
    """Load shared service settings from the environment."""
    return ServiceSettings(
        service_name=os.getenv(SERVICE_NAME_ENV_VAR, default_service_name),
        port=_load_port(),
        environment=os.getenv(APP_ENV_ENV_VAR, DEFAULT_ENVIRONMENT),
        log_level=os.getenv(LOG_LEVEL_ENV_VAR, DEFAULT_LOG_LEVEL).upper(),
    )


def _load_port() -> int:
    """Read a valid port while preserving a safe local default."""
    try:
        port = int(os.getenv(PORT_ENV_VAR, str(DEFAULT_PORT)))
    except ValueError:
        return DEFAULT_PORT
    return port if 1 <= port <= 65535 else DEFAULT_PORT

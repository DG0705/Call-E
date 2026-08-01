"""Health endpoint utilities."""

from call_e_shared.config import ServiceSettings
from call_e_shared.responses import HealthResponse


def build_health_response(settings: ServiceSettings) -> HealthResponse:
    """Build the standard health response for a service."""
    return HealthResponse(service=settings.service_name)

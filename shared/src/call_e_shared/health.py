"""Health endpoint utilities."""

from call_e_shared.config import ServiceSettings
from call_e_shared.responses import PlatformResponse, build_platform_response


def build_health_response(
    settings: ServiceSettings, *, request_id: str | None = None
) -> PlatformResponse:
    """Build the standard health response for a service."""
    return build_platform_response(
        service_name=settings.service_name,
        request_id=request_id,
    )

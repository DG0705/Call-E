"""Read-only auth database route."""

from fastapi import APIRouter, Request

from auth_service.repositories import AuthAccountRepository
from call_e_shared import PlatformResponse, build_platform_response
from call_e_shared.exceptions import PlatformError


AUTH_DATABASE_DESCRIPTION = "Auth database connection verified"

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _get_repository(request: Request) -> AuthAccountRepository:
    return request.app.state.auth_repository


@router.get("/ping-db", response_model=PlatformResponse, response_model_exclude_none=True)
async def ping_database(request: Request) -> PlatformResponse:
    """Verify that MongoDB can inspect the auth collection without writing data."""
    try:
        await _get_repository(request).collection_exists()
    except Exception as exc:
        raise PlatformError(
            code="auth_database_unavailable",
            message="Auth database is unavailable.",
            status_code=503,
        ) from exc
    return build_platform_response(
        service_name=request.app.title,
        request_id=getattr(request.state, "request_id", None),
        description=AUTH_DATABASE_DESCRIPTION,
    )

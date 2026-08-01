"""Auth service application assembly."""

from fastapi import FastAPI

from auth_service.routes.status import router as status_router
from call_e_shared import create_app


AUTH_SERVICE_NAME = "auth-service"


def create_auth_app() -> FastAPI:
    """Create the auth service application foundation."""
    app = create_app(AUTH_SERVICE_NAME)
    app.include_router(status_router)
    return app

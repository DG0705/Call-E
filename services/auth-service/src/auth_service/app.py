"""Auth service application assembly."""

from fastapi import FastAPI

from auth_service.database import AuthDatabase, create_auth_database
from auth_service.repositories import AuthAccountRepository
from auth_service.routes.database import router as database_router
from auth_service.routes.status import router as status_router
from call_e_shared import create_app


AUTH_SERVICE_NAME = "auth-service"


def create_auth_app(
    *,
    auth_repository: AuthAccountRepository | None = None,
    auth_database: AuthDatabase | None = None,
) -> FastAPI:
    """Create the auth service application foundation."""
    app = create_app(AUTH_SERVICE_NAME)
    database = auth_database or (None if auth_repository else create_auth_database())
    app.state.auth_repository = auth_repository or database.repository
    app.include_router(status_router)
    app.include_router(database_router)

    if database is not None:

        @app.on_event("shutdown")
        async def close_auth_database() -> None:
            await database.close()

    return app

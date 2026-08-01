"""Gateway application assembly."""

from fastapi import FastAPI

from api_gateway.routes.info import router as info_router
from api_gateway.routes.status import router as status_router
from call_e_shared import create_app


GATEWAY_SERVICE_NAME = "api-gateway"


def create_gateway_app() -> FastAPI:
    """Create the public API Gateway application."""
    app = create_app(GATEWAY_SERVICE_NAME)
    app.include_router(status_router)
    app.include_router(info_router)
    return app

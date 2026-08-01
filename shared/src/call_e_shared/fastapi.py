"""Reusable FastAPI application support."""

from collections.abc import Awaitable, Callable
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from call_e_shared.config import load_settings
from call_e_shared.constants import HEALTH_PATH, REQUEST_ID_HEADER
from call_e_shared.exceptions import PlatformError, error_response
from call_e_shared.health import build_health_response
from call_e_shared.logging import configure_logging
from call_e_shared.request_id import (
    create_request_id,
    reset_request_id,
    set_request_id,
)
from call_e_shared.responses import HealthResponse

RequestHandler = Callable[[Request], Awaitable[Response]]


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a request identifier to every request and response."""

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or create_request_id()
        request.state.request_id = request_id
        token = set_request_id(request_id)
        try:
            response = await call_next(request)
        finally:
            reset_request_id(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def create_app(service_name: str) -> FastAPI:
    """Create a consistent FastAPI service shell."""
    settings = load_settings(default_service_name=service_name)
    configure_logging(service_name=settings.service_name, level=settings.log_level)
    app = FastAPI(title=settings.service_name)
    app.add_middleware(RequestIDMiddleware)

    @app.get(HEALTH_PATH, response_model=HealthResponse, tags=["platform"])
    async def health(request: Request) -> HealthResponse:
        return build_health_response(
            settings,
            request_id=getattr(request.state, "request_id", None),
        )

    @app.exception_handler(PlatformError)
    async def handle_platform_error(
        request: Request, exc: PlatformError
    ) -> Response:
        return error_response(
            request,
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
        )

    @app.exception_handler(HTTPException)
    async def handle_http_error(request: Request, exc: HTTPException) -> Response:
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return error_response(
            request,
            code="http_error",
            message=message,
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, _: RequestValidationError
    ) -> Response:
        return error_response(
            request,
            code="request_validation_error",
            message="Request validation failed.",
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, _: Exception) -> Response:
        return error_response(
            request,
            code="internal_error",
            message="An unexpected error occurred.",
            status_code=500,
        )

    return app

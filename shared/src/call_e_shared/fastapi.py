"""Reusable FastAPI application support."""

from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from call_e_shared.config import ServiceSettings
from call_e_shared.constants import HEALTH_PATH, REQUEST_ID_HEADER
from call_e_shared.exceptions import PlatformError, error_response
from call_e_shared.health import build_health_response
from call_e_shared.logging import configure_logging, request_id_context
from call_e_shared.responses import HealthResponse

RequestHandler = Callable[[Request], Awaitable[Response]]


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a request identifier to every request and response."""

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid4())
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_context.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def create_app(settings: ServiceSettings) -> FastAPI:
    """Create a consistent FastAPI service shell."""
    configure_logging(level=settings.log_level, logger_name=settings.service_name)
    app = FastAPI(title=settings.service_name)
    app.add_middleware(RequestIDMiddleware)

    @app.get(HEALTH_PATH, response_model=HealthResponse, tags=["platform"])
    async def health() -> HealthResponse:
        return build_health_response(settings)

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

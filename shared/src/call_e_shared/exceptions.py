"""Platform exception types and response helpers."""

from fastapi import Request
from fastapi.responses import JSONResponse

from call_e_shared.responses import ErrorDetail, ErrorResponse


class PlatformError(Exception):
    """Expected platform error with a safe API representation."""

    def __init__(self, *, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def error_response(
    request: Request,
    *,
    code: str,
    message: str,
    status_code: int,
) -> JSONResponse:
    """Create a standardized JSON error response."""
    request_id = getattr(request.state, "request_id", None)
    payload = ErrorResponse(
        error=ErrorDetail(code=code, message=message, request_id=request_id)
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())

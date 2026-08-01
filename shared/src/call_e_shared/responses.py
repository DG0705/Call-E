"""Standard API response models."""

from typing import Generic, TypeVar

from pydantic import BaseModel

DataT = TypeVar("DataT")


class APIResponse(BaseModel, Generic[DataT]):
    """Envelope for successful API responses."""

    data: DataT
    request_id: str | None = None


class ErrorDetail(BaseModel):
    """Serializable error metadata."""

    code: str
    message: str
    request_id: str | None = None


class ErrorResponse(BaseModel):
    """Envelope for API errors."""

    error: ErrorDetail


class PlatformResponse(BaseModel):
    """Stable versioned response for lightweight platform endpoints."""

    service_name: str
    status: str = "healthy"
    version: str = "v1"
    request_id: str | None = None
    description: str | None = None


def build_platform_response(
    *,
    service_name: str,
    status: str = "healthy",
    version: str = "v1",
    request_id: str | None = None,
    description: str | None = None,
) -> PlatformResponse:
    """Build a stable JSON response shared across platform endpoints."""
    return PlatformResponse(
        service_name=service_name,
        status=status,
        version=version,
        request_id=request_id,
        description=description,
    )

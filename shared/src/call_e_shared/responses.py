"""Standard API response models."""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

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


class HealthResponse(BaseModel):
    """Standard service health response."""

    status: str = Field(default="healthy")
    service: str

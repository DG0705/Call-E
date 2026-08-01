"""Request identifier utilities."""

from contextvars import ContextVar, Token
from uuid import uuid4

request_id_context: ContextVar[str | None] = ContextVar(
    "request_id", default=None
)


def create_request_id() -> str:
    """Create a request identifier for an inbound request."""
    return str(uuid4())


def get_request_id() -> str | None:
    """Return the request identifier for the current context."""
    return request_id_context.get()


def set_request_id(request_id: str) -> Token[str | None]:
    """Set the request identifier for the current context."""
    return request_id_context.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Restore the preceding request identifier context."""
    request_id_context.reset(token)

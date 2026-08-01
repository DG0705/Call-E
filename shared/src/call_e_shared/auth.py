"""Minimal shared authentication primitives."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Identity context for future authentication and session boundaries."""

    subject_id: str | None = None
    session_id: str | None = None

    @property
    def is_authenticated(self) -> bool:
        """Return whether the context represents an identified subject."""
        return self.subject_id is not None

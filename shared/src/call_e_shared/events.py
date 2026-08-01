"""Event naming helpers."""


def event_name(*, domain: str, action: str, version: int = 1) -> str:
    """Return a versioned event name using the platform convention."""
    normalized_domain = domain.strip().replace(" ", "-").lower()
    normalized_action = action.strip().replace(" ", "-").lower()
    if not normalized_domain or not normalized_action:
        raise ValueError("Event domain and action must be non-empty.")
    if version < 1:
        raise ValueError("Event version must be positive.")
    return f"{normalized_domain}.{normalized_action}.v{version}"

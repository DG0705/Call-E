"""FastAPI application for the notification-service service."""

from fastapi import FastAPI


app = FastAPI(title="notification-service")


@app.get("/health")
async def health() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "healthy", "service": "notification-service"}


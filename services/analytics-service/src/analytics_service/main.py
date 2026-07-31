"""FastAPI application for the analytics-service service."""

from fastapi import FastAPI


app = FastAPI(title="analytics-service")


@app.get("/health")
async def health() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "healthy", "service": "analytics-service"}


"""FastAPI application for the call-service service."""

from fastapi import FastAPI


app = FastAPI(title="call-service")


@app.get("/health")
async def health() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "healthy", "service": "call-service"}


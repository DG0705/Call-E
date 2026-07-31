"""FastAPI application for the voice-service service."""

from fastapi import FastAPI


app = FastAPI(title="voice-service")


@app.get("/health")
async def health() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "healthy", "service": "voice-service"}


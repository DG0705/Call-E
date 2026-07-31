"""FastAPI application for the ai-service service."""

from fastapi import FastAPI


app = FastAPI(title="ai-service")


@app.get("/health")
async def health() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "healthy", "service": "ai-service"}


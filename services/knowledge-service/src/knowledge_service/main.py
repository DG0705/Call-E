"""FastAPI application for the knowledge-service service."""

from fastapi import FastAPI


app = FastAPI(title="knowledge-service")


@app.get("/health")
async def health() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "healthy", "service": "knowledge-service"}


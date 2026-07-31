"""FastAPI application for the tool-service service."""

from fastapi import FastAPI


app = FastAPI(title="tool-service")


@app.get("/health")
async def health() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "healthy", "service": "tool-service"}


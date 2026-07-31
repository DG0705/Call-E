"""FastAPI application for the api-gateway service."""

from fastapi import FastAPI


app = FastAPI(title="api-gateway")


@app.get("/health")
async def health() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "healthy", "service": "api-gateway"}


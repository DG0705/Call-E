"""FastAPI application for the campaign-service service."""

from fastapi import FastAPI


app = FastAPI(title="campaign-service")


@app.get("/health")
async def health() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "healthy", "service": "campaign-service"}


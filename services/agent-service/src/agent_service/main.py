"""FastAPI application for the agent-service service."""

from fastapi import FastAPI


app = FastAPI(title="agent-service")


@app.get("/health")
async def health() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "healthy", "service": "agent-service"}


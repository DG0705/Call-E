"""FastAPI application for the call-orchestrator service."""

from fastapi import FastAPI


app = FastAPI(title="call-orchestrator")


@app.get("/health")
async def health() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "healthy", "service": "call-orchestrator"}


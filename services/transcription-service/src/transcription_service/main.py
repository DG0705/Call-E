"""FastAPI application for the transcription-service service."""

from fastapi import FastAPI


app = FastAPI(title="transcription-service")


@app.get("/health")
async def health() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "healthy", "service": "transcription-service"}


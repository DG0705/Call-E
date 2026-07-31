"""FastAPI application for the contacts-service service."""

from fastapi import FastAPI


app = FastAPI(title="contacts-service")


@app.get("/health")
async def health() -> dict[str, str]:
    """Return the service health status."""
    return {"status": "healthy", "service": "contacts-service"}


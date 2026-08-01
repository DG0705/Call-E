"""FastAPI application for the voice-service service."""

from call_e_shared import create_app


app = create_app("voice-service")

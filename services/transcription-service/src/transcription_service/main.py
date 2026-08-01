"""FastAPI application for the transcription-service service."""

from call_e_shared import create_app


app = create_app("transcription-service")

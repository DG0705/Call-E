"""FastAPI application for the tool-service service."""

from call_e_shared import create_app


app = create_app("tool-service")

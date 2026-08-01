"""FastAPI application for the auth-service service."""

from call_e_shared import create_app


app = create_app("auth-service")

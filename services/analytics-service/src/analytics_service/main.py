"""FastAPI application for the analytics-service service."""

from call_e_shared import create_app


app = create_app("analytics-service")

"""FastAPI application for the campaign-service service."""

from call_e_shared import create_app


app = create_app("campaign-service")

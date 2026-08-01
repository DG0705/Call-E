"""FastAPI application for the api-gateway service."""

from call_e_shared import create_app


app = create_app("api-gateway")

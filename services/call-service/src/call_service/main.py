"""FastAPI application for the call-service service."""

from call_e_shared import create_app


app = create_app("call-service")

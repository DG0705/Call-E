"""FastAPI application for the contacts-service service."""

from call_e_shared import create_app


app = create_app("contacts-service")

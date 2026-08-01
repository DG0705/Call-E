"""FastAPI application for the notification-service service."""

from call_e_shared import create_app


app = create_app("notification-service")

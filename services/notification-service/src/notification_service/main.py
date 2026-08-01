"""FastAPI application for the notification-service service."""

from call_e_shared import create_app, load_settings


settings = load_settings(default_service_name="notification-service")
app = create_app(settings)
